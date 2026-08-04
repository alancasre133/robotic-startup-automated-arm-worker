#!/usr/bin/env python3
"""
MELVINN performs "I Am Not A Robot" — the full-body showcase.

Inspired by the Engineered Arts RoboThespians' rendition. MELVINN isn't a
humanoid — it's a 4WD chassis with ONE 6-DOF arm and an LCD face — so this
captures the SPIRIT: a robot insisting, through song, that it is Not A Robot,
using every part of its body at once.

THE AUDIO is pulled straight from THAT video (the robots' version), not the
original Marina studio track — extracted once to ~/music and played from disk
after that.

WHAT IT USES (the "all of MELVINN" ask)
    music   — the robots'-video audio plays under the whole routine
    face    — the cyan grid-eyes emote through the song (set_face)     [KEPT]
    LCD text— the hook flashes on the panel ("I'M NOT A ROBOT") (show_text)
    arm     — BIG, varied ease-in/out gestures using every joint (move_joints)
    gripper — opens/closes as "hands" on the beat (gripper)
    wheels  — a VARIED routine: rocks, wiggles, spins, quarter-turns (robot_drive)
    voice   — a spoken robot-effect intro & outro (speak + _effect)

The face is SPI and the audio is ALSA, so grid-eyes emote freely WHILE the
music plays. Only aplay-based speech can't overlap mpg123 on the exclusive
audio device (plughw:1,0) — so the spoken lines BOOKEND the song.

SAFETY
    The wheels move (rocks, wiggles, spins) — put MELVINN on the FLOOR with
    room, or pass --no-drive to keep it stationary (the arm carries the show).

RUN (on the Pi)
    python3 robot_code/tests/melvinn_performs.py            # full show
    python3 robot_code/tests/melvinn_performs.py --no-drive # desk-safe
    Ctrl-C any time — stops the music, halts the wheels, rests the arm.
"""

import argparse
import math
import os
import random
import subprocess
import threading
from time import sleep

# Reuse the REAL assistant capabilities so this behaves like the voice
# commands. `import assistant` (not just `from`) is needed to READ the mutable
# module globals it reassigns at runtime (_music_proc, _effect).
import assistant
from assistant import (
    MUSIC_DIR, _play_file, _stop_media,
    speak, set_face, show_text, move_joints, gripper, center_arm, robot_drive,
    ARM_CENTER_ANGLES, ARM_JOINTS, _face_frame,
)

# The exact clip the performance is set to — audio extracted from HERE.
VIDEO_URL = "https://www.youtube.com/watch?v=CycD3e7UaDM"
# Deterministic filename so we always find/play THIS audio (not the Marina
# studio mp3 that may also be sitting in ~/music).
SONG_PATH = os.path.join(MUSIC_DIR, "robothespians_not_a_robot.mp3")

DRIVE = True          # wheels enabled? toggled by --no-drive


# ---------------------------------------------------------------------------
# Audio: extract the robots'-video track to ~/music once (needs internet once)
# ---------------------------------------------------------------------------
def ensure_audio():
    if os.path.exists(SONG_PATH):
        return SONG_PATH
    if not _which("yt-dlp"):
        print("[perform] yt-dlp not installed — run: pip install -U --break-system-packages yt-dlp")
        return None
    os.makedirs(MUSIC_DIR, exist_ok=True)
    out = os.path.join(MUSIC_DIR, "robothespians_not_a_robot.%(ext)s")
    print("[perform] Extracting the robots'-video audio to ~/music (once)…")
    # Try player clients in order to dodge YouTube's 403s from a missing JS runtime.
    for client in ("web", "android", "tv"):
        r = subprocess.run(
            ["yt-dlp", "-x", "--audio-format", "mp3", "--audio-quality", "5",
             "--no-playlist", "--output", out,
             "--extractor-args", f"youtube:player_client={client}",
             VIDEO_URL],
            capture_output=True, text=True, timeout=300,
        )
        if r.returncode == 0 and os.path.exists(SONG_PATH):
            return SONG_PATH
    tail = (r.stderr or "").strip().splitlines()[-1:] or [""]
    print("[perform] Download failed:", tail[0])
    return SONG_PATH if os.path.exists(SONG_PATH) else None


def _which(name):
    from shutil import which
    return which(name)


def _music_alive():
    """True while the mpg123 track is still playing."""
    p = assistant._music_proc
    return p is not None and p.poll() is None


