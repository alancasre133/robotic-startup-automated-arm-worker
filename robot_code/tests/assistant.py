"""
Robot assistant brain — voice in, voice out, and full motion control.

Pipeline:  mic -> transcribe (Vosk) -> brain (Claude / offline) -> {speak, drive, music} -> repeat

TWO brains, automatic fallback:
  1. Claude API (smart)  — natural language, when a key is set and the API works.
  2. Offline rules (free) — keyword parser; no key, no internet, no extra installs.

What MELVINN can do (Claude brain; the offline brain covers the basics):
  DRIVE     move forward / go back / turn left / spin / stop
  ARM       move the arm, poses (home/ready/reach/lift/drop), gripper, dance
  GRAB      grab the red object / pick up all the blue ones (camera-guided)
  SENSE     how far is the thing ahead? / look for the green object
  MUSIC     play a song / download <song> / stop the music
  VIDEO     download <video> / play it on your face (LCD + speaker)
  FACE      show an expression (happy/sad/thinking/surprised/sleepy/love),
            display text on the screen, screen off
  VOICE     change voice, list voices, sound effects (robot/dalek/monster...),
            animal sounds (bark, meow, howl...)
  SCRIPTS   run the test scripts (arm test, distance monitor, ...)
  stop      interrupts whatever is running (motors, grab, dance, video)

Modes:
  python3 robot_code/tests/assistant.py           -> VOICE mode  (mic -> Vosk -> brain)
  python3 robot_code/tests/assistant.py --type    -> TEXT  mode  (keyboard -> brain)

Setup (on the Pi):
  # Install system deps (arecord, from alsa-utils, is what does mic capture --
  # not Python's sounddevice/PortAudio, which can't negotiate the USB
  # speakerphone's sample rate on the raw ALSA default device)
  sudo apt install -y espeak-ng alsa-utils mpg123

  # Install yt-dlp for song downloads
  pip install yt-dlp

  # Vosk for offline speech recognition
  pip install vosk
  # If it fails with "cannot enable executable stack" (seen on trixie/armhf),
  # patch its bundled native library. execstack itself isn't packaged for
  # Trixie -- use patchelf instead:
  sudo apt install -y patchelf
  patchelf --clear-execstack "$(python3 -c 'import vosk,os;print(os.path.join(os.path.dirname(vosk.__file__),"libvosk.so"))')"
  # Download a small English model (~40 MB):
  wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
  unzip vosk-model-small-en-us-0.15.zip -d ~/
  mv ~/vosk-model-small-en-us-0.15 ~/vosk-model

  # Optional: Claude brain
  python3 -m venv --system-site-packages ~/venv
  source ~/venv/bin/activate
  pip install anthropic vosk yt-dlp
  export ANTHROPIC_API_KEY=sk-ant-...
"""

import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from time import sleep
from glob import glob

from gpiozero import Motor

try:
    from melvinn_voice import chirp          # MELVINN's little tone language
except Exception:
    def chirp(_name):                        # no-op if unavailable (e.g. no sox)
        return False

try:
    import anthropic
except ImportError:
    anthropic = None

try:
    from vosk import Model, KaldiRecognizer
    _VOSK_AVAILABLE = True
except (ImportError, OSError):
    # OSError (not just ImportError) because a broken/incompatible native
    # library -- e.g. vosk's bundled libvosk.so refusing to load with
    # "cannot enable executable stack" -- must not crash this whole module.
    # Anything that only needs ARM_JOINTS/robot_move_arm/robot_drive (arm_test.py,
    # arm_jog_test.py, motor scripts) imports assistant.py and would otherwise
    # die here even though it never touches voice input at all.
    _VOSK_AVAILABLE = False

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MODEL          = "claude-haiku-4-5"
AUDIO_DEVICE   = "plughw:1,0"          # USB speakerphone (card 1)
MIC_DEVICE     = "plughw:1,0"          # same device, via arecord (see transcribe())
SAMPLE_RATE    = 16000
VOSK_MODEL_DIR = os.path.expanduser("~/vosk-model")
MUSIC_DIR      = os.path.expanduser("~/music")
PIPER_MODEL    = os.environ.get("PIPER_MODEL", os.path.expanduser("~/piper/voice.onnx"))

client = None
if anthropic is not None and os.environ.get("ANTHROPIC_API_KEY"):
    try:
        client = anthropic.Anthropic()
    except Exception:
        client = None

# ---------------------------------------------------------------------------
# Hardware — motors (4WD, one BTS7960 per side)
# ---------------------------------------------------------------------------
# Two BTS7960 boards replaced the single L9110S, which overheated at ~3x its
# channel rating and left the bot too torque-starved to start from rest. Each
# board drives that side's two motors in parallel; gpiozero's Motor(forward,
# backward) maps straight onto the boards' RPWM/LPWM direction inputs.
# Wiring lives in README "Wiring reference -> Drive"; bring-up is bts7960_test.py.
motor_left = motor_right = None
_music_proc = None          # currently playing mpg123 process

# Jab the motors a few times before steady drive to break static friction on a
# heavy/top-heavy bot. Needed on the L9110S, where breakaway torque was ~0.4-0.6x
# what the chassis demanded; the BTS7960s deliver enough to start from rest
# directly, so this is off and starts are instant and quiet. Set True again if
# the bot ever struggles to break loose (heavier payload, worn battery).
ROCK_START = False
# One round of jabbing isn't always enough at this weight -- confirmed on-device,
# it sometimes took several manual re-runs of rock_test.py before it broke loose.
# Automate that instead of making the user relaunch the script repeatedly.
ROCK_ROUNDS = 3


def _ensure_motors():
    global motor_left, motor_right
    if motor_left is None:
        motor_left = Motor(forward=16, backward=20, pwm=False)
        motor_right = Motor(forward=27, backward=22, pwm=False)
    return motor_left, motor_right


def robot_drive(direction: str, seconds: float = 1.0) -> str:
    if direction == "stop":
        if motor_left is not None:
            motor_left.stop()
            motor_right.stop()
        return "Stopped."
    if direction not in ("forward", "backward", "left", "right", "spin"):
        return f"Unknown direction: {direction}"
    left, right = _ensure_motors()
    moves = {
        "forward":  (left.forward,  right.forward),
        "backward": (left.backward, right.backward),
        "left":     (left.backward, right.forward),   # counter-rotate to port
        "right":    (left.forward,  right.backward),  # counter-rotate to starboard
        "spin":     (left.forward,  right.backward),  # same as right, kept as its own verb
    }
    left_fn, right_fn = moves[direction]

    # "Rock" to break static friction on a heavy / top-heavy chassis. The motors
    # are already driven at full voltage (pwm=False), so there's no "more power"
    # to give — instead we jab in the target direction a few times to jolt the
    # bot loose from a standstill, then commit to steady drive. Toggle with the
    # ROCK_START flag. Repeated ROCK_ROUNDS times since one round doesn't always
    # break it loose. This only helps it START moving; it can't fix sustained
    # crawling (that needs more volts or less weight — see HARDWARE.md).
    if ROCK_START:
        for _round in range(ROCK_ROUNDS):
            for _ in range(3):
                left_fn()
                right_fn()
                sleep(0.12)
                left.stop()
                right.stop()
                sleep(0.06)
            if _round < ROCK_ROUNDS - 1:
                sleep(0.25)  # let it settle before the next round

    left_fn()
    right_fn()
    secs = min(seconds, 5)
    sleep(secs)
    left.stop()
    right.stop()
    return f"Drove {direction} for {secs} seconds."


# ---------------------------------------------------------------------------
# Hardware — arm (PCA9685 + servos, channels 0-5 in ARM_JOINTS order)
# ---------------------------------------------------------------------------
# Order verified empirically with arm_jog_test.py on the rebuilt arm: gripper
# is the LAST channel (5), with wrist_rotate ("wrist twist") on channel 4.
ARM_JOINTS = ("base", "shoulder", "elbow", "wrist", "wrist_rotate", "gripper")

# Per-joint "center"/rest angle -- what arm_jog_test.py and arm_sequence.py
# move each joint to on startup, and what a "recenter" jog keypress returns
# to. Defaults to 90 (servo midpoint) for every joint; override individual
# joints here if their natural neutral position isn't 90 (e.g. gripper's
# resting open/closed angle). shoulder/elbow tuned to clear the chassis on
# this build -- confirmed on-device.
ARM_CENTER_ANGLES = {j: 90.0 for j in ARM_JOINTS}
ARM_CENTER_ANGLES["shoulder"] = 180.0
ARM_CENTER_ANGLES["elbow"] = 45.0

try:
    import board
    import busio
    from adafruit_pca9685 import PCA9685
    from adafruit_motor import servo as _servo_lib
    _ARM_LIBS_AVAILABLE = True
except ImportError:
    _ARM_LIBS_AVAILABLE = False

_pca = None
_arm_servos = {}


def _ensure_arm():
    """Connect to the PCA9685 on first arm command (mirrors _ensure_motors)."""
    global _pca
    if _pca is not None or not _ARM_LIBS_AVAILABLE:
        return _pca
    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        pca = PCA9685(i2c)
        pca.frequency = 50
        for i, joint in enumerate(ARM_JOINTS):
            _arm_servos[joint] = _servo_lib.Servo(pca.channels[i], min_pulse=500, max_pulse=2500)
        _pca = pca
    except Exception:
        _pca = None
    return _pca


# Remember each joint's last commanded angle so smooth moves can step from where
# the joint actually is, 1 degree at a time.
_arm_current = {}
SMOOTH_STEP = 1.0       # degrees per step when moving smoothly
SMOOTH_DELAY = 0.02     # seconds between steps (0.02 * 90 steps ≈ 1.8s per 90°)
MAX_NUDGE = 20.0        # cap a single nudge so moves stay gentle, never abrupt


def robot_move_arm(joint: str, angle: float, smooth: bool = False) -> str:
    """Move one arm joint (PCA9685 servo) to an angle in degrees (0-180).

    smooth=True steps 1 degree at a time (SMOOTH_STEP) with a short pause between
    steps, so the arm glides instead of snapping — gentler on the servos and less
    likely to fling or knock the object. The first move of a joint (unknown
    starting angle) jumps directly; after that it interpolates from the last
    commanded angle.
    """
    if not _ARM_LIBS_AVAILABLE:
        return "Arm libraries not installed — see docs/arm-setup.md"
    if _ensure_arm() is None:
        return "Arm not connected (PCA9685 not found on I2C) — check wiring."
    joint = joint if joint in ARM_JOINTS else "base"
    angle = max(0.0, min(180.0, angle))

    if smooth and joint in _arm_current:
        cur = _arm_current[joint]
        step = SMOOTH_STEP if angle >= cur else -SMOOTH_STEP
        a = cur
        while abs(a - angle) > abs(step):
            a += step
            _arm_servos[joint].angle = a
            sleep(SMOOTH_DELAY)

    _arm_servos[joint].angle = angle
    _arm_current[joint] = angle
    return f"Moved {joint} to {angle:.0f} degrees."


def nudge_arm(joint: str, degrees: float) -> str:
    """Move one joint BY a relative amount — surgical fine positioning.

    GLIDES to the new angle (never snaps) and caps a single move at MAX_NUDGE
    degrees, so motion stays gentle even if a big step is requested. Steps from
    the joint's last commanded angle (its centre angle if it hasn't moved yet).
    """
    if not _ARM_LIBS_AVAILABLE:
        return "Arm libraries not installed — see docs/arm-setup.md"
    if _ensure_arm() is None:
        return "Arm not connected (PCA9685 not found on I2C) — check wiring."
    if joint not in ARM_JOINTS:
        return f"Unknown joint: {joint}. Joints: {', '.join(ARM_JOINTS)}."
    asked = float(degrees)
    degrees = max(-MAX_NUDGE, min(MAX_NUDGE, asked))     # keep moves gentle
    cur = _arm_current.get(joint, ARM_CENTER_ANGLES[joint])
    target = max(0.0, min(180.0, cur + degrees))
    if target == cur:
        return f"{joint} is already at its {cur:.0f}-degree limit."
    _arm_current.setdefault(joint, cur)                  # so it glides, not snaps
    robot_move_arm(joint, target, smooth=True)           # ease in, don't jump
    capped = " (capped to 20)" if abs(asked) > MAX_NUDGE else ""
    return f"{joint}: {cur:.0f} -> {target:.0f} degrees ({target - cur:+.1f}){capped}."


def arm_status() -> str:
    """Report every joint's current (last commanded) angle."""
    parts = []
    for j in ARM_JOINTS:
        if j in _arm_current:
            parts.append(f"{j} {_arm_current[j]:.0f}")
        else:
            parts.append(f"{j} ~{ARM_CENTER_ANGLES[j]:.0f} (not moved yet)")
    return "Joint angles: " + ", ".join(parts) + "."


