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
import re
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
    ARM_CENTER_ANGLES, ARM_JOINTS, _face_frame, _ensure_face,
)

# --- default performance = "I Am Not A Robot" (the RoboThespians clip) -------
# This whole file is a reusable engine: another song just calls
#   perform(source=…, song_path=…, intro=…, outro=…, texts=…)
# `source` is anything yt-dlp accepts — a URL, or "ytsearch1:<query>".
# See melvinn_cash_machine.py for a second song built on this.
DEFAULT_SOURCE    = "https://www.youtube.com/watch?v=CycD3e7UaDM"   # exact clip
DEFAULT_SONG_PATH = os.path.join(MUSIC_DIR, "robothespians_not_a_robot.mp3")
DEFAULT_INTRO     = "I… am NOT… a robot!"
DEFAULT_OUTRO     = "Thank you! I hope you enjoyed the show."

DRIVE = True          # wheels enabled? toggled by --no-drive


# ---------------------------------------------------------------------------
# Audio: extract the robots'-video track to ~/music once (needs internet once)
# ---------------------------------------------------------------------------
def ensure_audio(source, path):
    """Extract `source` (a URL, or a yt-dlp "ytsearch1:<query>") to `path` as
    mp3, once. Returns the path, or None if it couldn't be fetched."""
    if os.path.exists(path):
        return path
    if not _which("yt-dlp"):
        print("[perform] yt-dlp not installed — run: pip install -U --break-system-packages yt-dlp")
        return None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    out = os.path.splitext(path)[0] + ".%(ext)s"   # deterministic filename
    print(f"[perform] Fetching audio to {os.path.basename(path)} (once)…")
    # Try player clients in order to dodge YouTube's 403s from a missing JS runtime.
    for client in ("web", "android", "tv"):
        r = subprocess.run(
            ["yt-dlp", "-x", "--audio-format", "mp3", "--audio-quality", "5",
             "--no-playlist", "--output", out,
             "--extractor-args", f"youtube:player_client={client}",
             source],
            capture_output=True, text=True, timeout=300,
        )
        if r.returncode == 0 and os.path.exists(path):
            return path
    tail = (r.stderr or "").strip().splitlines()[-1:] or [""]
    print("[perform] Download failed:", tail[0])
    return path if os.path.exists(path) else None


def _which(name):
    from shutil import which
    return which(name)


_STANDALONE = False     # True while an animation runs OUTSIDE a show
                        # (assistant's play_animation tool via play_anim.py)


def _music_alive():
    """True while the mpg123 track is still playing. In standalone-animation
    mode there's no music to gate on, so it's always True — the animation
    just runs to its own end."""
    if _STANDALONE:
        return True
    p = assistant._music_proc
    return p is not None and p.poll() is None


def run_animation(fn, repeats=2):
    """Run one animation outside a show (no music gate). Used by play_anim.py
    for the assistant's play_animation tool."""
    global _STANDALONE
    _STANDALONE = True
    try:
        stop = threading.Event()
        for _ in range(repeats):
            fn(stop)
    finally:
        _STANDALONE = False


# ---------------------------------------------------------------------------
# Arm vocabulary — STRICTLY VERTICAL. The arm base sits up on the second tier
# right beside the mic + batteries, so the arm must NOT reach outward or dip or
# it hits the components below/around it. Every pose therefore keeps the
# vertical invariant (shoulder=180 straight up, elbow=45, wrist=90 — its exact
# chassis-clearing centre); ALL movement comes from rotating the whole vertical
# arm about the BASE and twisting WRIST_ROTATE, plus the gripper. The arm spins
# and twists in place above its own footprint and can't strike anything.
# ---------------------------------------------------------------------------
VERT = dict(shoulder=180, elbow=45, wrist=90)   # the "keep it high" invariant