# ---------------------------------------------------------------------------
# Arm vocabulary — BIG, distinct poses, but kept HIGH. The arm fouls MELVINN's
# FRONT (the camera + case) if the shoulder drops too far forward, so every
# pose stays at/above MIN_SHOULDER. The "big movement" comes from SAFE joints —
# horizontal base sweeps, wrist waves, wrist twists, gripper claps, and high
# shoulder pumps — never from dropping the arm down onto the chassis.
# (shoulder centre 180 = straight up; smaller = tilted forward/down.)
# ---------------------------------------------------------------------------
MIN_SHOULDER = 180      # shoulder PINNED straight up — 180 IS the physical max
                        # height, it can't go higher in software. The remaining
                        # height is set by the ELBOW: higher elbow swings the
                        # forearm outward/down, so keep it at/near its 45 centre
                        # (the arm's natural, highest, chassis-clearing rest).
                        # If it still reads low, that's the arm's mounting, not
                        # these angles — it'd need remounting / a new elbow zero.
MAX_ELBOW = 50          # elbow never above this, so the forearm stays folded up.

POSES = {
    #             base  shoulder elbow  wrist  wrist_rotate
    "up":    dict(base=90,  shoulder=180, elbow=45, wrist=95,  wrist_rotate=90),
    "tall":  dict(base=90,  shoulder=180, elbow=45, wrist=105, wrist_rotate=90),
    "left":  dict(base=50,  shoulder=180, elbow=45, wrist=95,  wrist_rotate=60),
    "right": dict(base=130, shoulder=180, elbow=45, wrist=95,  wrist_rotate=120),
    "outL":  dict(base=60,  shoulder=180, elbow=48, wrist=98,  wrist_rotate=75),
    "outR":  dict(base=120, shoulder=180, elbow=48, wrist=98,  wrist_rotate=105),
}


def move_to(name, t=0.7):
    move_joints(POSES[name], seconds=t)


def a_up():    move_to("up", 0.6)
def a_tall():  move_to("tall", 0.6)
def a_left():  move_to("left", 0.6)
def a_right(): move_to("right", 0.6)
def a_outL():  move_to("outL", 0.6)
def a_outR():  move_to("outR", 0.6)


def a_pump():                       # energetic bounce — base jabs side to side (no dip)
    for ang in (75, 105, 75, 105):
        move_joints({"base": ang}, seconds=0.22)


def a_wave():                       # hand wave from the wrist (near level)
    for ang in (80, 115, 80, 115):
        move_joints({"wrist": ang}, seconds=0.25)


def a_twist():                      # wrist_rotate twist — no vertical change
    for ang in (25, 155, 90):
        move_joints({"wrist_rotate": ang}, seconds=0.3)


def a_sweep():                      # big slow pan across the base (horizontal)
    move_joints({"base": 40}, seconds=0.6)
    move_joints({"base": 140}, seconds=0.9)


def a_clap():                       # gripper "hands"
    for _ in range(2):
        gripper("open"); gripper("close")


ARM_BEATS = [a_up, a_tall, a_left, a_right, a_outL, a_outR,
             a_pump, a_wave, a_twist, a_sweep, a_clap]


# ---------------------------------------------------------------------------
# Wheel vocabulary — VARIED maneuvers so it never repeats the same rock+spin.
# All short and roughly self-cancelling so MELVINN stays near its spot.
# ---------------------------------------------------------------------------
def w_rock():
    robot_drive("forward", 0.2); robot_drive("backward", 0.2)


def w_wiggle():
    for d in ("left", "right", "left", "right"):
        robot_drive(d, 0.15)


def w_spin_r():
    robot_drive("spin", 0.5)


def w_spin_l():
    robot_drive("left", 0.5)         # counter-rotate the other way


def w_quarter():
    robot_drive(random.choice(("left", "right")), 0.3)


def w_hold():                        # let the arm carry this beat
    pass


WHEEL_BEATS = [w_rock, w_wiggle, w_spin_r, w_spin_l, w_quarter, w_hold, w_hold]