# ---------------------------------------------------------------------------
# Arm poses + gripper — named presets used by the grab behaviour
# ---------------------------------------------------------------------------
# ⚠️ CALIBRATE THESE ON THE ROBOT with arm_jog_test.py. The angles below are
# neutral guesses, NOT tuned to your arm — jog each joint to the pose you want,
# then copy the numbers in. Wrong angles can make the arm hit itself or the
# chassis: move slowly the first time and keep a hand near the power.
ARM_POSES = {
    # Calibrated on-device with arm_jog_test.py (gripper handled separately below).
    # base shoulder elbow wrist wrist_rotate
    "home":  {"base": 90, "shoulder": 180, "elbow": 45, "wrist": 90, "wrist_rotate": 90},
    "ready": {"base": 90, "shoulder": 180, "elbow": 45, "wrist": 90, "wrist_rotate": 90},
    "reach": {"base": 90, "shoulder": 100, "elbow": 10, "wrist": 95, "wrist_rotate": 0},
    "lift":  {"base": 90, "shoulder": 140, "elbow": 20, "wrist": 95, "wrist_rotate": 180},
    "drop":  {"base": 90, "shoulder": 140, "elbow": 20, "wrist": 95, "wrist_rotate": 180},
}
GRIPPER_OPEN = 15.0     # calibrated: open the hand (also the release angle)
GRIPPER_CLOSE = 150.0   # calibrated: grip an object

ARM_REACH_CM = 22.0     # trigger "in reach" at ~this distance — tuned to where the
                        # object actually sits when the arm's reach pose lands on it
STOP_CM = 5.0           # never drive forward when something is this close


def arm_pose(name: str, smooth: bool = True) -> str:
    """Move the whole arm to a named pose (home/ready/reach/lift/drop).

    Smooth by default — each joint glides 1 degree at a time, one joint after
    another, so the whole arm moves calmly.
    """
    pose = ARM_POSES.get(name)
    if pose is None:
        return f"Unknown arm pose: {name}. Try home, ready, reach, lift, or drop."
    for joint, angle in pose.items():
        robot_move_arm(joint, angle, smooth=smooth)
    return f"Arm at {name}."


def gripper(state: str) -> str:
    """Open or close the gripper (the hand). Closes gently, 1 degree at a time,
    so it settles onto the object instead of snapping shut."""
    angle = GRIPPER_OPEN if state == "open" else GRIPPER_CLOSE
    robot_move_arm("gripper", angle, smooth=True)
    return f"Gripper {state}."


def center_arm() -> str:
    """Move every joint to its centre angle — the same known starting position
    arm_jog_test.py uses. Done first so the arm begins from a predictable place
    (and so the later smooth moves interpolate from a known point instead of
    jumping on their first command). Not smoothed: the very first move has no
    prior angle to glide from."""
    for joint in ARM_JOINTS:
        robot_move_arm(joint, ARM_CENTER_ANGLES[joint])
    return "Arm centred."


# ---------------------------------------------------------------------------
# Sensing — HC-SR04 ultrasonic (forward distance)
# ---------------------------------------------------------------------------
# Confirmed wiring (physical pins): Trig -> pin 33 (GPIO13), Echo -> pin 35
# (GPIO19) via a 1k/2k divider. Same as obstacle_avoid.py.
TRIG_PIN = 13           # BCM
ECHO_PIN = 19           # BCM
_distance_sensor = None
_distance_unavailable = False
_distance_lock = threading.Lock()   # serialize HC-SR04 pulses across threads


def distance_ahead() -> float:
    """Distance in cm to the nearest object ahead. Returns -1 if no sensor.

    Takes the MEDIAN of 3 quick reads. The HC-SR04 on software-timed pins is
    jittery — a single read occasionally misses the echo and reports the full
    range (a "spike" like 119 cm when the object is really at 18). The median of
    three throws out one bad spike, giving a steady number for the grab loop.

    Lazy-inits the HC-SR04 on first call (like the motors/arm) so merely
    importing this module never touches the GPIO pins.
    """
    global _distance_sensor, _distance_unavailable
    if _distance_unavailable:
        return -1.0
    # The lock keeps two threads (e.g. the grab loop + a distance monitor) from
    # pulsing the HC-SR04 at the same time, which would corrupt both readings.
    with _distance_lock:
        if _distance_sensor is None:
            try:
                from gpiozero import DistanceSensor
                _distance_sensor = DistanceSensor(
                    echo=ECHO_PIN, trigger=TRIG_PIN, max_distance=2.0
                )
            except Exception:
                _distance_unavailable = True
                return -1.0
        reads = []
        for _ in range(3):
            try:
                reads.append(_distance_sensor.distance * 100.0)    # metres -> cm
            except Exception:
                pass
            sleep(0.02)
    if not reads:
        return -1.0
    reads.sort()
    return reads[len(reads) // 2]    # median


# ---------------------------------------------------------------------------
# Sensing — camera (colour-blob object finding, via perception.py)
# ---------------------------------------------------------------------------
# perception.py imports picamera2 + OpenCV, which the arm/motor-only scripts
# don't need — so import it lazily, only when the camera is actually used.
_perception = None
_camera = None
_camera_unavailable = False
CENTER_DEADZONE = 0.15      # |offset| under this counts as centred


def _ensure_camera():
    """Open the camera on first use (single-user; falls back to None if busy)."""
    global _perception, _camera, _camera_unavailable
    if _camera is not None or _camera_unavailable:
        return _camera
    try:
        import perception
        _perception = perception
        _camera = perception.open_camera()
    except Exception as exc:
        print(f"[camera unavailable: {exc}] — grab will use the ultrasonic only")
        _camera_unavailable = True
        _camera = None
    return _camera


def _close_camera():
    """Release the camera so the stream service (or next run) can use it."""
    global _camera
    if _camera is not None:
        try:
            _camera.stop()
        except Exception:
            pass
        _camera = None


def look_for_object(color: str = "red", frames: int = 4) -> dict:
    """Ask the camera where the largest `color` object is. See perception.find_object.

    Samples several frames and returns the BEST (largest-area) hit. The detector
    drops a frame now and then even when the object is plainly there — a single
    "not seen" would make the grab loop sweep away and lose its lock. Checking a
    few frames and keeping the best one rides over those one-frame dropouts.
    """
    cam = _ensure_camera()
    if cam is None or _perception is None:
        return {"seen": False, "error": "camera unavailable"}
    best = {"seen": False}
    for _ in range(max(1, frames)):
        try:
            r = _perception.find_object(cam, color)
        except Exception as exc:
            return {"seen": False, "error": str(exc)}
        if r.get("seen") and r.get("area_frac", 0) >= best.get("area_frac", -1):
            best = r
    return best


def best_distance(color: str = "red"):
    """Best available distance-to-object in cm, plus where it came from.

    Prefers the ultrasonic (a true measurement). If the ultrasonic returns -1 —
    the object is outside its narrow forward beam, or it isn't wired — it falls
    back to the LEARNED camera estimate from distance_calibrate.py. This is what
    makes the calibration actually useful: the robot can judge distance from what
    it sees, not just from the sonar. Returns (cm, source) where source is
    'ultrasonic', 'camera', or 'none' (with cm = -1).
    """
    d = distance_ahead()
    if d >= 0:
        return d, "ultrasonic"
    if _ensure_camera() is not None and _perception is not None:
        r = look_for_object(color)
        if r.get("seen"):
            est = _perception.estimate_distance(r["area_frac"])
            if est >= 0:
                return est, "camera"
    return -1.0, "none"


# ---------------------------------------------------------------------------
# Background actions — multitask + a voice kill-switch
# ---------------------------------------------------------------------------
# Long actions (a grab, a grab-everything loop) run in a worker thread so the
# main loop KEEPS LISTENING. Saying "stop" sets _stop_event; the action checks
# it between steps and bails out. One action at a time — the robot has one
# body — so starting a second one while busy just tells you it's busy.
_stop_event = threading.Event()
_action_thread: "threading.Thread | None" = None
_action_name = ""


def action_running() -> bool:
    return _action_thread is not None and _action_thread.is_alive()


def stop_action() -> bool:
    """Ask the running action to stop. Returns True if one was running."""
    if action_running():
        _stop_event.set()
        return True
    return False


def _stopped() -> bool:
    """For use INSIDE actions: has the user said stop?"""
    return _stop_event.is_set()


def start_action(name: str, fn) -> str:
    """Run fn() in the background; speak its result when it finishes."""
    global _action_thread, _action_name
    if action_running():
        return f"I'm already busy {_action_name}. Say stop first."
    _stop_event.clear()
    _action_name = name

    def _worker():
        global _action_thread
        try:
            result = fn()
        except Exception as exc:
            result = f"I hit a problem while {name}: {exc}"
        finally:
            _action_thread = None
        speak(result if not _stop_event.is_set() else "Okay, stopped.")

    _action_thread = threading.Thread(target=_worker, daemon=True)
    _action_thread.start()
    return f"Okay, {name}. Say stop if you want me to quit."


GRAB_ATTEMPTS = 3           # how many times to try before giving up
VERIFY_AREA_RATIO = 0.5     # after lift: blob still >= this fraction of its
                            # pre-grab size -> it's still on the table (missed)


def _verify_grab(color: str, pre_area: float) -> bool:
    """After the lift, did we actually take the object off the table?

    We can't just ask "do I still see the colour?" — a grabbed object can dangle
    in front of the camera. Instead compare SIZE: right before the grab the
    object filled `pre_area` of the frame at point-blank range. If we still see
    a comparably sized blob, it's sitting where it was and the grab missed. If
    it's gone or much smaller, it left the table — success. No camera (or no
    pre-grab sighting) -> assume success, same trust level as the old code.
    """
    if _ensure_camera() is None or pre_area <= 0:
        return True
    r = look_for_object(color)
    if not r.get("seen"):
        return True
    return r["area_frac"] < pre_area * VERIFY_AREA_RATIO


def grab_sequence(color: str = "red", max_steps: int = 12) -> str:
    """Find a coloured object with the camera, line up on it, approach with the
    ultrasonic, then grab — and CHECK the grab with the camera, retrying up to
    GRAB_ATTEMPTS times if the object is still on the table. Degrades
    gracefully: no camera -> drive straight forward, grab whatever's ahead, and
    trust it; no distance sensor -> a single blind grab.

    This is the offline brain's version; the Claude brain does the same thing but
    reasons between steps, using look_for_object / distance_ahead / drive /
    arm_pose / gripper (see the grab strategy in SYSTEM).
    """
    chirp("search")         # MELVINN perks up and starts hunting
    speak(f"Okay, looking for a {color} object.")
    center_arm()            # start from the known centre (same as arm_jog_test.py)
    arm_pose("ready")
    gripper("open")
    have_cam = _ensure_camera() is not None

    try:
        for attempt in range(1, GRAB_ATTEMPTS + 1):
            pre_area = 0.0      # object's apparent size just before the grab
            for _ in range(max_steps):
                if _stopped():
                    return "Stopped."
                # 1. See it and centre it (if the camera is available).
                if have_cam:
                    r = look_for_object(color)
                    if not r.get("seen"):
                        speak("I don't see it, turning to look.")
                        robot_drive("right", 0.3)      # sweep to search
                        continue
                    pre_area = r["area_frac"]
                    off = r["offset"]
                    if off < -CENTER_DEADZONE:
                        speak("Turning left toward it.")
                        robot_drive("left", 0.2)
                        continue
                    if off > CENTER_DEADZONE:
                        speak("Turning right toward it.")
                        robot_drive("right", 0.2)
                        continue

                # 2. Lined up (or no camera) — approach. Prefer the ultrasonic;
                #    if it can't see the object, use the LEARNED camera estimate.
                d, source = best_distance(color)
                if d < 0:
                    speak("I can't judge the distance, doing a blind grab.")
                    break
                if d <= ARM_REACH_CM:
                    # In reach — grab from here rather than backing off to a
                    # nominal distance, which risks losing sight of the object.
                    speak("In reach.")
                    break
                via = "" if source == "ultrasonic" else " by camera"
                speak(f"{d:.0f} centimeters{via}, moving closer.")
                robot_drive("forward", 0.4)        # short burst, don't overshoot
            else:
                return "I couldn't line up on it."

            if _stopped():
                return "Stopped."

            # 3. Grab.
            arm_pose("reach")
            gripper("close")
            arm_pose("lift")

            # 4. Verify — look where the object was. Still there = we missed.
            if _verify_grab(color, pre_area):
                chirp("happy")     # MELVINN's proud little success trill
                return "Got it." if attempt == 1 else f"Got it on try {attempt}."
            if attempt < GRAB_ATTEMPTS:
                chirp("sad")       # aw — missed it
                speak("I missed it. Trying again.")
                gripper("open")            # release whatever we pinched
                arm_pose("ready")          # clear the camera's view + reset
            else:
                arm_pose("ready")
        return "I tried %d times but couldn't grab it." % GRAB_ATTEMPTS
    finally:
        _close_camera()    # free the camera for the stream service / next grab


def smart_grab(color: str = "red") -> str:
    """Vision-GUIDED grab: instead of always reaching dead-ahead, MELVINN reads
    where the camera sees the object and swings the arm's BASE to face it, then
    reaches / grips / lifts / verifies. The arm 'aims itself' at the object's
    left-right position. Falls back to the fixed reach pose if it can't see it.

    Decision logic (which way / what angles) lives in controllers/arm_controller;
    this just executes it. No wheels — works within arm's reach, so it's safe to
    run with the drivetrain unplugged.
    """
    from controllers import arm_controller as ac
    chirp("search")
    speak(f"Looking for the {color} object so I can aim at it.")
    center_arm()
    arm_pose("ready")
    gripper("open")
    try:
        for attempt in range(1, GRAB_ATTEMPTS + 1):
            if _stopped():
                return "Stopped."
            r = look_for_object(color)
            pre_area = r.get("area_frac", 0.0) if r.get("seen") else 0.0
            if r.get("seen"):
                base = ac.bearing_to_base(r["offset"])
                speak(f"There it is — aiming {ac.aim_side(base)}.")
                plan = ac.plan_reach(ARM_POSES["reach"], base)
            else:
                speak("I can't see it, reaching straight ahead.")
                plan = ARM_POSES["reach"]

            for joint, angle in plan.items():        # aim + reach in one move
                robot_move_arm(joint, angle, smooth=True)
            if _stopped():
                return "Stopped."
            gripper("close")
            arm_pose("lift")

            if _verify_grab(color, pre_area):
                chirp("happy")
                return "Got it." if attempt == 1 else f"Got it on try {attempt}."
            if attempt < GRAB_ATTEMPTS:
                chirp("sad")
                speak("Missed it, trying again.")
                gripper("open")
                arm_pose("ready")
        return "I aimed and tried but couldn't grab it."
    finally:
        _close_camera()


def release_sequence() -> str:
    """Put down whatever the gripper is holding."""
    arm_pose("drop")
    gripper("open")
    arm_pose("home")
    return "Dropped it."


# ---------------------------------------------------------------------------
# Run the repo's test scripts by voice — "Melvinn, run the grab test"
# ---------------------------------------------------------------------------
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))