POSES = {
    #            base  + vertical invariant + wrist_rotate
    "up":     dict(base=90,  wrist_rotate=90,  **VERT),
    "left":   dict(base=48,  wrist_rotate=60,  **VERT),
    "right":  dict(base=132, wrist_rotate=120, **VERT),
    "farL":   dict(base=22,  wrist_rotate=70,  **VERT),
    "farR":   dict(base=158, wrist_rotate=110, **VERT),
    "twistL": dict(base=90,  wrist_rotate=28,  **VERT),
    "twistR": dict(base=90,  wrist_rotate=152, **VERT),
}


def move_to(name, t=0.6):
    move_joints(POSES[name], seconds=t)


def a_up():     move_to("up", 0.5)
def a_left():   move_to("left", 0.5)
def a_right():  move_to("right", 0.5)
def a_farL():   move_to("farL", 0.6)
def a_farR():   move_to("farR", 0.6)
def a_twistL(): move_to("twistL", 0.5)
def a_twistR(): move_to("twistR", 0.5)


def a_spin():                       # slow full-width base pan (arm stays vertical)
    move_joints({"base": 20}, seconds=0.7)
    move_joints({"base": 160}, seconds=1.1)


def a_shimmy():                     # quick side-to-side base wiggle
    for ang in (70, 110, 70, 110, 90):
        move_joints({"base": ang}, seconds=0.16)


def a_screw():                      # continuous wrist twist (the "cash" spin)
    for ang in (25, 155, 25, 155, 90):
        move_joints({"wrist_rotate": ang}, seconds=0.22)


def a_bounce():                     # energetic base jabs
    for ang in (80, 100, 80, 100):
        move_joints({"base": ang}, seconds=0.18)


def a_clap():                       # gripper "hands"
    for _ in range(3):
        gripper("open"); gripper("close")


def a_grab():                       # "counting cash" — twist + grip together
    for ang in (55, 125):
        move_joints({"wrist_rotate": ang}, seconds=0.2)
        gripper("close"); gripper("open")


ARM_BEATS = [a_up, a_left, a_right, a_farL, a_farR, a_twistL, a_twistR,
             a_spin, a_shimmy, a_screw, a_bounce, a_clap, a_grab]


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
# Emotional face styles come from the assistant's shared _EXPRESSIONS table
# (the extended moods were promoted there so they also work by voice —
# "look suspicious"). Each entry is kwargs passed straight to _face_frame.
EMOTIONS = dict(assistant._EXPRESSIONS)
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


# --- picture animations (little scenes drawn straight to the LCD) -----------
# These bypass the grid-eye face and draw ICONS (moon, witch, ghost, bat...)
# onto the panel with PIL, then push the frame. Same LCD, same thread.
_BG = (6, 10, 16)


def _canvas():
    """Fresh dark LCD frame -> (face, img, draw), or (None, None, None)."""
    face = _ensure_face()
    if face is None:
        return None, None, None
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (face.width, face.height), _BG)
    return face, img, ImageDraw.Draw(img)