# ---------------------------------------------------------------------------
# Screen show — runs in its OWN thread so the LCD is ALWAYS busy (lots of
# expressions, flashing text, blinks, darting eyes, head-tilts, heart-eyes),
# independent of the arm's timing. The face is SPI; the arm is I2C and wheels
# are GPIO — separate hardware, so this thread never fights the arm/wheel loop.
# ---------------------------------------------------------------------------
# 21 emotional face "styles" built from _face_frame params (openness, gaze,
# tilt, brows, mouth, colour, hearts) — far beyond the handful of built-in
# expressions. Each maps a name -> kwargs passed straight to _face_frame.
EMOTIONS = {
    "neutral":    {},
    "happy":      dict(openness=1.05, mouth="smile"),
    "excited":    dict(openness=1.35, mouth="smile", color=(120, 255, 180)),
    "joyful":     dict(openness=1.15, mouth="smile", color=(255, 230, 80)),
    "love":       dict(hearts=True, mouth="smile"),
    "smitten":    dict(hearts=True, tilt=8),
    "surprised":  dict(openness=1.15, mouth="o"),
    "shocked":    dict(openness=1.45, mouth="o", pupil_dy=-3),
    "angry":      dict(openness=0.8, color=(255, 140, 40), brow=16, mouth="frown"),
    "furious":    dict(openness=0.7, color=(255, 60, 30), brow=22, mouth="frown"),
    "sad":        dict(openness=0.6, pupil_dy=10, tilt=-8, mouth="frown"),
    "worried":    dict(openness=0.8, brow=-12, mouth="frown", pupil_dy=6),
    "suspicious": dict(openness=0.5, pupil_dx=16, brow=8),
    "mischief":   dict(openness=0.85, pupil_dx=-14, brow=10, mouth="smile", tilt=6),
    "cool":       dict(openness=0.5, color=(255, 230, 80), mouth="smile"),
    "playful":    dict(openness=1.1, mouth="smile", pupil_dx=12, tilt=-6),
    "sassy":      dict(openness=0.6, pupil_dx=18, tilt=8, mouth="smile"),
    "proud":      dict(openness=1.0, brow=-6, mouth="smile", color=(255, 215, 0)),
    "thinking":   dict(pupil_dx=-14, pupil_dy=-12),
    "bored":      dict(openness=0.45, pupil_dy=8),
    "sleepy":     dict(openness=0.22, zzz=True),
}
SCREEN_TEXTS = ["I'M NOT A ROBOT", "NOT A ROBOT!", "BEEP BOOP", "GUESS WHAT",
                "I AM MELVINN", "WOOO!", "DANCE!", "ROBOT? ME?", "LA LA LA",
                "01001101", "BZZT!", "ENCORE!", "I FEEL ALIVE", "SO HAPPY!",
                "GRRR", "<3 <3 <3", "WHEEE!"]
COLORS = [(60, 210, 255), (255, 90, 150), (255, 140, 40),
          (120, 255, 180), (255, 230, 80), (170, 120, 255)]  # cyan/pink/orange/mint/yellow/purple


# ---------------------------------------------------------------------------
# The performance
# ---------------------------------------------------------------------------
def _pick(pool, avoid):
    """Random choice that avoids repeating the previous pick."""
    c = random.choice(pool)
    while len(pool) > 1 and c is avoid:
        c = random.choice(pool)
    return c


def _nap(stop, secs):
    """Sleep in small chunks so the thread reacts fast when the song ends."""
    t = 0.0
    while t < secs and not stop.is_set() and _music_alive():
        sleep(0.05)
        t += 0.05


# --- multi-frame animations (each plays several frames on the LCD) ---------
def _anim_look_around(stop):            # eyes glance around, then re-centre
    for dx, dy in ((-16, 0), (16, 0), (0, -12), (0, 12), (0, 0)):
        _face_frame(pupil_dx=dx, pupil_dy=dy)
        _nap(stop, 0.16)


def _anim_eye_roll(stop):               # pupils sweep a full circle
    for k in range(8):
        a = k / 8 * 2 * math.pi
        _face_frame(pupil_dx=int(15 * math.cos(a)), pupil_dy=int(11 * math.sin(a)))
        _nap(stop, 0.08)
    _face_frame(pupil_dx=0, pupil_dy=0)


def _anim_pulse(stop):                  # eyes grow/shrink to the beat
    for o in (1.0, 0.5, 1.3, 0.7, 1.0):
        _face_frame(openness=o)
        _nap(stop, 0.11)


def _anim_wobble(stop):                 # head shake (tilt left/right)
    for t in (-12, 12, -10, 8, 0):
        _face_frame(tilt=t)
        _nap(stop, 0.13)


def _anim_color_flash(stop):            # disco eye colours
    for c in COLORS:
        _face_frame(color=c)
        _nap(stop, 0.15)


def _anim_double_blink(stop):
    set_face("blink"); set_face("blink")


def _anim_hearts(stop):                 # heart-eyes hold
    _face_frame(hearts=True, mouth="smile")
    _nap(stop, 0.5)


def _anim_zzz(stop):                    # cheeky "bored" beat
    _face_frame(openness=0.25, zzz=True)
    _nap(stop, 0.6)


def _anim_laugh(stop):                  # belly laugh — eyes bounce with a grin
    for o in (1.15, 0.5, 1.25, 0.5, 1.15):
        _face_frame(openness=o, mouth="smile")
        _nap(stop, 0.11)


def _anim_cry(stop):                    # teary wobble — blue tint, frown
    for dy in (8, 12, 8, 13, 8):
        _face_frame(openness=0.55, pupil_dy=dy, tilt=-8, mouth="frown",
                    color=(90, 160, 255))
        _nap(stop, 0.14)