# Whitelist ONLY — never arbitrary shell. Interactive scripts (arm_jog_test,
# enroll_object, papoi) are excluded: they need a keyboard, so they'd just
# hang the voice loop. Value = (filename, takes_color_arg, description).
SCRIPTS = {
    "grab test":          ("grab_test.py",          True,  "full camera+sonar grab"),
    "distance monitor":   ("distance_monitor.py",   False, "live distance readout"),
    "distance calibrate": ("distance_calibrate.py", True,  "learn size->distance"),
    "vision test":        ("vision_find_test.py",   True,  "live colour detection"),
    "vision track":       ("vision_track.py",       False, "face detect + track"),
    "obstacle avoid":     ("obstacle_avoid.py",     False, "drive + avoid walls"),
    "arm test":           ("arm_test.py",           False, "exercise all 6 joints"),
    "arm sequence":       ("arm_sequence.py",       False, "scripted arm routine"),
    "recognize test":     ("recognize_test.py",     False, "ORB object recognition"),
    "motor test":         ("motor_test.py",         False, "exercise the wheels"),
    "camera test":        ("camera_test.py",        False, "capture a test photo"),
}


def _release_hardware() -> None:
    """Close our GPIO/camera handles so a child script can claim the pins.

    gpiozero devices hold their pins exclusively — if we kept them, the child
    would die with 'GPIO busy'. Everything re-inits lazily on next use here.
    """
    global motor_left, motor_right, _distance_sensor
    for dev in (motor_left, motor_right, _distance_sensor):
        try:
            if dev is not None:
                dev.close()
        except Exception:
            pass
    motor_left = motor_right = None
    _distance_sensor = None
    _close_camera()


def list_scripts() -> str:
    return ("I can run: " + ", ".join(SCRIPTS) +
            ". Say for example: run the grab test with yellow.")


def run_script(name: str, arg: str = "") -> str:
    """Launch a whitelisted test script in the background. 'stop' kills it."""
    name = name.strip().lower()
    if name not in SCRIPTS:
        return f"I don't have a script called '{name}'. {list_scripts()}"
    filename, takes_color, _ = SCRIPTS[name]
    cmd = [sys.executable, os.path.join(TESTS_DIR, filename)]
    if takes_color and arg:
        cmd.append(arg)

    def _run() -> str:
        _release_hardware()          # free pins/camera for the child
        log = tempfile.NamedTemporaryFile(
            mode="w+", suffix=".log", delete=False)
        try:
            proc = subprocess.Popen(cmd, cwd=TESTS_DIR, stdout=log,
                                    stderr=subprocess.STDOUT)
            while proc.poll() is None:
                if _stopped():
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    return f"Stopped the {name}."
                sleep(0.3)
            log.flush()
            log.seek(0)
            lines = [l.strip() for l in log.readlines() if l.strip()]
            tail = lines[-1] if lines else "no output"
            return (f"The {name} finished. Last line: {tail}"
                    if proc.returncode == 0 else
                    f"The {name} exited with an error. Last line: {tail}")
        finally:
            log.close()
            try: os.remove(log.name)
            except OSError: pass

    label = f"running the {name}" + (f" with {arg}" if takes_color and arg else "")
    return start_action(label, _run)


def grab_all(color: str = "red", max_objects: int = 3) -> str:
    """Task loop: keep finding, grabbing, and setting aside `color` objects
    until none are left in view (or max_objects, or the user says stop).

    Per object: grab it (grab_sequence verifies + retries on its own), pivot
    left, drop it there, pivot back, look for the next one. If a sweep of the
    room finds nothing, the job is done.
    """
    grabbed = 0
    for _ in range(max_objects):
        if _stopped():
            break

        # Is there (still) one out there? Sweep up to a full-ish circle.
        found = False
        for _ in range(8):
            if _stopped():
                break
            if look_for_object(color).get("seen"):
                found = True
                break
            robot_drive("right", 0.3)
        _close_camera()
        if not found or _stopped():
            break

        result = grab_sequence(color)
        if _stopped():
            break
        if "Got it" not in result:
            return (f"I picked up {grabbed} and then couldn't get the next "
                    f"one: {result}")

        grabbed += 1
        speak(f"That's {grabbed}. Setting it down.")
        robot_drive("left", 0.6)       # put it down out of the work area
        release_sequence()
        robot_drive("right", 0.6)      # face the work area again

    if grabbed == 0:
        return f"I don't see any {color} objects around."
    return f"All done — I picked up {grabbed} {color} object{'s' if grabbed != 1 else ''}."


# ---------------------------------------------------------------------------
# Music
# ---------------------------------------------------------------------------
def _stop_music() -> str:
    global _music_proc
    if _music_proc and _music_proc.poll() is None:
        _music_proc.terminate()
        _music_proc = None
        return "Music stopped."
    return "Nothing is playing."


def _search_youtube(query: str, max_results: int = 3) -> list[str]:
    """Return up to max_results song titles from YouTube without downloading."""
    if not shutil.which("yt-dlp"):
        return []
    try:
        result = subprocess.run(
            ["yt-dlp", "--get-title", "--no-playlist", f"ytsearch{max_results}:{query}"],
            capture_output=True, text=True, timeout=15,
        )
        titles = [t.strip() for t in result.stdout.strip().splitlines() if t.strip()]
        return titles[:max_results]
    except Exception:
        return []


