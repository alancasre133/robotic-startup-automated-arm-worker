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
MIN_SHOULDER = 174      # shoulder never goes below this (180 = straight up).
                        # Raise it further toward 180 if the arm still grazes
                        # the camera/case; lower cautiously only to reach forward.

POSES = {
    #             base  shoulder elbow  wrist  wrist_rotate
    "up":    dict(base=90,  shoulder=179, elbow=50, wrist=118, wrist_rotate=90),
    "tall":  dict(base=90,  shoulder=177, elbow=62, wrist=134, wrist_rotate=90),
    "left":  dict(base=45,  shoulder=176, elbow=62, wrist=112, wrist_rotate=55),
    "right": dict(base=135, shoulder=176, elbow=62, wrist=112, wrist_rotate=125),
    "outL":  dict(base=55,  shoulder=174, elbow=68, wrist=114, wrist_rotate=70),
    "outR":  dict(base=125, shoulder=174, elbow=68, wrist=114, wrist_rotate=110),
}


def move_to(name, t=0.7):
    move_joints(POSES[name], seconds=t)


def a_up():    move_to("up", 0.6)
def a_tall():  move_to("tall", 0.6)
def a_left():  move_to("left", 0.6)
def a_right(): move_to("right", 0.6)
def a_outL():  move_to("outL", 0.6)
def a_outR():  move_to("outR", 0.6)


def a_pump():                       # fist pump — stays HIGH, no low dip
    for ang in (179, 174, 179, 174):
        move_joints({"shoulder": ang}, seconds=0.28)


def a_wave():                       # hand wave from the wrist (kept up)
    for ang in (85, 145, 85, 145):
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
SCREEN_FACES = ["happy", "surprised", "love", "thinking", "neutral",
                "angry", "sad", "sleepy"]
SCREEN_TEXTS = ["I'M NOT A ROBOT", "NOT A ROBOT!", "BEEP BOOP", "GUESS WHAT",
                "I AM MELVINN", "WOOO!", "DANCE!", "ROBOT? ME?", "LA LA LA",
                "01001101", "BZZT!", "ENCORE!"]
EYE_DARTS = [(-16, 0), (16, 0), (0, -12), (0, 10), (-14, -8), (14, 8)]


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


def _face_show(stop):
    """Keep the LCD lively for the whole song — a stream of expressions,
    flashing text, blinks, darting eyes, head-tilts and heart-eyes. Runs in a
    daemon thread and is the ONLY thing that touches the screen during playback
    (so the main loop must not call the face). Stops when `stop` is set or the
    music ends."""
    prev = None
    i = 0
    while not stop.is_set() and _music_alive():
        i += 1
        r = random.random()
        if i % 6 == 0:                                # flash a phrase
            show_text(random.choice(SCREEN_TEXTS))
            _nap(stop, 0.9)
        elif r < 0.18:                                # blink
            set_face("blink")
        elif r < 0.34:                                # dart the eyes, then re-centre
            dx, dy = random.choice(EYE_DARTS)
            _face_frame(pupil_dx=dx, pupil_dy=dy)
            _nap(stop, 0.28)
            _face_frame(pupil_dx=0, pupil_dy=0)
        elif r < 0.46:                                # quick head-tilt bob
            _face_frame(tilt=random.choice((-12, 12)))
        elif r < 0.56:                                # heart-eyes flash
            _face_frame(hearts=True, mouth="smile")
        else:                                         # a fresh expression
            prev = _pick(SCREEN_FACES, prev)
            set_face(prev)
        _nap(stop, random.uniform(0.28, 0.6))


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
