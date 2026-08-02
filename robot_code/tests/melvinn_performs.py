#!/usr/bin/env python3
"""
MELVINN performs a song — the full-body showcase.

Inspired by the Engineered Arts RoboThespians' rendition of Marina's
"I Am Not A Robot" (two humanoids theatrically lip-syncing with head tilts
and arm gestures). MELVINN isn't a humanoid — it's a 4WD chassis with ONE
6-DOF arm and an LCD face — so this doesn't copy the poses 1:1. It captures the
*spirit*: a robot insisting, through song, that it is Not A Robot, using every
part of its body at once.

WHAT IT USES (the "all of MELVINN" ask)
    music   — the track plays underneath the whole routine (play_song path)
    face    — the cyan grid-eyes emote through verses/choruses (set_face)
    LCD text— the hook flashes on the panel ("I'M NOT A ROBOT") (show_text)
    arm     — coordinated ease-in/out gestures: sways, nods, reaches (move_joints)
    gripper — opens/closes as "hands" on the beat (gripper)
    wheels  — little forward/back rocks + a chorus spin flourish (robot_drive)
    voice   — a spoken intro & outro line, in the ROBOT effect (speak + _effect)

ONE HARDWARE TRUTH honored here
    AUDIO_DEVICE ("plughw:1,0") is an EXCLUSIVE ALSA device — mpg123 (music)
    grabs it, so aplay-based speech/sound-effects CANNOT overlap the music
    (they'd get "Device or resource busy", exactly the note in _play_file).
    So the spoken lines BOOKEND the song; the silent body (face/arm/wheels)
    carries the middle. Everything visual runs fine over the music.

SAFETY
    The wheels sway and do a short spin — put MELVINN on the FLOOR with room,
    or pass --no-drive to keep it stationary (the arm bobs instead).

RUN (on the Pi)
    python3 robot_code/tests/melvinn_performs.py            # full show
    python3 robot_code/tests/melvinn_performs.py --no-drive # desk-safe
    Ctrl-C any time — it stops the music, halts the wheels, and rests the arm.

The song auto-downloads to ~/music on first run (needs internet once); after
that it plays from disk.
"""

import argparse
import os
from glob import glob
from time import sleep

# Reuse the REAL assistant capabilities so this behaves exactly like the voice
# commands. `import assistant` (not just `from`) is needed to READ the mutable
# module globals it reassigns at runtime (_music_proc, _effect).
import assistant
from assistant import (
    MUSIC_DIR, _download_by_title, _play_file, _stop_media,
    speak, set_face, show_text, move_joints, gripper, center_arm, robot_drive,
    ARM_CENTER_ANGLES, ARM_JOINTS,
)

SONG_HINT = "not a robot"                         # match an existing local file
SONG_SEARCH = "Marina and the Diamonds - I Am Not A Robot"

DRIVE = True          # wheels enabled? toggled by --no-drive


# ---------------------------------------------------------------------------
# Song acquisition (non-interactive — no voice/keyboard pick)
# ---------------------------------------------------------------------------
def find_or_get_song():
    os.makedirs(MUSIC_DIR, exist_ok=True)

    def local():
        return sorted(
            s for s in glob(os.path.join(MUSIC_DIR, "*.mp3"))
            if SONG_HINT in os.path.basename(s).lower()
        )

    hits = local()
    if hits:
        return hits[0]
    print("[perform] Song not in ~/music yet — downloading (needs internet)…")
    print("[perform]", _download_by_title(SONG_SEARCH))
    hits = local()
    return hits[0] if hits else None


def _music_alive():
    """True while the mpg123 track is still playing."""
    p = assistant._music_proc
    return p is not None and p.poll() is None


# ---------------------------------------------------------------------------
# Gesture vocabulary — all angles kept near the tuned centres so the arm
# clears the chassis (shoulder centre 180, elbow 45, rest 90). Tune freely.
# ---------------------------------------------------------------------------
def g(targets, t=0.8):
    move_joints(targets, seconds=t)


# --- verse moves: calm, introspective (the song's quieter verses) ----------
def sway_left():
    set_face("thinking"); g({"base": 60, "wrist_rotate": 65, "wrist": 80}, 0.8)