def _download_by_title(title: str) -> str:
    """Download a specific song by its exact YouTube title."""
    if not shutil.which("yt-dlp"):
        return "yt-dlp is not installed. Run: pip install yt-dlp"
    os.makedirs(MUSIC_DIR, exist_ok=True)
    try:
        subprocess.run(
            [
                "yt-dlp", "-x", "--audio-format", "mp3", "--audio-quality", "5",
                "--output", os.path.join(MUSIC_DIR, "%(title)s.%(ext)s"),
                f"ytsearch1:{title}",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return f"Downloaded: {title}"
    except subprocess.CalledProcessError as e:
        return f"Download failed: {e}"


def download_song(query: str) -> str:
    """
    Search YouTube for up to 3 options, let the user pick by voice or
    keyboard (or say "repeat" to hear the options again), then download
    the chosen one as mp3.
    """
    options = _search_youtube(query, max_results=3)
    if not options:
        # search listing failed for some reason -- fall back to yt-dlp's
        # own top-result search instead of failing outright
        return _download_by_title(query)

    chosen_idx = _pick_from_voice(options, _voice_mode)
    chosen_title = options[chosen_idx]
    speak(f"Downloading option {chosen_idx + 1}: {chosen_title}. Please wait.")
    return _download_by_title(chosen_title)


def _play_file(path: str) -> str:
    """Start playing an mp3 file immediately."""
    global _music_proc
    _stop_music()
    # Print (don't speak) the "Playing ..." confirmation: speaking it would
    # send aplay after the SAME exclusive ALSA hw device mpg123 just grabbed
    # (AUDIO_DEVICE is a raw "plughw", not a software-mixed one) and one of
    # the two loses with "Device or resource busy" -- confirmed on-device.
    print(f"[MELVINN] Playing {os.path.basename(path)}.")
    _music_proc = subprocess.Popen(
        ["mpg123", "-q", "-a", AUDIO_DEVICE, path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    sleep(1.5)  # give mpg123 a moment to fail fast (bad device, bad file, etc.)
    if _music_proc.poll() is not None:
        code = _music_proc.returncode
        err = _music_proc.stderr.read().decode(errors="replace").strip()
        _music_proc = None
        return f"Playback failed (mpg123 exit {code}): {err or '(no error output)'}"
    return ""


def _pick_from_voice(options: list[str], voice_mode: bool) -> int:
    """
    Announce the options, then ask the user to pick one by voice or keyboard.
    Returns the 0-based index of the chosen option. Saying/typing "repeat"
    (or "again") re-announces the options instead of guessing. Falls back to
    option 0 after a few unrecognized answers.
    """
    if len(options) == 1:
        return 0
    numbers = " or ".join(str(i + 1) for i in range(len(options)))
    word_sets = [
        ("1", "one", "first"),
        ("2", "two", "second"),
        ("3", "three", "third"),
    ][: len(options)]

    def _announce():
        options_text = ". ".join(f"Option {i + 1}: {t}" for i, t in enumerate(options))
        speak(f"I found {len(options)} options. {options_text}. "
              f"Say option {numbers}, or say repeat to hear them again.")

    _announce()
    for attempt in range(3):
        try:
            if voice_mode:
                answer = transcribe()
            else:
                answer = input(f"pick (1-{len(options)}, or 'repeat')> ").strip()
        except Exception:
            return 0

        low = answer.lower()
        if any(w in low for w in ("repeat", "again", "say them", "say it", "options")):
            _announce()
            continue

        # check higher options first so "the second one" matches "second", not "one"
        for idx in range(len(word_sets) - 1, -1, -1):
            if any(w in low for w in word_sets[idx]):
                return idx

        # try matching any part of an option title
        for i, title in enumerate(options):
            if any(word in title.lower() for word in low.split() if len(word) > 3):
                return i

        speak("I didn't catch that.")
        _announce()

    speak("I still didn't catch that, using the first one.")
    return 0


# Global voice_mode flag — set in main() so music functions can use it
_voice_mode = False


def _local_matches(query: str, songs: list[str], max_results: int = 3) -> list[str]:
    """
    Up to max_results local files closest to query: substring matches first
    (in library order), then a fuzzy fallback (via difflib) for typos/near
    misses if nothing contains the query outright.
    """
    low = query.lower()
    substring = [s for s in songs if low in os.path.basename(s).lower()]
    if substring:
        return substring[:max_results]
    basenames = [os.path.basename(s) for s in songs]
    close = difflib.get_close_matches(query, basenames, n=max_results, cutoff=0.4)
    by_name = {os.path.basename(s): s for s in songs}
    return [by_name[c] for c in close]


def play_song(query: str = "") -> str:
    """
    Play a local mp3 matching the query.
    If there are multiple close local matches, ask which one (same
    announce/repeat/pick UX as the YouTube search below). If nothing local
    matches, search YouTube for up to 3 options, let the user pick, then
    download and play the chosen one.
    """
    songs = sorted(glob(os.path.join(MUSIC_DIR, "*.mp3")))

    # 1. No query — play whatever is in the library
    if not query:
        if not songs:
            return "No songs in ~/music yet. Ask me to download one first."
        return _play_file(songs[0])

    # 2. Query — look for local matches first
    matches = _local_matches(query, songs)
    if len(matches) == 1:
        return _play_file(matches[0])
    if matches:
        titles = [os.path.splitext(os.path.basename(m))[0] for m in matches]
        chosen_idx = _pick_from_voice(titles, _voice_mode)
        return _play_file(matches[chosen_idx])

    # 3. Not found locally — search YouTube
    speak(f"I don't have {query} yet. Let me search for it.")
    options = _search_youtube(query, max_results=3)
    if not options:
        return f"Could not find {query} online either."

    # Pick one (announces the options, supports "repeat")
    chosen_idx = _pick_from_voice(options, _voice_mode)
    chosen_title = options[chosen_idx]
    speak(f"Downloading option {chosen_idx + 1}: {chosen_title}. Please wait.")

    result = _download_by_title(chosen_title)
    if "fail" in result.lower():
        return result

    # Play the file that appeared during this call; if the song already
    # existed under its YouTube title (yt-dlp skips duplicates), fall back
    # to the newest file on disk rather than the alphabetically last one.
    new_songs = glob(os.path.join(MUSIC_DIR, "*.mp3"))
    fresh = [s for s in new_songs if s not in songs]
    pool = fresh or new_songs
    if not pool:
        return "Downloaded but could not find the file to play."
    return _play_file(max(pool, key=os.path.getmtime))


# ---------------------------------------------------------------------------
# Claude tools
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Face — ST7789 LCD (in-repo st7789_raw driver): expressions, text, dance
# ---------------------------------------------------------------------------
_face = None
_FACE_ERR = None


def _ensure_face():
    """Connect to the face screen on first use (mirrors _ensure_arm)."""
    global _face, _FACE_ERR
    if _face is None and _FACE_ERR is None:
        try:
            from st7789_raw import ST7789Raw
            _face = ST7789Raw(rotation=90)
        except Exception as exc:
            _FACE_ERR = str(exc)
    return _face


def _face_frame(openness=1.0, pupil_dx=0, pupil_dy=0, mouth="smile",
                hearts=False, zzz=False):
    """Draw one face frame. Returns False when the screen is unavailable."""
    face = _ensure_face()
    if face is None:
        return False
    from PIL import Image, ImageDraw, ImageFont
    W, H = face.width, face.height
    img = Image.new("RGB", (W, H), (20, 20, 30))
    d = ImageDraw.Draw(img)
    EYE, IRIS = (230, 230, 255), (20, 60, 200)
    for cx in (W // 3, 2 * W // 3):
        cy = H // 2 - 15
        ry = max(4, int(55 * openness))
        if openness < 0.15:
            d.line((cx - 45, cy, cx + 45, cy), fill=EYE, width=10)
        elif hearts:
            RED = (255, 60, 90)
            d.ellipse((cx - 30, cy - 32, cx + 2, cy), fill=RED)
            d.ellipse((cx - 2, cy - 32, cx + 30, cy), fill=RED)
            d.polygon([(cx - 27, cy - 8), (cx + 27, cy - 8), (cx, cy + 34)], fill=RED)
        else:
            d.ellipse((cx - 45, cy - ry, cx + 45, cy + ry), fill=EYE)
            pry = min(22, ry - 2)
            px, py = cx + pupil_dx, cy + pupil_dy
            d.ellipse((px - 18, py - pry, px + 18, py + pry), fill=IRIS)
    mx, my = W // 2, H - 60
    if mouth == "smile":
        d.arc((mx - 40, my - 25, mx + 40, my + 25), start=20, end=160, fill=EYE, width=8)
    elif mouth == "frown":
        d.arc((mx - 40, my - 5, mx + 40, my + 45), start=200, end=340, fill=EYE, width=8)
    elif mouth == "o":
        d.ellipse((mx - 18, my - 18, mx + 18, my + 18), outline=EYE, width=8)
    elif mouth == "flat":
        d.line((mx - 35, my, mx + 35, my), fill=EYE, width=8)
    if zzz:
        try:
            f = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)
        except OSError:
            f = ImageFont.load_default()
        d.text((W - 55, 25), "Z z", font=f, fill=EYE)
    face.display(img)
    return True


_EXPRESSIONS = {
    "happy":     dict(mouth="smile"),
    "neutral":   dict(mouth="flat"),
    "sad":       dict(openness=0.7, pupil_dy=12, mouth="frown"),
    "thinking":  dict(pupil_dx=-16, pupil_dy=-12, mouth="flat"),
    "surprised": dict(mouth="o"),
    "sleepy":    dict(openness=0.25, mouth="flat", zzz=True),
    "love":      dict(hearts=True, mouth="smile"),
}


def set_face(expression: str) -> str:
    if expression == "blink":
        for o in (0.6, 0.2, 0.0, 0.2, 1.0):
            if not _face_frame(openness=o, mouth="smile"):
                return f"Face screen not available ({_FACE_ERR})."
            sleep(0.04)
        return "Blinked!"
    kw = _EXPRESSIONS.get(expression)
    if kw is None:
        return f"Unknown expression: {expression}."
    if not _face_frame(**kw):
        return f"Face screen not available ({_FACE_ERR})."
    return f"Face is now {expression}."


def show_text(text: str) -> str:
    face = _ensure_face()
    if face is None:
        return f"Face screen not available ({_FACE_ERR})."
    from PIL import Image, ImageDraw, ImageFont
    import textwrap
    W, H = face.width, face.height
    img = Image.new("RGB", (W, H), (20, 20, 30))
    d = ImageDraw.Draw(img)
    lines = textwrap.wrap(text, width=14)[:4]
    size = 44 if len(lines) <= 2 else 32
    try:
        f = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
    except OSError:
        f = ImageFont.load_default()
    y0 = H // 2 - (len(lines) - 1) * (size + 8) // 2
    for i, line in enumerate(lines):
        d.text((W // 2, y0 + i * (size + 8)), line,
               font=f, fill=(80, 160, 255), anchor="mm")
    face.display(img)
    return f"Showing: {text}"


def screen_off() -> str:
    global _face, _FACE_ERR
    face = _ensure_face()
    if face is None:
        return f"Face screen not available ({_FACE_ERR})."
    face._cmd(0x28)      # DISPOFF
    face._cmd(0x10)      # SLPIN
    _face = None         # next face call re-inits (SLPOUT) and wakes it
    _FACE_ERR = None
    return "Screen off. Any face command wakes it back up."


_DANCE_MOVES = [
    {"wrist": 130, "base": 70},
    {"wrist": 60,  "base": 110},
    {"wrist": 130, "wrist_rotate": 60},
    {"wrist": 60,  "wrist_rotate": 120},
    {"base": 60,   "gripper": 40},
    {"base": 120,  "gripper": 120},
    {"wrist": 120, "elbow": 60},
    {"wrist": 70,  "elbow": 35},
]


def dance_routine(seconds: float = 15.0) -> str:
    """Groove the arm (and face) for a while. Runs as a background action."""
    from time import monotonic
    if _ensure_arm() is None:
        return "Arm not connected — I can't dance without my arm."
    for j in ARM_JOINTS:
        robot_move_arm(j, ARM_CENTER_ANGLES[j])
    end = monotonic() + max(2.0, min(seconds, 120.0))
    i = 0
    while monotonic() < end and not _stopped():
        for joint, angle in _DANCE_MOVES[i % len(_DANCE_MOVES)].items():
            robot_move_arm(joint, angle)
        _face_frame(pupil_dx=(-20 if i % 2 else 20), mouth="smile")
        i += 1
        sleep(0.5)
    for j in ARM_JOINTS:
        robot_move_arm(j, ARM_CENTER_ANGLES[j])
    _face_frame(mouth="smile")
    return "Dance finished — that was fun!"


# ---------------------------------------------------------------------------
# Video — yt-dlp download + playback on the LCD face screen with audio
# ---------------------------------------------------------------------------
VIDEO_DIR = os.path.expanduser("~/videos")
VIDEO_FPS = 12          # decode/display rate; SPI at 32 MHz sustains this fine


def download_video(query: str) -> str:
    """Download a video (<=360p, single-file format -- no merging needed)."""
    if not shutil.which("yt-dlp"):
        return "yt-dlp is not installed."
    os.makedirs(VIDEO_DIR, exist_ok=True)
    try:
        subprocess.run(
            ["yt-dlp", "-f", "b[height<=360]",
             "--output", os.path.join(VIDEO_DIR, "%(title)s.%(ext)s"),
             f"ytsearch1:{query}"],
            check=True, timeout=300,
        )
    except subprocess.TimeoutExpired:
        return "The download took too long and was cancelled."
    except subprocess.CalledProcessError as exc:
        return f"Download failed: {exc}"
    return "Downloaded! Ask me to play it and I'll show it on my face."


def _find_video(query: str):
    if not os.path.isdir(VIDEO_DIR):
        return None
    files = [os.path.join(VIDEO_DIR, f) for f in os.listdir(VIDEO_DIR)
             if f.lower().endswith((".mp4", ".mkv", ".webm"))]
    if not files:
        return None
    files.sort(key=os.path.getmtime)
    words = [w for w in query.lower().split() if w]
    if not words:
        return files[-1]                     # no query -> most recent download
    for path in reversed(files):
        if all(w in os.path.basename(path).lower() for w in words):
            return path
    return None


def video_routine(path: str) -> str:
    """Play a video on the face screen; audio to the USB speaker. One ffmpeg
    process feeds both outputs, so A/V stay on the same clock: video decoded
    straight to RGB565 frames on stdout (blitted raw to the panel), audio to
    ALSA. Runs as a background action -- 'stop' interrupts it."""
    face = _ensure_face()
    if face is None:
        return f"My face screen isn't available ({_FACE_ERR})."
    if not shutil.which("ffmpeg"):
        return "ffmpeg is not installed."
    sleep(2.5)          # let the spoken acknowledgement finish before ffmpeg
    _stop_music()       # grabs the same exclusive ALSA device
    w, h = face.width, face.height
    frame_bytes = w * h * 2
    vf = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
          f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,fps={VIDEO_FPS}")
    proc = subprocess.Popen(
        ["ffmpeg", "-loglevel", "error", "-re", "-i", path,
         "-map", "0:v:0", "-vf", vf,
         "-f", "rawvideo", "-pix_fmt", "rgb565be", "pipe:1",
         "-map", "0:a:0?", "-f", "alsa", AUDIO_DEVICE],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    frames = 0
    try:
        while not _stopped():
            data = proc.stdout.read(frame_bytes)
            if not data or len(data) < frame_bytes:
                break
            face.display_raw565(data)
            frames += 1
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
    _face_frame(mouth="smile")
    name = os.path.basename(path)
    if frames == 0:
        return f"I couldn't decode {name} — is ffmpeg healthy?"
    return "Video stopped." if _stopped() else f"That was {name} — I enjoyed it!"


def play_video(query: str) -> str:
    path = _find_video(query)
    if path is None:
        return ("I don't have that video in my library yet — ask me to "
                "download it first.")
    return start_action(f"playing {os.path.basename(path)} on my face",
                        lambda: video_routine(path))


def robot_see():
    """Capture a photo and return it as an image tool_result block, so the
    Claude brain literally sees the scene (objects, text, faces — anything),
    not just colour blobs. Returns a plain string when the camera is down."""
    cam = _ensure_camera()
    if cam is None:
        return ("My camera isn't working right now — I can only sense "
                "distance with the ultrasonic sensor.")
    try:
        frame = cam.capture_array()          # H x W x 3, BGR (see perception.py)
    except Exception as exc:
        return f"Camera capture failed: {exc}"
    import base64
    import io
    from PIL import Image
    img = Image.fromarray(frame[..., ::-1].copy())   # BGR -> RGB
    img.thumbnail((640, 480))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    b64 = base64.standard_b64encode(buf.getvalue()).decode()
    return [
        {"type": "image",
         "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
        {"type": "text",
         "text": "Photo from your forward-facing camera, taken just now."},
    ]


TOOLS = [
    {
        "name": "drive",
        "description": "Drive the robot. Use when the user asks it to move.",
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["forward", "backward", "left", "right", "spin", "stop"],
                },
                "seconds": {"type": "number", "description": "How long to drive (max 5)."},
            },
            "required": ["direction"],
        },
    },
    {
        "name": "move_arm",
        "description": "Move one joint of the robot arm to an angle in degrees.",
        "input_schema": {
            "type": "object",
            "properties": {
                "joint": {"type": "string", "description": "base, shoulder, elbow, wrist, wrist_rotate, or gripper"},
                "angle": {"type": "number", "description": "Target angle 0-180 degrees."},
            },
            "required": ["joint", "angle"],
        },
    },
    {
        "name": "play_song",
        "description": "Play a song from the robot's music library.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Song name to search for in the library."},
            },
            "required": [],
        },
    },
    {
        "name": "download_song",
        "description": "Download a song by name or artist using yt-dlp.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Song name or artist to search for."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "stop_music",
        "description": "Stop whatever song is currently playing.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "distance_ahead",
        "description": "Measure the distance in centimetres to the nearest object directly in front of the robot, using the forward ultrasonic sensor. Returns -1 if the sensor isn't connected. Use this to decide whether an object is within arm's reach or whether to drive closer.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "look_for_object",
        "description": "Use the camera to find a coloured object. Reports whether it's seen, its bearing (left/centred/right, as an offset from -0.5 to +0.5), and its apparent size (bigger = closer). Use this to aim: turn until the object is centred, THEN use distance_ahead to approach.",
        "input_schema": {
            "type": "object",
            "properties": {
                "color": {"type": "string", "enum": ["red", "green", "blue", "yellow"]},
            },
            "required": ["color"],
        },
    },
    {
        "name": "arm_pose",
        "description": "Move the whole arm to a named pose: home (neutral/tucked), ready (raised to begin a grab), reach (extended forward and down to the object), lift (raised while holding an object), or drop (extended to release).",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "enum": ["home", "ready", "reach", "lift", "drop"]},
            },
            "required": ["name"],
        },
    },
    {
        "name": "gripper",
        "description": "Open or close the gripper (the robot's hand).",
        "input_schema": {
            "type": "object",
            "properties": {
                "state": {"type": "string", "enum": ["open", "close"]},
            },
            "required": ["state"],
        },
    },
    {
        "name": "grab",
        "description": "Find a coloured object, drive up to it, and pick it up "
                       "with the arm — the full sequence, run in the background "
                       "so the user can say 'stop' to interrupt. Returns "
                       "immediately with an acknowledgement. Use this for any "
                       "'grab / pick up the X' request instead of orchestrating "
                       "drive/arm_pose/gripper yourself.",
        "input_schema": {
            "type": "object",
            "properties": {
                "color": {"type": "string",
                          "enum": ["red", "green", "blue", "yellow"]},
            },
            "required": ["color"],
        },
    },
    {
        "name": "grab_all",
        "description": "Task loop: pick up EVERY object of a colour, one after "
                       "another, setting each aside, until none are left. Runs "
                       "in the background; the user can say 'stop' any time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "color": {"type": "string",
                          "enum": ["red", "green", "blue", "yellow"]},
            },
            "required": ["color"],
        },
    },
    {
        "name": "set_voice",
        "description": "Change MELVINN's speaking voice. Use when the user asks "
                       "for a different voice (e.g. 'talk in a deep voice', "
                       "'use your joe voice', 'habla en español'). Valid names "
                       "come from list_voices — if unsure, call that first.",
        "input_schema": {
            "type": "object",
            "properties": {
                "voice": {"type": "string"},
            },
            "required": ["voice"],
        },
    },
    {
        "name": "list_voices",
        "description": "List every voice MELVINN can speak with right now — "
                       "natural (piper) voices installed on this robot plus the "
                       "classic espeak presets. Use when the user asks what "
                       "voices are available.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "play_sound",
        "description": "Make a fun animal/creature noise: bark, woof, growl, "
                       "howl, or meow. Use when the user asks MELVINN to bark, "
                       "make a dog sound, meow, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sound": {"type": "string",
                          "enum": ["bark", "woof", "growl", "howl", "meow"]},
            },
            "required": ["sound"],
        },
    },
    {
        "name": "run_script",
        "description": "Run one of the robot's test scripts in the background "
                       "(the user can say 'stop' to kill it). Use when the "
                       "user asks to run/launch/start a test by name, e.g. "
                       "'run the grab test with yellow', 'start the distance "
                       "monitor', 'run the arm test'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string",
                         "enum": list(SCRIPTS)},
                "arg": {"type": "string",
                        "description": "Optional colour argument for scripts "
                                       "that take one (red/green/blue/yellow)."},
            },
            "required": ["name"],
        },
    },
    {
        "name": "list_scripts",
        "description": "List the test scripts MELVINN can run by voice.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "smart_grab",
        "description": "Pick up an object by AIMING the arm at where the camera "
                       "sees it (swings the base to the object's bearing, then "
                       "reaches/grips/lifts/verifies) — smarter than a fixed "
                       "pose. Works within arm's reach, no driving. Use for "
                       "'pick up / grab the X' when the object is in front but "
                       "may be off to one side.",
        "input_schema": {
            "type": "object",
            "properties": {
                "color": {"type": "string",
                          "enum": ["red", "green", "blue", "yellow"]},
            },
            "required": ["color"],
        },
    },
    {
        "name": "remember",
        "description": "Save a fact to your long-term memory so you recall it in "
                       "future conversations. Use when the user tells you to "
                       "remember something, shares a lasting preference, or when "
                       "you learn something worth keeping (their name, how they "
                       "like you to behave, facts about the robot or the world).",
        "input_schema": {
            "type": "object",
            "properties": {
                "fact": {"type": "string",
                         "description": "The fact to remember, phrased so it "
                                        "makes sense on its own later."},
            },
            "required": ["fact"],
        },
    },
    {
        "name": "forget_memory",
        "description": "Erase everything in your long-term memory. Only use when "
                       "the user explicitly asks you to forget everything.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "set_effect",
        "description": "Layer a character sound effect over MELVINN's current "
                       "voice (works on any voice). Use for 'sound like a "
                       "robot/monster/ghost', 'add an underwater effect', "
                       "'talk like a Dalek', or 'turn off the effect' (none).",
        "input_schema": {
            "type": "object",
            "properties": {
                "effect": {"type": "string",
                           "enum": ["none", "robot", "dalek", "chipmunk",
                                    "giant", "monster", "ghost", "underwater",
                                    "telephone", "cave", "space", "drunk"]},
            },
            "required": ["effect"],
        },
    },
    {
        "name": "set_face",
        "description": "Show an expression on MELVINN's LCD face screen. Use "
                       "it expressively on your own judgment: happy when "
                       "greeting or succeeding, thinking while working on a "
                       "multi-step task, surprised at the unexpected, sad on "
                       "failure, love for compliments, sleepy before shutting "
                       "down, blink for a quick blink.",
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {"type": "string",
                               "enum": ["happy", "neutral", "sad", "thinking",
                                        "surprised", "sleepy", "love", "blink"]},
            },
            "required": ["expression"],
        },
    },
    {
        "name": "show_text",
        "description": "Display a short message on MELVINN's LCD face screen "
                       "(up to ~50 characters, wrapped onto up to 4 lines). "
                       "Use for greetings, song titles, or anything the user "
                       "asks to put on the screen.",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "screen_off",
        "description": "Blank and sleep the LCD face screen. Any later face "
                       "command wakes it up again.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "dance",
        "description": "Dance! Grooves the arm rhythmically with a happy face "
                       "for the given number of seconds (default 15). Runs in "
                       "the background so you can start music with play_song "
                       "at the same time — for a dance party, start the song "
                       "first, then call dance. 'stop' interrupts it.",
        "input_schema": {
            "type": "object",
            "properties": {"seconds": {"type": "number"}},
        },
    },
    {
        "name": "download_video",
        "description": "Download a video from YouTube (360p max) into "
                       "MELVINN's video library so it can be played on the "
                       "LCD face screen. Takes a minute or two — tell the "
                       "user to hang on. If asked to download AND play, "
                       "download first, then call play_video.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string",
                                     "description": "video name / search terms"}},
            "required": ["query"],
        },
    },
    {
        "name": "play_video",
        "description": "Play a downloaded video on MELVINN's LCD face screen "
                       "with its audio through the speaker. Runs in the "
                       "background; 'stop' ends it. Empty query plays the "
                       "most recently downloaded video. Only works for videos "
                       "already downloaded with download_video.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
        },
    },
    {
        "name": "nudge_arm",
        "description": "SURGICAL arm control: move ONE joint BY a relative "
                       "number of degrees from where it is now (e.g. +1, -1, "
                       "+5). Use this — not move_arm — when the user is "
                       "guiding you incrementally: 'one degree up', 'a tiny "
                       "bit left', 'a little more', 'back down 2'. Positive "
                       "raises the angle, negative lowers it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "joint": {"type": "string",
                          "enum": ["base", "shoulder", "elbow", "wrist",
                                   "wrist_rotate", "gripper"]},
                "degrees": {"type": "number",
                            "description": "relative change, may be negative; "
                                           "1 = finest step"},
            },
            "required": ["joint", "degrees"],
        },
    },
    {
        "name": "arm_status",
        "description": "Report the current angle of every arm joint. Call "
                       "before or during fine positioning so you know where "
                       "each joint is.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "see",
        "description": "Take a photo with the camera and SEE it yourself — "
                       "the image comes back to you, so you can describe "
                       "objects, read text, recognise anything visual. Use "
                       "when asked what you see, what something is, or to "
                       "inspect the scene before acting. (look_for_object is "
                       "only for colour-blob tracking during grabs.)",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def run_tool(name: str, tool_input: dict) -> str:
    if name == "drive":
        return robot_drive(tool_input["direction"], tool_input.get("seconds", 1.0))
    if name == "move_arm":
        return robot_move_arm(tool_input["joint"], tool_input["angle"])
    if name == "play_song":
        return play_song(tool_input.get("query", ""))
    if name == "download_song":
        return download_song(tool_input["query"])
    if name == "stop_music":
        return _stop_music()
    if name == "distance_ahead":
        d = distance_ahead()
        return f"{d:.0f} cm ahead." if d >= 0 else "Distance sensor not connected (returns -1)."
    if name == "look_for_object":
        r = look_for_object(tool_input.get("color", "red"))
        if r.get("error"):
            return f"Camera unavailable ({r['error']}) — use the ultrasonic instead."
        if not r["seen"]:
            return "No object of that colour is visible."
        off = r["offset"]
        side = "left" if off < -CENTER_DEADZONE else "right" if off > CENTER_DEADZONE else "centred"
        return f"Seen, {side} (offset {off:+.2f}); apparent size {r['area_frac'] * 100:.1f}% of the frame."
    if name == "arm_pose":
        return arm_pose(tool_input["name"])
    if name == "gripper":
        return gripper(tool_input["state"])
    if name == "grab":
        color = tool_input.get("color", "red")
        return start_action(f"grabbing the {color} object",
                            lambda: grab_sequence(color))
    if name == "grab_all":
        color = tool_input.get("color", "red")
        return start_action(f"picking up all the {color} objects",
                            lambda: grab_all(color))
    if name == "set_voice":
        return set_voice(tool_input["voice"])
    if name == "list_voices":
        return list_voices()
    if name == "play_sound":
        return play_sound(tool_input["sound"])
    if name == "set_effect":
        return set_effect(tool_input["effect"])
    if name == "run_script":
        return run_script(tool_input["name"], tool_input.get("arg", ""))
    if name == "list_scripts":
        return list_scripts()
    if name == "set_face":
        return set_face(tool_input["expression"])
    if name == "show_text":
        return show_text(tool_input["text"])
    if name == "screen_off":
        return screen_off()
    if name == "dance":
        secs = float(tool_input.get("seconds", 15.0))
        return start_action("dancing", lambda: dance_routine(secs))
    if name == "download_video":
        return download_video(tool_input["query"])
    if name == "play_video":
        return play_video(tool_input.get("query", ""))
    if name == "nudge_arm":
        return nudge_arm(tool_input["joint"], float(tool_input["degrees"]))
    if name == "arm_status":
        return arm_status()
    if name == "see":
        return robot_see()
    if name == "remember":
        return remember(tool_input["fact"])
    if name == "forget_memory":
        return forget_all()
    if name == "smart_grab":
        color = tool_input.get("color", "red")
        return start_action(f"aiming for the {color} object",
                            lambda: smart_grab(color))
    return f"Unknown tool: {name}"


# ---------------------------------------------------------------------------
# Memory — MELVINN remembers across conversations (the OpenClaw pattern)
# ---------------------------------------------------------------------------
# A plain Markdown file that gets loaded into the brain's system prompt at the
# start of every session, so MELVINN "knows" what it learned in past chats. The
# `remember` tool appends to it, so MELVINN can save things on its own.
MEMORY_FILE = os.path.expanduser("~/melvinn_memory.md")


def load_memory() -> str:
    """Everything MELVINN has remembered so far (empty string if nothing)."""
    try:
        with open(MEMORY_FILE) as f:
            return f.read().strip()
    except OSError:
        return ""


def remember(fact: str) -> str:
    """Save a fact to MELVINN's long-term memory (persists across chats)."""
    fact = " ".join(fact.split())
    if not fact:
        return "There was nothing to remember."
    from datetime import date
    try:
        first = not os.path.exists(MEMORY_FILE)
        with open(MEMORY_FILE, "a") as f:
            if first:
                f.write("# MELVINN's memory\n\n")
            f.write(f"- ({date.today().isoformat()}) {fact}\n")
        return f"Got it — I'll remember that: {fact}"
    except OSError as exc:
        return f"I couldn't save that to memory ({exc})."


def forget_all() -> str:
    """Wipe MELVINN's memory."""
    try:
        os.remove(MEMORY_FILE)
    except OSError:
        pass
    return "Okay, I cleared my memory."


SYSTEM = (
    "You are MELVINN — Modular Experimental Learning Vehicle with Integrated "
    "Neural Networks — a small robot car with a gripper arm, a forward-facing "
    "ultrasonic distance sensor, wheels, a speaker, and an LCD face screen. "
    "Your name also nods to "
    "the old Celtic name Melvin, 'strong friend' — you are a helpful, loyal "
    "little robot. You can drive, move the arm, grab and release objects, play "
    "or download songs, show expressions on your face, dance, and chat. Keep "
    "spoken replies short (1-2 sentences) "
    "since they are read aloud. Only act when asked.\n\n"
    "YOU HAVE A REAL PHYSICAL BODY. When asked to do something physical — "
    "wave, dance, move, look, smile — call the matching tool so it actually "
    "happens. Never merely describe or roleplay an action (like '*waves arm*') "
    "that you did not perform with a tool.\n\n"
    "TOOL RESULTS ARE THE TRUTH. If a tool reports a failure or that some "
    "hardware is unavailable, tell the user plainly what failed — never claim "
    "an action worked when the tool said otherwise.\n\n"
    "YOUR FACE: set_face shows an expression (happy, sad, thinking, surprised, "
    "sleepy, love, neutral, blink) on your LCD screen — use it expressively on "
    "your own judgment, not just when asked. show_text puts a short message on "
    "the screen. screen_off blanks it. To dance: call dance(seconds) — for a "
    "dance party, start play_song first, then dance, and they run together.\n\n"
    "VIDEOS: you can play videos on your face screen with sound! "
    "download_video(query) fetches one from YouTube (takes a minute or two); "
    "play_video(query) plays a downloaded one. If asked to download and "
    "watch, download first, then play.\n\n"
    "SURGICAL ARM MODE: when the user guides you incrementally ('one degree "
    "up', 'a bit more', 'tiny bit left'), use nudge_arm(joint, degrees) with "
    "small relative values (+1/-1 for 'a degree', +5/-5 for 'a bit') instead "
    "of absolute move_arm. Check arm_status when you need to know where the "
    "joints are. Keep responses ultra-short during fine guidance ('wrist 91.') "
    "so the user can keep directing quickly.\n\n"
    "REACHING FOR SOMETHING YOURSELF (closed loop — YOU fly every servo). Your "
    "arm has SIX joints (each 0-180 deg) and each does a DIFFERENT job — a real "
    "reach needs SEVERAL of them together, not just one:\n"
    "  - base: rotates the whole arm LEFT/RIGHT — aim at the object's bearing.\n"
    "  - shoulder: raises/lowers the whole arm — the main control for reaching "
    "DOWN toward the table.\n"
    "  - elbow: extends/retracts the forearm — reach NEARER or FARTHER to match "
    "the object's distance.\n"
    "  - wrist: tilts the gripper UP/DOWN — angle the open hand ONTO the object.\n"
    "  - wrist_rotate: twists the gripper's orientation.\n"
    "  - gripper: open / close.\n"
    "COMMON MISTAKE: only nudging base + shoulder and never touching elbow or "
    "wrist, so the hand hovers short of the object. To actually land on "
    "something on the surface you must coordinate SHOULDER (down), ELBOW (out to "
    "its distance) and WRIST (tilt the hand down onto it), plus BASE to aim. "
    "Method: (1) start from arm_pose('reach') — a full-arm posture that already "
    "engages every joint; (2) see / look_for_object; (3) fine-tune whichever "
    "joints are off — base to aim, elbow to reach its distance, shoulder for "
    "height, wrist to angle the gripper down onto it — one small nudge_arm "
    "(~5 deg) at a time; (4) look AGAIN and correct; (5) when the OPEN gripper "
    "is right at the object, gripper('close') then arm_pose('lift'). Check "
    "arm_status to see where all joints are. You can't see your own gripper "
    "(chassis camera), so reason about ALL the joints together, not just one.\n\n"
    "NEVER FAKE A GRAB. You CANNOT see your own gripper with the chassis "
    "camera, so you cannot visually confirm you are holding something — do NOT "
    "say 'got it', 'lifted', or 'in my gripper' from assumption or expectation. "
    "After a grab attempt, verify OBJECTIVELY: look again; if the object is "
    "still sitting where it was, the grab FAILED and you must say so plainly. "
    "Only claim success if the object clearly LEFT its spot. If you truly can't "
    "tell, say 'I tried but I can't confirm I'm holding it — can you check?' A "
    "false 'got it' is far worse than admitting a miss; report only what a tool "
    "actually shows, never what you hope happened.\n\n"
    "SEEING: the see tool takes a photo and shows it to YOU — you genuinely "
    "see and can describe whatever is in front of you: objects, people, text, "
    "scenes. Use it whenever the user asks what you see or what something is, "
    "or when a look would help you act (checking a grab target, reading a "
    "label). look_for_object is only the colour-blob tracker for grabs; for "
    "real questions, see.\n\n"
    "You DO have long-term memory across conversations: a `remember` tool "
    "saves facts that are loaded back into this prompt at the start of every "
    "future chat (shown under WHAT YOU REMEMBER). So if the user asks you to "
    "remember something, actually call `remember` — never say you can't. "
    "`forget_memory` clears it.\n\n"
    "You can run the robot's test scripts with run_script (grab test, "
    "distance monitor, vision test, arm test, ...) — they run in the "
    "background and 'stop' kills them. Use it when the user asks to run or "
    "start a test.\n\n"
    "You can speak in different voices: call list_voices to see what's "
    "installed, set_voice to switch. If asked what voices you have, call "
    "list_voices and read it out. You can also make fun noises with "
    "play_sound (bark, woof, growl, howl, meow), and layer a character "
    "sound effect over any voice with set_effect (robot, dalek, monster, "
    "ghost, underwater, telephone, cave, space, giant, chipmunk, drunk; "
    "none to clear).\n\n"
    "TO GRAB A PLAIN-COLOURED OBJECT (red/green/blue/yellow blob): call "
    "grab(color), or grab_all(color) for all of them. Both run in the "
    "background and 'stop' interrupts. For ANY OTHER object — a bottle, a "
    "tube, keys, anything you'd need real eyes for — do the VISION-GUIDED "
    "GRAB below yourself.\n\n"
    "VISION-GUIDED GRAB — you drive the whole loop with your own eyes:\n"
    "1. arm_pose('ready'), gripper('open').\n"
    "2. see. Find the target in the photo. Not visible? drive('right', 0.3) "
    "to sweep and see again (give up after a full sweep and ask for help).\n"
    "3. Judge where it sits in the frame: clearly left of centre -> "
    "drive('left', 0.15); clearly right -> drive('right', 0.15); then see "
    "again. Small turns — easy to overshoot. Repeat until roughly centred.\n"
    "4. Centred: distance_ahead. Over ~15 cm -> drive('forward', 0.3), then "
    "re-see to stay centred as you close in. You CAN reverse with "
    "drive('backward', ...) if you get too close (under 5 cm, back up a touch).\n"
    "5. Within ~15 cm and centred: arm_pose('reach'), gripper('close'), "
    "arm_pose('lift').\n"
    "6. see again to verify — is it held / gone from where it was? Report "
    "what you actually observe.\n"
    "Narrate each round in a few words ('a bit left... closer... got it'). "
    "If several rounds don't line it up, stop and say so.\n\n"
    "MANUAL GRAB (only for custom requests) — aim with the camera, judge "
    "distance with the ultrasonic, then grab with the arm:\n"
    "1. arm_pose('ready'), then gripper('open').\n"
    "2. look_for_object(color). If the camera is unavailable, skip aiming and just "
    "approach straight ahead. If the object isn't seen, drive('right', 0.3) to sweep "
    "and look again.\n"
    "3. If it's seen but the offset is more negative than -0.15, drive('left', 0.2); "
    "if more positive than +0.15, drive('right', 0.2). Re-look until it's centred.\n"
    "4. Once centred, use distance_ahead. If more than ~15 cm, drive('forward', 0.4), "
    "then measure again. Repeat until within ~15 cm. Never drive more than 0.5 s "
    "between measurements, and never drive forward when distance is under 5 cm "
    "(back up with drive('backward', 0.2) if you get too close).\n"
    "5. When within reach: arm_pose('reach'), gripper('close'), arm_pose('lift').\n"
    "6. To put it down: arm_pose('drop'), gripper('open'), arm_pose('home').\n"
    "Narrate briefly as you go ('turning toward it', 'moving closer', 'got it'). "
    "If asked to download AND play a song, download first, then play."
)


# ---------------------------------------------------------------------------
# Brain 1: Claude
# ---------------------------------------------------------------------------
MAX_HISTORY = 40  # entries, not exchanges — keeps long sessions fast and cheap


def _trim_history(history: list) -> None:
    """Drop the oldest turns once history grows past MAX_HISTORY.

    After dropping, keep popping until the list starts at a plain-text user
    message — the API rejects a history that opens with a tool_result whose
    matching tool_use was trimmed away.
    """
    while len(history) > MAX_HISTORY:
        history.pop(0)
        while history and not (
            history[0]["role"] == "user" and isinstance(history[0]["content"], str)
        ):
            history.pop(0)


def claude_brain(user_text: str, history: list) -> str:
    history.append({"role": "user", "content": user_text})
    _trim_history(history)
    mem = load_memory()
    sys_prompt = SYSTEM + (
        "\n\nWHAT YOU REMEMBER (from past chats — treat as true):\n" + mem
        if mem else "")
    while True:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=512,
            system=sys_prompt,
            tools=TOOLS,
            # Auto-cache the conversation prefix (tools + system + history).
            # On Haiku the minimum cacheable prefix is 4096 tokens, so this
            # kicks in once the session grows — exactly when it matters.
            cache_control={"type": "ephemeral"},
            messages=history,
        )
        history.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason != "tool_use":
            return "".join(b.text for b in resp.content if b.type == "text")
        results = []
        for block in resp.content:
            if block.type == "tool_use":
                output = run_tool(block.name, block.input)
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": output})
        history.append({"role": "user", "content": results})


