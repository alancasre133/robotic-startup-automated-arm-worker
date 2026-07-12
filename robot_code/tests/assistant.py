"""
Robot assistant brain — voice in, voice out, and full motion control.

Pipeline:  mic -> transcribe (Vosk) -> brain (Claude / offline) -> {speak, drive, music} -> repeat

TWO brains, automatic fallback:
  1. Claude API (smart)  — natural language, when a key is set and the API works.
  2. Offline rules (free) — keyword parser; no key, no internet, no extra installs.

Voice commands supported:
  move forward / go back / turn left / spin      -> drives the motors
  play a song / play despacito                   -> plays from ~/music
  download despacito                             -> downloads via yt-dlp
  stop the music                                 -> stops playback
  say hello                                      -> speaks the text
  stop                                           -> stops motors instantly

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

from gpiozero import Motor, OutputDevice

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
# Hardware — motors
# ---------------------------------------------------------------------------
# TEMPORARY WORKAROUND: Motor A's A-1A wire (GPIO16 -> L9110S A-1A) is loose or
# disconnected — motor_diag.py showed that input floats HIGH no matter what the
# Pi drives it to, so Motor A can only go FORWARD or STOP; it can't reverse.
# (forward / right / spin / stop only ever ask Motor A to go forward or stop,
# so those are unaffected — only backward/left, which need Motor A to reverse.)
# Reseat the GPIO16 <-> A-1A jumper, confirm with motor_diag.py, then set this
# back to False to return to normal two-direction control.
MOTOR_A_FORWARD_ONLY = True


class _ForwardOnlyMotor:
    """Drop-in for gpiozero's Motor when only GPIO20 (A-1B) actually works.

    Drives GPIO20 directly: LOW = spin forward, HIGH = stop/brake. backward()
    can't truly reverse, so it just stops this side — the robot pivots around
    the stopped wheel instead of turning symmetrically or backing up straight.
    """

    def __init__(self, pin):
        self._pin = OutputDevice(pin)
        self._pin.on()  # start stopped

    def forward(self, speed=1):
        self._pin.off()

    def backward(self, speed=1):
        self._pin.on()  # can't reverse — stop this side instead

    def stop(self):
        self._pin.on()


motor_a = motor_b = None
_music_proc = None          # currently playing mpg123 process

# Jab the motors a few times before steady drive to break static friction on a
# heavy/top-heavy bot. Set False if the bot moves fine and you want instant, quiet starts.
ROCK_START = True


def _ensure_motors():
    global motor_a, motor_b
    if motor_a is None:
        motor_a = _ForwardOnlyMotor(20) if MOTOR_A_FORWARD_ONLY else Motor(forward=16, backward=20, pwm=False)
        motor_b = Motor(forward=27, backward=22, pwm=False)
    return motor_a, motor_b


# WORKAROUND: motor A's A-1A wire (GPIO16) is loose/disconnected, so motor A
# can only go forward or stop — it can never reverse (see motor_diag.py results:
# GPIO16 has no effect; A only responds to A2/GPIO20 as forward-vs-stop). Until
# that wire is reseated, any move needing a.backward() is downgraded to a.stop(),
# turning a full two-wheel spin into a one-wheel pivot. Set this to False (or
# delete the substitution below) once the wire is fixed.
MOTOR_A_A1A_STUCK = True


def robot_drive(direction: str, seconds: float = 1.0) -> str:
    if direction == "stop":
        if motor_a is not None:
            motor_a.stop()
            motor_b.stop()
        return "Stopped."
    if direction not in ("forward", "backward", "left", "right", "spin"):
        return f"Unknown direction: {direction}"
    a, b = _ensure_motors()
    a_backward = a.stop if MOTOR_A_A1A_STUCK else a.backward
    moves = {
        "forward":  (a.forward,  b.forward),
        "backward": (a_backward, b.backward),   # pivot on A, not a true reverse (see workaround above)
        "left":     (a_backward, b.forward),    # pivot on A, wider turn than a full spin
        "right":    (a.forward,  b.backward),
        "spin":     (a.forward,  b.backward),   # full spin (right motors fwd, left bwd)
    }
    left_fn, right_fn = moves[direction]

    # "Rock" to break static friction on a heavy / top-heavy chassis. The motors
    # are already driven at full voltage (pwm=False), so there's no "more power"
    # to give — instead we jab in the target direction a few times to jolt the
    # bot loose from a standstill, then commit to steady drive. Toggle with the
    # ROCK_START flag. This only helps it START moving; it can't fix sustained
    # crawling (that needs more volts or less weight — see HARDWARE.md).
    if ROCK_START:
        for _ in range(3):
            left_fn()
            right_fn()
            sleep(0.12)
            a.stop()
            b.stop()
            sleep(0.06)

    left_fn()
    right_fn()
    secs = min(seconds, 5)
    sleep(secs)
    a.stop()
    b.stop()
    note = " (pivot, not a full turn — motor A's reverse wire is loose)" if (
        MOTOR_A_A1A_STUCK and direction in ("backward", "left")
    ) else ""
    return f"Drove {direction} for {secs} seconds.{note}"


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
# resting open/closed angle). shoulder/elbow centered at 45 (not 90) to clear
# the chassis on this build -- confirmed on-device.
ARM_CENTER_ANGLES = {j: 90.0 for j in ARM_JOINTS}
ARM_CENTER_ANGLES["shoulder"] = 45.0
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


def robot_move_arm(joint: str, angle: float) -> str:
    """Move one arm joint (PCA9685 servo) to an angle in degrees (0-180)."""
    if not _ARM_LIBS_AVAILABLE:
        return "Arm libraries not installed — see docs/arm-setup.md"
    if _ensure_arm() is None:
        return "Arm not connected (PCA9685 not found on I2C) — check wiring."
    joint = joint if joint in ARM_JOINTS else "base"
    angle = max(0.0, min(180.0, angle))
    _arm_servos[joint].angle = angle
    return f"Moved {joint} to {angle:.0f} degrees."


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
    print(f"[robot] Playing {os.path.basename(path)}.")
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
    return f"Unknown tool: {name}"


SYSTEM = (
    "You are the brain of a small robot car. You can drive, move the arm, "
    "play or download songs, and chat. Keep spoken replies short (1-2 sentences) "
    "since they are read aloud. Only drive or move when the user asks. "
    "If asked to download AND play, download first, then play."
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
    while True:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=512,
            system=SYSTEM,
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

    # say
    if t.startswith("say "):
        return user_text.strip()[4:].strip()

    # arm — check longer/more specific joint names first (e.g. "wrist_rotate"
    # before "wrist", since "wrist" is a substring of it) and accept "wrist
    # rotate" (spoken/typed with a space) as well as the underscored form.
    _joints_by_specificity = sorted(ARM_JOINTS, key=len, reverse=True)

    def _joint_in_text(j):
        return j in t or j.replace("_", " ") in t

    if "arm" in t or any(_joint_in_text(j) for j in ARM_JOINTS):
        joint = next((j for j in _joints_by_specificity if _joint_in_text(j)), "base")
        m = re.search(r"(-?\d+(?:\.\d+)?)", t)
        return robot_move_arm(joint, float(m.group(1)) if m else 90.0)

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

    if any(w in t for w in ("hello", "hi", "hey")):
        return "Hi! I am running in offline mode."
    if "help" in t or "what can" in t:
        return "Say: forward, back, left, right, spin, play, download, or stop."

    return "I didn't catch that. Try: forward, spin, play a song, or download a song."


# ---------------------------------------------------------------------------
# Think — pick brain
# ---------------------------------------------------------------------------
def think(user_text: str, history: list) -> str:
    if "stop" in user_text.lower() and "music" not in user_text.lower():
        return robot_drive("stop")
    if client is not None:
        try:
            return claude_brain(user_text, history)
        except Exception as exc:
            print(f"[Claude error: {exc}] -> offline mode")
    return local_brain(user_text)


# ---------------------------------------------------------------------------
# Text-to-speech
# ---------------------------------------------------------------------------
def _say_piper(text: str) -> bool:
    if shutil.which("piper") is None or not os.path.exists(PIPER_MODEL):
        return False
    wav = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav = f.name
        subprocess.run(["piper", "--model", PIPER_MODEL, "--output_file", wav],
                       input=text.encode(), stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True)
        subprocess.run(["aplay", "-q", "-D", AUDIO_DEVICE, wav])
        return True
    except (OSError, subprocess.SubprocessError):
        return False
    finally:
        if wav:
            try: os.remove(wav)
            except OSError: pass


def _say_espeak(text: str) -> None:
    try:
        tts = subprocess.Popen(["espeak-ng", text, "--stdout"], stdout=subprocess.PIPE)
        subprocess.run(["aplay", "-q", "-D", AUDIO_DEVICE], stdin=tts.stdout)
        tts.stdout.close()
        tts.wait()
    except FileNotFoundError:
        pass


def speak(text: str) -> None:
    print(f"[robot] {text}")
    if not text.strip():
        return
    if not _say_piper(text):
        _say_espeak(text)


# ---------------------------------------------------------------------------
# Speech-to-text (Vosk, offline)
# ---------------------------------------------------------------------------
_vosk_model = None  # loaded once — Model() takes seconds and ~200MB RAM on a Pi 3


def transcribe() -> str:
    """Listen on the mic until a complete phrase is detected, return the text."""
    global _vosk_model
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
    if _vosk_model is None:
        print("[loading speech model...]")
        _vosk_model = Model(VOSK_MODEL_DIR)
    rec = KaldiRecognizer(_vosk_model, SAMPLE_RATE)

    print("[listening...]")
    # arecord, not Python's sounddevice/PortAudio: PortAudio's raw ALSA
    # "default"/"sysdefault" device rejected 16kHz outright ("Invalid sample
    # rate"). plughw auto-converts, and `arecord -D plughw:1,0 -r 16000` is
    # the exact command already confirmed working (see voice-assistant.md).
    proc = subprocess.Popen(
        ["arecord", "-D", MIC_DEVICE, "-f", "S16_LE", "-c", "1", "-r", str(SAMPLE_RATE), "-t", "raw"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    try:
        while True:
            data = proc.stdout.read(4000)  # ~0.25s of audio at 16kHz mono S16LE
            if not data:
                break
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                text = result.get("text", "").strip()
                if text:
                    print(f"[heard] {text}")
                    return text
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

    history: list = []

    brain_label = f"Claude ({MODEL})" if client is not None else "offline rules"
    input_label = "voice (Vosk)" if voice_mode else "keyboard"
    print(f"Brain: {brain_label}  |  Input: {input_label}")
    print("Commands: move forward / spin / play a song / download despacito / stop")
    if voice_mode:
        print("Speak after '[listening...]' appears. Ctrl-C to quit.\n")
    else:
        print("Type a command. Ctrl-C or 'quit' to exit.\n")

    speak("Hi, I am ready. What should I do?")

    try:
        while True:
            if voice_mode:
                try:
                    user_text = transcribe()
                except RuntimeError as e:
                    print(f"[STT error] {e}")
                    print("Falling back to keyboard input. Use --type flag to skip this message.")
                    voice_mode = False
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
        if motor_a is not None:
            motor_a.stop()
        if motor_b is not None:
            motor_b.stop()
        print("\nbye")


if __name__ == "__main__":
    main()