def sway_right():
    set_face("neutral"); g({"base": 120, "wrist_rotate": 115, "wrist": 100}, 0.8)


def nod():
    set_face("neutral"); g({"wrist": 60}, 0.4); g({"wrist": 110}, 0.4)


def peek():
    set_face("blink"); g({"base": 90, "wrist_rotate": 90, "wrist": 90}, 0.6)


VERSE = [sway_left, nod, sway_right, peek]


# --- chorus moves: the "I'm not a robot" hook, big and bright --------------
def hook_text():
    show_text("I'M NOT A ROBOT")     # flashes the hook on the LCD panel
    sleep(0.8)


def reach():
    set_face("love"); g({"shoulder": 150, "elbow": 75, "wrist": 115}, 0.9)


def clap():
    set_face("happy")
    for _ in range(2):               # gripper "hands" on the beat
        gripper("open"); gripper("close")


def cheer():
    set_face("surprised"); g({"base": 55}, 0.5); g({"base": 125}, 0.5)


def rock():
    set_face("happy")
    if DRIVE:                        # tiny forward/back rock — returns to place
        robot_drive("forward", 0.22); robot_drive("backward", 0.22)
    else:
        g({"shoulder": 165, "elbow": 55}, 0.5)   # bob the arm instead


def spin_flourish():
    set_face("love")
    if DRIVE:
        robot_drive("spin", 0.5)     # short stage spin
    g({"wrist_rotate": 40}, 0.4); g({"wrist_rotate": 140}, 0.4)


CHORUS = [hook_text, reach, clap, cheer, rock, spin_flourish]


# ---------------------------------------------------------------------------
# The performance
# ---------------------------------------------------------------------------
def _run(moves):
    """Play a block of moves, bailing the moment the track ends."""
    for m in moves:
        if not _music_alive():
            return False
        m()
    return True


def _robot_line(text):
    """Speak a line in the ROBOT effect (only safe when music isn't holding
    the ALSA device — i.e. the intro/outro bookends)."""
    old = assistant._effect
    assistant._effect = "robot"
    try:
        speak(text)
    finally:
        assistant._effect = old


def _rest():
    """Return the arm to its centre pose (the 'bow')."""
    g({j: ARM_CENTER_ANGLES[j] for j in ARM_JOINTS}, 1.2)


def perform(drive=True):
    global DRIVE
    DRIVE = drive

    song = find_or_get_song()
    if not song:
        print("[perform] Could not get the song — aborting.")
        return
    print(f"[perform] Performing: {os.path.basename(song)}")
    if DRIVE:
        print("[perform] Wheels ENABLED — MELVINN will sway & spin. Floor, room, go!")

    finished_clean = False
    try:
        # --- INTRO: wake up, then the spoken hook (music not started yet) ---
        center_arm()
        set_face("sleepy"); sleep(0.6)
        set_face("blink"); set_face("surprised")
        _robot_line("I… am NOT… a robot!")

        # --- MUSIC ON --- (grabs the exclusive audio device from here on) ---
        err = _play_file(song)
        if err:
            print("[perform]", err)
            return
        set_face("happy")
        g({"shoulder": 155, "elbow": 70}, 0.8)      # arm rises to "perform"

        # --- BODY: verse/chorus cycles until the track ends -----------------
        while _music_alive():
            if not _run(VERSE):
                break
            if not _run(CHORUS):
                break
        finished_clean = True

    except KeyboardInterrupt:
        print("\n[perform] Stopped by user.")
    finally:
        _stop_media()                # release the audio device
        try:
            robot_drive("stop")      # halt the wheels no matter what
        except Exception:
            pass

    # --- FINALE / cleanup: bow to rest, then the spoken outro -------------
    set_face("love")
    _rest()
    set_face("blink")
    if finished_clean:
        _robot_line("Thank you! I hope you enjoyed the show.")
    set_face("happy")
    print("[perform] Done.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="MELVINN performs a song, full-body.")
    ap.add_argument("--no-drive", action="store_true",
                    help="keep the wheels still (desk-safe); the arm bobs instead")
    args = ap.parse_args()
    perform(drive=not args.no_drive)