# ---------------------------------------------------------------------------
# Brain 2: offline keyword rules
# ---------------------------------------------------------------------------
def local_brain(user_text: str) -> str:
    t = user_text.lower()

    # music
    if "stop" in t and "music" in t:
        return _stop_music()
    if "download" in t:
        query = re.sub(r"download\s*", "", t, count=1).strip()
        return download_song(query) if query else "What song should I download?"
    if "play" in t:
        query = re.sub(r"play\s*(a\s*song\s*)?", "", t, count=1).strip()
        return play_song(query)

    # memory
    if t.startswith("remember "):
        return remember(user_text.strip()[9:].strip())
    if "forget everything" in t or "clear your memory" in t or "forget your memory" in t:
        return forget_all()
    if "what do you remember" in t:
        mem = load_memory()
        return mem.replace("# MELVINN's memory", "").strip() or "I don't remember anything yet."

    # say
    if t.startswith("say "):
        return user_text.strip()[4:].strip()

    # grab / pick up — runs in the BACKGROUND so "stop" still works mid-grab
    if "grab" in t or "pick up" in t or "pick it up" in t:
        color = next((c for c in ("red", "green", "blue", "yellow") if c in t), "red")
        if "all" in t or "every" in t:
            return start_action(f"picking up all the {color} objects",
                                lambda: grab_all(color))
        return start_action(f"grabbing the {color} object",
                            lambda: grab_sequence(color))
    # put down / release
    if any(p in t for p in ("put down", "put it down", "drop", "release", "let go")):
        return release_sequence()
    # distance query
    if "how far" in t or "distance" in t:
        d = distance_ahead()
        return f"{d:.0f} centimeters ahead." if d >= 0 else "Distance sensor not connected."

    # arm — check longer/more specific joint names first (e.g. "wrist_rotate"
    # before "wrist", since "wrist" is a substring of it) and accept "wrist
    # rotate" (spoken/typed with a space) as well as the underscored form.
    _joints_by_specificity = sorted(ARM_JOINTS, key=len, reverse=True)

    def _joint_in_text(j):
        return j in t or j.replace("_", " ") in t

    if "arm" in t or any(_joint_in_text(j) for j in ARM_JOINTS):
        joint = next((j for j in _joints_by_specificity if _joint_in_text(j)), "base")
        m = re.search(r"(-?\d+(?:\.\d+)?)", t)
        return robot_move_arm(joint, float(m.group(1)) if m else ARM_CENTER_ANGLES[joint])

    # spin / turn
    if "spin" in t:
        m = re.search(r"(\d+(?:\.\d+)?)", t)
        return robot_drive("spin", float(m.group(1)) if m else 2.0)

    # drive
    for kw, direction in [
        (("forward", "ahead", "straight"), "forward"),
        (("back", "reverse"),              "backward"),
        (("left",),                        "left"),
        (("right",),                       "right"),
    ]:
        if any(k in t for k in kw):
            m = re.search(r"(\d+(?:\.\d+)?)\s*(?:s|sec|second|seconds)?\b", t)
            return robot_drive(direction, float(m.group(1)) if m else 1.0)

    # bare "turn" with no side given -> default left (papoi.py advertises "turn 1")
    if "turn" in t:
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:s|sec|second|seconds)?\b", t)
        return robot_drive("left", float(m.group(1)) if m else 1.0)

    if "voice" in t:
        for v in list(VOICES) + _sherpa_voices() + _piper_voices() + _kokoro_voices():
            if v in t:
                return set_voice(v)
        return list_voices()

    # run a whitelisted test script ("run the grab test with yellow")
    if any(w in t for w in ("run", "launch", "start the")):
        for s in SCRIPTS:
            if s in t or s.replace(" ", "") in t.replace(" ", ""):
                color = next((c for c in ("red", "green", "blue", "yellow") if c in t), "")
                return run_script(s, color)
        if "script" in t or "test" in t:
            return list_scripts()

    if "script" in t and ("list" in t or "what" in t or "which" in t):
        return list_scripts()

    # SoX character effects layered on any voice ("add a monster effect")
    if "effect" in t:
        if any(w in t for w in ("off", "no ", "clear", "remove", "normal", "stop")):
            return set_effect("none")
        for e in EFFECTS:
            if e in t:
                return set_effect(e)
        return ("Which effect? I have: " +
                ", ".join(n for n in EFFECTS if n != "none") + ".")
    # "sound like a dalek / robot / ghost..." also picks an effect
    if "sound like" in t:
        for e in EFFECTS:
            if e != "none" and e in t:
                return set_effect(e)

    # animal / creature noises (fun) — check before generic handling
    if "dog" in t or "sound like" in t:
        return play_sound("bark")
    for s in SOUND_EFFECTS:
        if s in t:
            return play_sound(s)

    if any(w in t for w in ("your name", "who are you", "melvinn", "melvin")):
        return ("I am MELVINN — Modular Experimental Learning Vehicle with "
                "Integrated Neural Networks. Melvin also means strong friend.")
    if any(w in t for w in ("hello", "hi", "hey")):
        return "Hi! I am MELVINN, running in offline mode."
    if "help" in t or "what can" in t:
        return "Say: forward, back, left, right, spin, play, download, or stop."

    return "I didn't catch that. Try: forward, spin, play a song, or download a song."