def _anim_rage(stop):                   # red, furrowed, shaking with anger
    for t in (-10, 10, -10, 10, 0):
        _face_frame(openness=0.75, color=(255, 60, 30), brow=20,
                    mouth="frown", tilt=t)
        _nap(stop, 0.10)


def _anim_swoon(stop):                  # heart-eyes swaying dreamily
    for t in (-10, 10, -6, 6, 0):
        _face_frame(hearts=True, mouth="smile", tilt=t)
        _nap(stop, 0.13)


def _anim_shock(stop):                  # eyes pop wide, jaw drops
    for o in (1.0, 1.45, 1.2, 1.45):
        _face_frame(openness=o, mouth="o", pupil_dy=-3)
        _nap(stop, 0.12)


ANIMS = [_anim_look_around, _anim_eye_roll, _anim_pulse, _anim_wobble,
         _anim_color_flash, _anim_double_blink, _anim_hearts, _anim_zzz,
         _anim_laugh, _anim_cry, _anim_rage, _anim_swoon, _anim_shock]


def _face_show(stop):
    """Keep the LCD alive the whole song — a fast stream of 21 emotional face
    styles, flashing text, and 13 multi-frame animations (laugh, cry, rage,
    swoon, shock, eye-rolls, pulses, colour flashes, hearts, zzz...). Runs in a
    daemon thread and is the ONLY thing that touches the screen during
    playback. Stops when `stop` is set or the music ends."""
    names = list(EMOTIONS)
    prev = None
    i = 0
    while not stop.is_set() and _music_alive():
        i += 1
        r = random.random()
        if i % 6 == 0:                       # flash a phrase
            show_text(random.choice(SCREEN_TEXTS))
            _nap(stop, 0.85)
        elif r < 0.5:                        # a fresh emotional face
            prev = _pick(names, prev)
            _face_frame(**EMOTIONS[prev])
        else:                                # a multi-frame animation
            random.choice(ANIMS)(stop)
        _nap(stop, random.uniform(0.22, 0.5))


def _robot_line(text):
    """Speak in the ROBOT effect — only when music isn't holding the ALSA
    device (the intro/outro bookends)."""
    old = assistant._effect
    assistant._effect = "robot"
    try:
        speak(text)
    finally:
        assistant._effect = old


def _rest():
    move_joints({j: ARM_CENTER_ANGLES[j] for j in ARM_JOINTS}, seconds=1.2)


def perform(drive=True):
    global DRIVE
    DRIVE = drive

    song = ensure_audio()
    if not song:
        print("[perform] Couldn't get the audio — aborting.")
        return
    print(f"[perform] Performing: {os.path.basename(song)}")
    if DRIVE:
        print("[perform] Wheels ENABLED — MELVINN will move. Floor + room, please!")

    finished_clean = False
    prev_arm = None
    try:
        # --- INTRO: wake up, then the spoken hook (music not started yet) ---
        center_arm()
        set_face("sleepy"); sleep(0.6)
        set_face("blink"); set_face("surprised")
        _robot_line("I… am NOT… a robot!")

        # --- MUSIC ON --- (grabs the exclusive audio device from here) ------
        err = _play_file(song)
        if err:
            print("[perform]", err)
            return
        set_face("happy")
        move_to("up", 0.8)                         # arm rises to "perform"

        # --- BODY: the LCD runs its own lively show in a background thread
        # (lots of faces + text + eye-darts) while the arm + wheels perform
        # here. Separate hardware buses, so they don't collide.
        stop_face = threading.Event()
        face_thread = threading.Thread(target=_face_show, args=(stop_face,),
                                       daemon=True)
        face_thread.start()
        try:
            while _music_alive():
                a = _pick(ARM_BEATS, prev_arm); a(); prev_arm = a
                if not _music_alive():
                    break
                if DRIVE and random.random() < 0.6:   # wheels on ~60% of beats
                    random.choice(WHEEL_BEATS)()
        finally:
            stop_face.set()
            face_thread.join(timeout=2)

        finished_clean = True

    except KeyboardInterrupt:
        print("\n[perform] Stopped by user.")
    finally:
        _stop_media()                # release the audio device
        try:
            robot_drive("stop")      # halt the wheels no matter what
        except Exception:
            pass

    # --- FINALE: bow to rest, then the spoken outro ----------------------
    set_face("love")
    _rest()
    set_face("blink")
    if finished_clean:
        _robot_line("Thank you! I hope you enjoyed the show.")
    set_face("happy")
    print("[perform] Done.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="MELVINN performs, full-body.")
    ap.add_argument("--no-drive", action="store_true",
                    help="keep the wheels still (desk-safe); the arm carries it")
    args = ap.parse_args()
    perform(drive=not args.no_drive)
