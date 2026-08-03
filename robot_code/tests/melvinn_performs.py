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
from time import sleep

# Reuse the REAL assistant capabilities so this behaves like the voice
# commands. `import assistant` (not just `from`) is needed to READ the mutable
# module globals it reassigns at runtime (_music_proc, _effect).
import assistant
from assistant import (
    MUSIC_DIR, _play_file, _stop_media,
    speak, set_face, show_text, move_joints, gripper, center_arm, robot_drive,
    ARM_CENTER_ANGLES, ARM_JOINTS,
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
# Arm vocabulary — BIG, distinct poses. Angles stay inside safe ranges tuned
# on the real robot (shoulder centre 180 / elbow 45; reaching-forward pose in
# the URDF model uses shoulder~90, so 105-180 is comfortable). Every beat moves
# the arm clearly — the earlier version barely nudged it.
# ---------------------------------------------------------------------------
POSES = {
    #             base  shoulder elbow  wrist  wrist_rotate
    "up":    dict(base=90,  shoulder=175, elbow=55,  wrist=120, wrist_rotate=90),
    "reach": dict(base=90,  shoulder=105, elbow=110, wrist=90,  wrist_rotate=90),
    "left":  dict(base=40,  shoulder=135, elbow=90,  wrist=80,  wrist_rotate=55),
    "right": dict(base=140, shoulder=135, elbow=90,  wrist=100, wrist_rotate=125),
    "bow":   dict(base=90,  shoulder=115, elbow=115, wrist=55,  wrist_rotate=90),
    "high":  dict(base=90,  shoulder=170, elbow=70,  wrist=140, wrist_rotate=90),
}


def move_to(name, t=0.7):
    move_joints(POSES[name], seconds=t)


def a_up():    move_to("up", 0.6)
def a_reach(): move_to("reach", 0.7)
def a_left():  move_to("left", 0.6)
def a_right(): move_to("right", 0.6)
def a_bow():   move_to("bow", 0.7)
def a_high():  move_to("high", 0.6)


def a_pump():                       # fist pump — big vertical shoulder swing
    for ang in (175, 120, 175, 120):
        move_joints({"shoulder": ang}, seconds=0.28)


def a_wave():                       # hand wave from the wrist
    for ang in (45, 135, 45, 135):
        move_joints({"wrist": ang}, seconds=0.25)


def a_twist():                      # wrist_rotate twist
    for ang in (25, 155, 90):
        move_joints({"wrist_rotate": ang}, seconds=0.3)


def a_sweep():                      # big slow pan across the base
    move_joints({"base": 40}, seconds=0.6)
    move_joints({"base": 140}, seconds=0.9)


def a_clap():                       # gripper "hands"
    for _ in range(2):
        gripper("open"); gripper("close")


ARM_BEATS = [a_up, a_reach, a_left, a_right, a_bow, a_high,
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

FACES = ["happy", "surprised", "love", "thinking", "neutral"]


# ---------------------------------------------------------------------------
# The performance
# ---------------------------------------------------------------------------
def _pick(pool, avoid):
    """Random choice that avoids repeating the previous pick."""
    c = random.choice(pool)
    while len(pool) > 1 and c is avoid:
        c = random.choice(pool)
    return c


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
    prev_face = prev_arm = None
    beat = 0
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
        move_to("high", 0.8)                       # arm rises to "perform"

        # --- BODY: face + BIG arm + VARIED wheels, until the track ends -----
        while _music_alive():
            beat += 1

            # every ~8 beats, flash the hook on the LCD, then back to eyes
            if beat % 8 == 0:
                show_text("I'M NOT A ROBOT"); sleep(0.8)

            f = _pick(FACES, prev_face); set_face(f); prev_face = f
            if not _music_alive():
                break

            a = _pick(ARM_BEATS, prev_arm); a(); prev_arm = a
            if not _music_alive():
                break

            if DRIVE and random.random() < 0.6:    # wheels on ~60% of beats
                random.choice(WHEEL_BEATS)()

            if beat % 5 == 0:
                set_face("blink")

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