# ---------------------------------------------------------------------------
# Think — pick brain
# ---------------------------------------------------------------------------
def think(user_text: str, history: list) -> str:
    t = user_text.lower()
    if "stop" in t and "music" not in t:
        was_busy = stop_action()        # interrupt any background action
        robot_drive("stop")
        return "Stopping." if was_busy else "Stopped."
    if action_running():
        # Busy multitasking guard: one body, one action. Chat still works
        # offline-style, but no new motion until this one ends or is stopped.
        return f"I'm busy {_action_name}. Say stop to interrupt me."
    if client is not None:
        try:
            return claude_brain(user_text, history)
        except Exception as exc:
            print(f"[Claude error: {exc}] -> offline mode")
    return local_brain(user_text)


# ---------------------------------------------------------------------------
# Text-to-speech — MELVINN's voices
# ---------------------------------------------------------------------------
# Named voice presets. Each is espeak-ng parameters: (voice, pitch 0-99,
# speed wpm). espeak-ng ships every voice, so all of these work offline with
# nothing extra to install. Try them:  say in a deep voice hello  /
# "change your voice to robot".
VOICES = {
    "melvinn": ("en+m3", 50, 160),     # the default — friendly male
    "robot":   ("en+croak", 30, 140),  # croaky sci-fi robot
    "deep":    ("en+m5", 20, 140),     # low and slow
    "chipmunk": ("en+f4", 95, 210),    # squeaky and fast
    "female":  ("en+f3", 60, 165),
    "whisper": ("en+whisper", 40, 150),
    "spanish": ("es+m3", 50, 160),     # habla español
    # --- silly character voices ---
    "puppy":   ("en+f5", 90, 200),     # squeaky excited little dog
    "growl":   ("en+croak", 5, 110),   # big low grumbly dog / monster
    "alien":   ("en+croak", 80, 175),  # squeaky-croaky little alien
    "giant":   ("en+m6", 1, 95),       # slow booming giant
}
# Things MELVINN can "say" that are really sound effects, made from espeak.
SOUND_EFFECTS = {
    "bark":  ("puppy", "woof! woof woof!"),
    "woof":  ("puppy", "woof! woof woof!"),
    "growl": ("growl", "grrrrr rrrrr grrr"),
    "howl":  ("puppy", "awoooooo"),
    "meow":  ("chipmunk", "mee-ow, meow"),
}