def _star(d, x, y, r, col):
    d.polygon([(x, y-r), (x+r//3, y-r//3), (x+r, y), (x+r//3, y+r//3),
               (x, y+r), (x-r//3, y+r//3), (x-r, y), (x-r//3, y-r//3)], fill=col)


def _crescent(d, cx, cy, r, col):
    d.ellipse((cx-r, cy-r, cx+r, cy+r), fill=col)
    d.ellipse((cx-r-26, cy-r, cx+r-26, cy+r), fill=_BG)   # carve the crescent


def _witch(d, x, y):
    robe = (35, 25, 55)
    d.line((x-42, y+6, x+42, y-6), fill=(120, 80, 40), width=5)       # broomstick
    for dy in (-8, -3, 2, 7):                                         # bristles
        d.line((x+42, y-6, x+60, y-6+dy), fill=(180, 140, 60), width=2)
    d.polygon([(x-16, y-4), (x+14, y-4), (x, y-46)], fill=robe)       # robe
    d.line((x-2, y-28, x-24, y-12), fill=robe, width=5)               # arm
    d.ellipse((x-9, y-58, x+9, y-40), fill=(150, 200, 120))          # green face
    d.line((x-18, y-56, x+18, y-56), fill=(18, 12, 28), width=5)     # hat brim
    d.polygon([(x-13, y-56), (x+13, y-56), (x-2, y-92)], fill=(18, 12, 28))  # cone


def _ghost(d, x, y):
    w, h, col = 62, 92, (235, 240, 255)
    d.pieslice((x-w//2, y-h//2, x+w//2, y-h//2+w), 180, 360, fill=col)  # dome top
    d.rectangle((x-w//2, y-h//2+w//2, x+w//2, y+h//2), fill=col)        # body
    for k in range(3):                                                 # wavy hem
        bx = x - w//2 + k*(w//3)
        d.pieslice((bx, y+h//2-14, bx+w//3, y+h//2+10), 0, 180, fill=_BG)
    d.ellipse((x-15, y-14, x-5, y+2), fill=(25, 20, 45))              # eyes
    d.ellipse((x+5, y-14, x+15, y+2), fill=(25, 20, 45))
    d.ellipse((x-6, y+8, x+6, y+22), fill=(25, 20, 45))              # mouth


def _bat(d, x, y, up):
    col = (30, 25, 45)
    wy = -14 if up else 8
    d.ellipse((x-7, y-9, x+7, y+9), fill=col)                        # body
    d.polygon([(x-6, y), (x-36, y+wy), (x-20, y+2), (x-30, y+12)], fill=col)
    d.polygon([(x+6, y), (x+36, y+wy), (x+20, y+2), (x+30, y+12)], fill=col)
    d.polygon([(x-4, y-9), (x-9, y-18), (x-1, y-10)], fill=col)      # ears
    d.polygon([(x+4, y-9), (x+9, y-18), (x+1, y-10)], fill=col)


def _anim_moon(stop):               # crescent moon + twinkling stars
    face = _ensure_face()
    if face is None: return
    import random as _R
    W, H = face.width, face.height
    stars = [(_R.randint(6, W-6), _R.randint(6, H-6)) for _ in range(16)]
    for phase in range(4):
        f, img, d = _canvas()
        if not f: return
        _crescent(d, W//2 + 22, H//2, 66, (245, 235, 175))
        for i, (sx, sy) in enumerate(stars):
            if (i + phase) % 3:
                d.ellipse((sx-2, sy-2, sx+2, sy+2), fill=(255, 255, 255))
        f.display(img)
        _nap(stop, 0.3)
        if stop.is_set() or not _music_alive(): return


def _anim_witch(stop):              # witch on a broom flies across the moon
    face = _ensure_face()
    if face is None: return
    W, H = face.width, face.height
    for i, x in enumerate(range(-50, W + 60, 34)):
        f, img, d = _canvas()
        if not f: return
        d.ellipse((W//2-70, 4, W//2+70, 144), fill=(230, 220, 160))   # full moon
        _witch(d, x, H//2 + (6 if i % 2 else -6))
        f.display(img)
        _nap(stop, 0.12)
        if stop.is_set() or not _music_alive(): return


def _anim_ghost(stop):              # ghost bobbing / peeking
    face = _ensure_face()
    if face is None: return
    W, H = face.width, face.height
    for i in range(6):
        f, img, d = _canvas()
        if not f: return
        _ghost(d, W//2 + int(18*math.sin(i)), H//2 + int(10*math.sin(i*1.6)))
        f.display(img)
        _nap(stop, 0.16)
        if stop.is_set() or not _music_alive(): return


def _anim_bat(stop):                # bat flaps across a little moon
    face = _ensure_face()
    if face is None: return
    W, H = face.width, face.height
    for i, x in enumerate(range(-40, W + 50, 28)):
        f, img, d = _canvas()
        if not f: return
        _crescent(d, W-46, 44, 30, (240, 230, 170))
        _bat(d, x, H//2 + int(14*math.sin(i*0.8)), up=i % 2)
        f.display(img)
        _nap(stop, 0.1)
        if stop.is_set() or not _music_alive(): return


def _anim_spell(stop):              # lightning / spell zap flashes
    for k in range(5):
        f, img, d = _canvas()
        if not f: return
        W, H = f.width, f.height
        col = (255, 240, 120) if k % 2 else (185, 120, 255)
        d.line([(W//2, 6), (W//2-26, H//2-18), (W//2+12, H//2+4), (W//2-16, H-6)],
               fill=col, width=9)
        f.display(img)
        _nap(stop, 0.1)
        if stop.is_set() or not _music_alive(): return


def _anim_starfield(stop):          # twinkling starfield with big stars
    face = _ensure_face()
    if face is None: return
    import random as _R
    W, H = face.width, face.height
    pts = [(_R.randint(8, W-8), _R.randint(8, H-8), _R.randint(3, 7)) for _ in range(20)]
    for phase in range(4):
        f, img, d = _canvas()
        if not f: return
        for i, (sx, sy, sr) in enumerate(pts):
            if (i + phase) % 2 == 0:
                _star(d, sx, sy, sr, (255, 255, 190))
            else:
                d.ellipse((sx-1, sy-1, sx+1, sy+1), fill=(120, 120, 150))
        f.display(img)
        _nap(stop, 0.26)
        if stop.is_set() or not _music_alive(): return


ANIMS = [_anim_look_around, _anim_eye_roll, _anim_pulse, _anim_wobble,
         _anim_color_flash, _anim_double_blink, _anim_hearts, _anim_zzz,
         _anim_laugh, _anim_cry, _anim_rage, _anim_swoon, _anim_shock,
         _anim_moon, _anim_witch, _anim_ghost, _anim_bat, _anim_spell,
         _anim_starfield]

EXTRA_ANIMS = []        # per-song extra picture animations, set by perform()

# Friendly name -> animation, for standalone playback (assistant's
# play_animation tool via play_anim.py). melvinn_cash_machine adds its own.
ANIM_NAMES = {
    "look around": _anim_look_around, "eye roll": _anim_eye_roll,
    "pulse": _anim_pulse, "wobble": _anim_wobble,
    "color flash": _anim_color_flash, "hearts": _anim_hearts,
    "zzz": _anim_zzz, "laugh": _anim_laugh, "cry": _anim_cry,
    "rage": _anim_rage, "swoon": _anim_swoon, "shock": _anim_shock,
    "moon": _anim_moon, "witch": _anim_witch, "ghost": _anim_ghost,
    "bat": _anim_bat, "spell": _anim_spell, "starfield": _anim_starfield,
}


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
            random.choice(ANIMS + EXTRA_ANIMS)(stop)
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


def perform(drive=True, source=DEFAULT_SOURCE, song_path=DEFAULT_SONG_PATH,
            intro=DEFAULT_INTRO, outro=DEFAULT_OUTRO, texts=None, extra_anims=None):
    global DRIVE, SCREEN_TEXTS, EXTRA_ANIMS
    DRIVE = drive
    if texts:
        SCREEN_TEXTS = texts        # the LCD thread reads these module globals
    EXTRA_ANIMS = extra_anims or []

    song = ensure_audio(source, song_path)
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
        _robot_line(intro)

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
        _robot_line(outro)
    set_face("happy")
    print("[perform] Done.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="MELVINN performs, full-body.")
    ap.add_argument("--no-drive", action="store_true",
                    help="keep the wheels still (desk-safe); the arm carries it")
    ap.add_argument("--song", default="", metavar="QUERY",
                    help="perform any track (fetched by YouTube search) "
                         "instead of the default 'I Am Not A Robot' show")
    args = ap.parse_args()
    if args.song:
        slug = re.sub(r"[^a-z0-9]+", "_", args.song.lower()).strip("_") or "song"
        perform(drive=not args.no_drive,
                source=f"ytsearch1:{args.song}",
                song_path=os.path.join(MUSIC_DIR, slug + ".mp3"),
                intro=f"Now performing: {args.song}!",
                outro="That was the show. Thank you, thank you!",
                texts=[args.song.upper()[:14], "LET'S GO!", "WOOO!", "DANCE!",
                       "MELVINN LIVE", "ENCORE!", "01001101"])
    else:
        perform(drive=not args.no_drive)