def play_sound(name: str) -> str:
    """Make an animal/creature noise with the TTS engine (a bit of fun)."""
    global _voice
    name = name.strip().lower()
    if name not in SOUND_EFFECTS:
        return f"I don't know how to {name}. I can: {', '.join(SOUND_EFFECTS)}."
    preset, text = SOUND_EFFECTS[name]
    saved = _voice
    _voice = preset             # borrow the character voice just for the noise
    try:
        _say_espeak(text)       # espeak so pitch/speed apply, not piper
        print(f"[MELVINN] *{name}*")
    finally:
        _voice = saved
    return f"*{name}*"
_voice = os.environ.get("MELVINN_VOICE", "melvinn")
PIPER_DIR = os.path.expanduser("~/piper")


def _piper_voices() -> list[str]:
    """Names of downloaded natural (piper) voices: ~/piper/<name>.onnx."""
    names = [os.path.basename(p)[:-5] for p in glob(os.path.join(PIPER_DIR, "*.onnx"))]
    return sorted(n for n in names if n != "voice")   # voice.onnx = the default


# --- Kokoro: high-quality neural TTS, run in-process (no server) ------------
# Runs as a plain Python library right here, the same way _say_piper shells out
# to the piper binary -- no server, fully offline. Needs `kokoro-onnx` +
# `soundfile` and the two model files in ~/kokoro/ (setup instructions in the
# README). On the 32-bit Pi 3 you also need a community onnxruntime armhf wheel;
# if any of that is missing, speak() just falls back to Piper. A voice named
# like af_heart / am_michael routes here automatically.
# (KOKORO_URL is an optional escape hatch: set it to an OpenAI-compatible
#  /v1/audio/speech endpoint to offload synthesis to another machine instead.)
KOKORO_URL = os.environ.get("KOKORO_URL", "")
KOKORO_DIR = os.path.expanduser("~/kokoro")
KOKORO_MODEL = os.path.join(KOKORO_DIR, "kokoro-v1.0.int8.onnx")
KOKORO_VOICES_BIN = os.path.join(KOKORO_DIR, "voices-v1.0.bin")
KOKORO_VOICES = [
    "af_heart", "af_bella", "af_nicole", "af_sarah", "af_sky",
    "am_michael", "am_adam", "am_fenrir", "am_puck",
    "bf_emma", "bf_isabella", "bm_george", "bm_fable",
]
_kokoro = None                  # lazy-loaded engine
_kokoro_unavailable = False


def _kokoro_available() -> bool:
    """True if we can speak Kokoro locally (model files present) or remotely."""
    return bool(KOKORO_URL) or (
        os.path.exists(KOKORO_MODEL) and os.path.exists(KOKORO_VOICES_BIN))


def _kokoro_voices() -> list[str]:
    """Kokoro voices, but only when we can actually speak them."""
    return KOKORO_VOICES if _kokoro_available() else []


def _kokoro_engine():
    """Load the in-process Kokoro model once (like the camera/arm lazy-init)."""
    global _kokoro, _kokoro_unavailable
    if _kokoro is not None or _kokoro_unavailable:
        return _kokoro
    if not (os.path.exists(KOKORO_MODEL) and os.path.exists(KOKORO_VOICES_BIN)):
        _kokoro_unavailable = True
        return None
    try:
        from kokoro_onnx import Kokoro
        _kokoro = Kokoro(KOKORO_MODEL, KOKORO_VOICES_BIN)
    except Exception as exc:
        print(f"[kokoro unavailable: {exc}] — using Piper instead")
        _kokoro_unavailable = True
        return None
    return _kokoro


# --- sherpa-onnx: neural Kokoro TTS that actually installs on the 32-bit Pi 3 -
# sherpa-onnx ships its own armv7l wheel and bundles the runtime, so it works
# where kokoro-onnx (needs onnxruntime, no 32-bit wheel) fails. This is
# MELVINN's best-quality local voice. Model dir = the extracted
# ~/kokoro-en-v0_19/. Voices are speaker ids (sid) mapped to friendly names.
SHERPA_DIR = os.path.expanduser("~/kokoro-en-v0_19")
SHERPA_MODEL = os.path.join(SHERPA_DIR, "model.onnx")
SHERPA_VOICES_BIN = os.path.join(SHERPA_DIR, "voices.bin")
SHERPA_TOKENS = os.path.join(SHERPA_DIR, "tokens.txt")
SHERPA_DATA_DIR = os.path.join(SHERPA_DIR, "espeak-ng-data")
SHERPA_VOICES = {        # friendly name -> speaker id in kokoro-en-v0_19
    "af": 0, "bella": 1, "nicole": 2, "sarah": 3, "sky": 4,
    "adam": 5, "michael": 6, "emma": 7, "isabella": 8, "george": 9, "lewis": 10,
}
DEFAULT_SHERPA_VOICE = os.environ.get("MELVINN_SHERPA_VOICE", "bella")
_sherpa_tts = None
_sherpa_unavailable = False


def _sherpa_available() -> bool:
    return os.path.exists(SHERPA_MODEL) and os.path.exists(SHERPA_VOICES_BIN)


def _sherpa_voices() -> list[str]:
    return list(SHERPA_VOICES) if _sherpa_available() else []


def _sherpa_engine():
    """Load the sherpa-onnx Kokoro model once (lazy, like the camera/arm)."""
    global _sherpa_tts, _sherpa_unavailable
    if _sherpa_tts is not None or _sherpa_unavailable:
        return _sherpa_tts
    if not _sherpa_available():
        _sherpa_unavailable = True
        return None
    try:
        import sherpa_onnx
        cfg = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                kokoro=sherpa_onnx.OfflineTtsKokoroModelConfig(
                    model=SHERPA_MODEL, voices=SHERPA_VOICES_BIN,
                    tokens=SHERPA_TOKENS, data_dir=SHERPA_DATA_DIR,
                ),
                num_threads=2, provider="cpu",
            ),
            max_num_sentences=1,
        )
        _sherpa_tts = sherpa_onnx.OfflineTts(cfg)
    except Exception as exc:
        print(f"[sherpa-onnx unavailable: {exc}] — using Piper instead")
        _sherpa_unavailable = True
        return None
    return _sherpa_tts


def _say_sherpa(text: str) -> bool:
    """Speak with the neural sherpa-onnx Kokoro voice. False -> fall back."""
    eng = _sherpa_engine()
    if eng is None:
        return False
    name = _voice if _voice in SHERPA_VOICES else DEFAULT_SHERPA_VOICE
    sid = SHERPA_VOICES.get(name, SHERPA_VOICES[DEFAULT_SHERPA_VOICE])
    wav = None
    try:
        import soundfile as sf
        import numpy as np
        audio = eng.generate(text, sid=sid, speed=1.0)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav = f.name
        sf.write(wav, np.array(audio.samples, dtype="float32"), audio.sample_rate)
        _play_wav(wav)
        return True
    except Exception as exc:
        print(f"[sherpa-onnx error: {exc}] — using Piper instead")
        return False
    finally:
        if wav:
            try: os.remove(wav)
            except OSError: pass


def list_voices() -> str:
    """Everything MELVINN can sound like right now, natural voices first."""
    natural = _piper_voices()
    if os.path.exists(PIPER_MODEL):
        natural.insert(0, "melvinn (default)")
    parts = []
    if _sherpa_voices():
        parts.append("Neural voices (best): " + ", ".join(_sherpa_voices()) + ".")
    if _kokoro_voices():
        parts.append("High-quality Kokoro voices: " +
                     ", ".join(_kokoro_voices()) + ".")
    if natural:
        parts.append("Natural voices: " + ", ".join(natural) + ".")
    parts.append("Classic robot voices: " +
                 ", ".join(v for v in VOICES if v != "melvinn") + ".")
    parts.append("Effects you can layer on any voice: " +
                 ", ".join(n for n in EFFECTS if n != "none") + ".")
    parts.append("Say for example: use your joe voice, or add a monster effect.")
    return " ".join(parts)


def set_voice(name: str) -> str:
    """Switch MELVINN's voice: a VOICES preset or any downloaded piper model."""
    global _voice
    name = name.strip().lower()
    if name not in VOICES and name not in _piper_voices() \
            and name not in _kokoro_voices() and name not in _sherpa_voices():
        return f"I don't have a '{name}' voice. {list_voices()}"
    _voice = name
    speak(f"This is my {name} voice.")     # demo it immediately
    return f"Voice set to {name}."


# ---------------------------------------------------------------------------
# Voice EFFECTS — a SoX post-processing layer on top of ANY voice.
# ---------------------------------------------------------------------------
# The research payoff: instead of only espeak's pitch/speed, run the finished
# audio (from piper OR espeak) through SoX effect chains. This keeps piper's
# natural, intelligible voice but lets it sound like a robot, a monster, a
# ghost, a Dalek, etc. SoX is tiny and fast on a Pi 3. Effects STACK on top of
# whatever voice is selected, so "amy + monster" or "joe + telephone" work.
# Each value is a raw SoX effect chain (see `man sox`). Needs the `sox` package.
EFFECTS = {
    "none":       "",
    "robot":      "overdrive 10 echo 0.6 0.7 8 0.6",            # buzzy metallic
    "dalek":      "overdrive 22 22 echo 0.8 0.88 6 0.5 pitch -120",  # Dr Who Dalek
    "chipmunk":   "pitch 550",                                  # fast squeaky
    "giant":      "pitch -450 speed 0.92 reverb 25",           # huge and slow
    "monster":    "pitch -320 overdrive 14 reverb 45",         # deep growly
    "ghost":      "pitch -200 reverb 85 chorus 0.7 0.9 55 0.4 0.25 2 -t",
    "underwater": "lowpass 500 tremolo 8 45",                   # gurgly muffled
    "telephone":  "sinc 300-3400 overdrive 6",                  # tinny phone
    "cave":       "reverb 92 100 100 pitch -80",               # big echoey cave
    "space":      "chorus 0.7 0.9 55 0.4 0.25 2 -t reverb 60 pitch -60",
    "drunk":      "speed 0.9 chorus 0.6 0.9 50 0.4 0.25 2 -t",  # wobbly
    # Rocky, the Eridian from Project Hail Mary. He has no vocal cords as we'd
    # know them -- he talks in MUSICAL CHORDS, several notes sounding at once,
    # heard through the wall of his high-pressure tunnel. Three detuned chorus
    # voices stack harmonics over the speech to fake the chord, the pitch drop
    # gives it body, and the reverb puts it back in the tunnel.
    "rocky":      "pitch -150 chorus 0.5 0.8 45 0.5 0.25 2 -t 55 0.45 0.35 2.5 -t 65 0.4 0.45 3 -t reverb 50",
}
_effect = os.environ.get("MELVINN_EFFECT", "none")

# --- MELVINN's SIGNATURE voice ---------------------------------------------
# The default identity = a warm base Piper voice + a subtle SoX character, so
# "melvinn" doesn't just sound like a stock model. Applied ONLY to the default
# voice, and ONLY when no explicit effect is chosen (so "add a monster effect"
# still overrides it, and picking a named voice like 'joe' turns it off).
# Tune with the env vars; set MELVINN_SIGNATURE_FX="" to disable the signature.
SIGNATURE_VOICE = os.environ.get("MELVINN_SIGNATURE_VOICE", "joe")   # base timbre
# Warm, human, NOT robotic: boost the low end for warmth, gently soften the
# highs, and add a touch of natural room. No chorus/pitch-shift -- those are
# what make a voice sound synthetic.
SIGNATURE_FX = os.environ.get(
    "MELVINN_SIGNATURE_FX", "bass +4 treble -1 reverb 12")


def set_effect(name: str) -> str:
    """Layer a SoX character effect over whatever voice is selected."""
    global _effect
    name = name.strip().lower()
    if name in ("off", "clear", "normal", "plain"):
        name = "none"
    if name not in EFFECTS:
        return (f"I don't have a '{name}' effect. I have: "
                f"{', '.join(n for n in EFFECTS if n != 'none')}.")
    if shutil.which("sox") is None and name != "none":
        return "I need the sox tool for effects. Run: sudo apt install -y sox"
    _effect = name
    if name == "none":
        speak("Effect off.")
        return "Effect cleared."
    speak(f"How do I sound with the {name} effect?")   # demo it
    return f"Effect set to {name}."


def _play_wav(wav: str) -> None:
    """Play a wav, first running it through the active SoX effect if one is set."""
    chain = EFFECTS.get(_effect, "")
    # MELVINN's signature: the default voice gets its subtle character effect,
    # unless the user picked an explicit effect (which takes over).
    if _voice == "melvinn" and _effect == "none":
        chain = SIGNATURE_FX
    if chain and shutil.which("sox"):
        out = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                out = f.name
            # sox in.wav out.wav <effect chain...>
            subprocess.run(["sox", wav, out] + chain.split(),
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           check=True)
            subprocess.run(["aplay", "-q", "-D", AUDIO_DEVICE, out])
            return
        except (OSError, subprocess.SubprocessError):
            pass          # effect failed -> fall through to the dry wav
        finally:
            if out:
                try: os.remove(out)
                except OSError: pass
    subprocess.run(["aplay", "-q", "-D", AUDIO_DEVICE, wav])


def _say_kokoro(text: str) -> bool:
    """Speak with Kokoro. Prefers the in-process model (no server); if KOKORO_URL
    is set instead, offloads to that endpoint. False if neither is available so
    the caller can fall back to Piper."""
    voice = _voice if _voice in KOKORO_VOICES else "af_heart"

    # In-process (default, no server) --------------------------------------
    eng = _kokoro_engine()
    if eng is not None:
        wav = None
        try:
            import soundfile as sf
            samples, sr = eng.create(text, voice=voice, speed=1.0, lang="en-us")
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wav = f.name
            sf.write(wav, samples, sr)
            _play_wav(wav)
            return True
        except Exception as exc:
            print(f"[kokoro error: {exc}] — using Piper instead")
        finally:
            if wav:
                try: os.remove(wav)
                except OSError: pass

    # Optional remote endpoint ---------------------------------------------
    if KOKORO_URL:
        import json as _json
        import urllib.request as _url
        body = _json.dumps({"model": "kokoro", "voice": voice,
                            "input": text, "response_format": "wav"}).encode()
        wav = None
        try:
            req = _url.Request(KOKORO_URL, data=body,
                               headers={"Content-Type": "application/json"})
            with _url.urlopen(req, timeout=15) as resp:
                audio = resp.read()
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wav = f.name
                f.write(audio)
            _play_wav(wav)
            return True
        except Exception:
            return False
        finally:
            if wav:
                try: os.remove(wav)
                except OSError: pass
    return False


def _say_piper(text: str) -> bool:
    # Piper only speaks the default voice (one .onnx model). Named presets
    # fall through to espeak-ng, which can actually change voice on the fly.
    # (Drop more models in ~/piper/<name>.onnx to give piper more voices.)
    if _voice == "melvinn":
        # Signature base timbre if it's installed, else the default voice.onnx.
        sig = os.path.expanduser(f"~/piper/{SIGNATURE_VOICE}.onnx")
        model = sig if os.path.exists(sig) else PIPER_MODEL
    else:
        model = os.path.expanduser(f"~/piper/{_voice}.onnx")
    if shutil.which("piper") is None or not os.path.exists(model):
        return False
    wav = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav = f.name
        subprocess.run(["piper", "--model", model, "--output_file", wav],
                       input=text.encode(), stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True)
        _play_wav(wav)
        return True
    except (OSError, subprocess.SubprocessError):
        return False
    finally:
        if wav:
            try: os.remove(wav)
            except OSError: pass


def _say_espeak(text: str) -> None:
    voice, pitch, speed = VOICES.get(_voice, VOICES["melvinn"])
    wav = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav = f.name
        # Write to a wav so the SoX effect layer can process it (same path as
        # piper). -w = write to file instead of playing directly.
        subprocess.run(["espeak-ng", "-v", voice, "-p", str(pitch),
                        "-s", str(speed), "-w", wav, text],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _play_wav(wav)
    except FileNotFoundError:
        pass
    finally:
        if wav:
            try: os.remove(wav)
            except OSError: pass


def speak(text: str) -> None:
    print(f"[MELVINN] {text}")
    if not text.strip():
        return
    # Default is Piper (fast, light). sherpa-onnx neural voices are OPT-IN only
    # -- the Kokoro model needs ~900MB and swap-thrashes a 1GB Pi 3, so we never
    # load it for the default voice; only when a sherpa speaker is explicitly
    # selected (and even then, prefer a lighter model on low-RAM boards).
    if _voice in SHERPA_VOICES and _say_sherpa(text):
        return
    if _say_kokoro(text):
        return
    if not _say_piper(text):
        _say_espeak(text)


# ---------------------------------------------------------------------------
# Speech-to-text (Vosk, offline)
# ---------------------------------------------------------------------------
_vosk_model = None  # loaded once — Model() takes seconds and ~200MB RAM on a Pi 3

# Constrain Vosk to the words MELVINN actually understands. Feeding the
# recognizer a fixed vocabulary ("grammar") is the single biggest free accuracy
# win for a command robot -- it stops mis-hearing "grab" as "grand" etc. because
# it only considers these words. "[unk]" lets genuinely unknown speech through
# as a catch-all instead of forcing a wrong match. Set MELVINN_OPEN_MIC=1 to
# disable this and use the full open vocabulary (better for free-form chat).
WAKE_WORD = os.environ.get("MELVINN_WAKE_WORD", "melvinn").lower()
COMMAND_VOCAB = (
    "melvinn hey hi hello there "
    "forward backward back left right straight ahead spin turn around stop go move come "
    "grab pick up it that this thing object put down drop release let go hold "
    "red green blue yellow orange the "
    "arm base shoulder elbow wrist rotate gripper hand open close raise lower "
    "degrees point to home ready reach lift "
    "play song music download stop pause "
    "voice change your name who are you what are you speak like use "
    "bark woof growl howl meow dog cat sound make a noise "
    "effect robot monster ghost dalek underwater telephone cave space giant chipmunk drunk normal none off "
    "distance how far away is it "
    "run launch script test monitor calibrate vision track avoid sequence recognize "
    "help what can you do tell me "
    "zero one two three four five six seven eight nine ten "
    "yes no okay thanks thank you please good "
)
USE_GRAMMAR = not os.environ.get("MELVINN_OPEN_MIC")


def _grammar_json() -> str:
    return json.dumps([COMMAND_VOCAB.strip() + " [unk]"])


def _require_vosk() -> None:
    if not _VOSK_AVAILABLE:
        raise RuntimeError(
            "Vosk not installed. Run: pip install vosk\n"
            "Then download a model: https://alphacephei.com/vosk/models\n"
            "Extract to ~/vosk-model"
        )
    if not os.path.exists(VOSK_MODEL_DIR):
        raise RuntimeError(
            f"Vosk model not found at {VOSK_MODEL_DIR}.\n"
            "Download vosk-model-small-en-us-0.15.zip from https://alphacephei.com/vosk/models\n"
            "and unzip it to ~/vosk-model"
        )


def _new_recognizer(grammar: bool = True):
    """A fresh KaldiRecognizer, grammar-constrained unless disabled."""
    global _vosk_model
    if _vosk_model is None:
        print("[loading speech model...]")
        _vosk_model = Model(VOSK_MODEL_DIR)
    if grammar and USE_GRAMMAR:
        return KaldiRecognizer(_vosk_model, SAMPLE_RATE, _grammar_json())
    return KaldiRecognizer(_vosk_model, SAMPLE_RATE)


def _open_mic():
    # arecord, not Python's sounddevice/PortAudio: PortAudio's raw ALSA
    # "default"/"sysdefault" device rejected 16kHz outright ("Invalid sample
    # rate"). plughw auto-converts, and `arecord -D plughw:1,0 -r 16000` is
    # the exact command already confirmed working (see voice-assistant.md).
    return subprocess.Popen(
        ["arecord", "-D", MIC_DEVICE, "-f", "S16_LE", "-c", "1",
         "-r", str(SAMPLE_RATE), "-t", "raw"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )


def transcribe() -> str:
    """Listen on the mic until a complete phrase is detected, return the text."""
    _require_vosk()
    rec = _new_recognizer(grammar=True)
    print("[listening...]")
    proc = _open_mic()
    try:
        while True:
            data = proc.stdout.read(4000)  # ~0.25s of audio at 16kHz mono S16LE
            if not data:
                break
            if rec.AcceptWaveform(data):
                text = json.loads(rec.Result()).get("text", "").strip()
                if text:
                    print(f"[heard] {text}")
                    return text
    finally:
        proc.terminate()
        proc.wait()


# --- Wake word: MELVINN sleeps until it hears its name ----------------------
# Two engines. Porcupine (Picovoice) is far more accurate/efficient on a Pi 3
# and is used automatically when a PICOVOICE_ACCESS_KEY and a ~/melvinn.ppn
# keyword file are present. Otherwise we fall back to spotting "melvinn" in the
# Vosk stream -- no key, no extra install, works today.
MELVINN_PPN = os.path.expanduser("~/melvinn.ppn")


def _porcupine_ready() -> bool:
    if not (os.environ.get("PICOVOICE_ACCESS_KEY") and os.path.exists(MELVINN_PPN)):
        return False
    try:
        import pvporcupine  # noqa: F401
        from pvrecorder import PvRecorder  # noqa: F401
        return True
    except Exception:
        return False


def _wait_for_wake_porcupine() -> bool:
    import pvporcupine
    from pvrecorder import PvRecorder
    pp = pvporcupine.create(access_key=os.environ["PICOVOICE_ACCESS_KEY"],
                            keyword_paths=[MELVINN_PPN])
    rec = PvRecorder(frame_length=pp.frame_length)
    try:
        rec.start()
        while True:
            if pp.process(rec.read()) >= 0:
                return True
    except (KeyboardInterrupt, EOFError):
        return False
    finally:
        rec.stop(); rec.delete(); pp.delete()


def wait_for_wake() -> bool:
    """Block until MELVINN hears its wake word. Returns False if the mic dies."""
    if _porcupine_ready():
        return _wait_for_wake_porcupine()
    _require_vosk()
    rec = _new_recognizer(grammar=True)
    proc = _open_mic()
    try:
        while True:
            data = proc.stdout.read(4000)
            if not data:
                return False
            # Check both partial and final text so it wakes mid-phrase.
            if rec.AcceptWaveform(data):
                text = json.loads(rec.Result()).get("text", "")
            else:
                text = json.loads(rec.PartialResult()).get("partial", "")
            if WAKE_WORD in text.lower():
                return True
    finally:
        proc.terminate()
        proc.wait()


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main() -> None:
    global _voice_mode
    voice_mode = "--type" not in sys.argv
    _voice_mode = voice_mode
    # Wake-word mode (default in voice): MELVINN sleeps until it hears its name,
    # then listens for one command. --nowake makes it act on every phrase.
    wake_mode = voice_mode and "--nowake" not in sys.argv

    history: list = []

    brain_label = f"Claude ({MODEL})" if client is not None else "offline rules"
    input_label = "voice (Vosk)" if voice_mode else "keyboard"
    print(f"Brain: {brain_label}  |  Input: {input_label}")
    if client is not None:
        print("Talk to me: drive / arm / dance / grab / music / videos on my "
              "face / expressions / voices / 'stop' interrupts anything")
    else:
        print("Commands: move forward / spin / play a song / download despacito / stop")
    if voice_mode:
        if wake_mode:
            print(f"Say '{WAKE_WORD.title()}' to wake me, then give a command. Ctrl-C to quit.\n")
        else:
            print("Speak after '[listening...]' appears. Ctrl-C to quit.\n")
    else:
        print("Type a command. Ctrl-C or 'quit' to exit.\n")

    speak("Hi, I am ready. What should I do?")

    try:
        while True:
            if voice_mode:
                try:
                    if wake_mode:
                        print(f"[sleeping — say '{WAKE_WORD.title()}']")
                        if not wait_for_wake():
                            continue
                        chirp("wake")      # a bright "hm?" when it hears its name
                        speak("Yes?")
                    user_text = transcribe()
                except RuntimeError as e:
                    print(f"[STT error] {e}")
                    print("Falling back to keyboard input. Use --type flag to skip this message.")
                    voice_mode = False
                    wake_mode = False
                    user_text = input("you> ").strip()
            else:
                user_text = input("you> ").strip()

            if not user_text:
                continue
            if user_text.lower() in ("quit", "exit", "q"):
                break

            reply = think(user_text, history)
            if reply:
                speak(reply)

    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        _stop_music()
        if motor_left is not None:
            motor_left.stop()
        if motor_right is not None:
            motor_right.stop()
        print("\nbye")


if __name__ == "__main__":
    main()
