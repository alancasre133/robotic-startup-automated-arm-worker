#!/usr/bin/env python3
"""
MELVINN performs Oliver Tree — "Alien Boy".

Thin wrapper over the melvinn_performs engine (same vertical-arm
choreography, varied wheels, lively LCD show) with an ALIEN-themed extra
animation set: a UFO flyby, a pixel alien head, a ringed planet, and a UFO
abducting pixel-art Oliver in its tractor beam (the sprite is reused from
melvinn_cash_machine).

The audio is fetched once to ~/music/oliver_tree_alien_boy.mp3, then played
from disk.

RUN (on the Pi)
    python3 robot_code/tests/melvinn_alien_boy.py            # full show
    python3 robot_code/tests/melvinn_alien_boy.py --no-drive # desk-safe
"""

import argparse
import math
import os
import random

from melvinn_performs import perform, MUSIC_DIR, _canvas, _nap, _music_alive
# Reuse the pixel-art machinery + the album-cover Oliver sprite
from melvinn_cash_machine import _sprite, _anim_oliver, OLIVER, OCMAP

SOURCE    = "ytsearch1:Oliver Tree Alien Boy"
SONG_PATH = os.path.join(MUSIC_DIR, "oliver_tree_alien_boy.mp3")

# Spoken bookends (robot voice). Original lines — no lyrics.
INTRO = "Alien Boy! MELVINN is taking off — beam me up!"
OUTRO = "MELVINN has left the planet. Goodbye, earthlings!"

# LCD text flashes — alien/space themed (title + generic hype only).
TEXTS = ["ALIEN BOY", "OLIVER TREE", "BEAM ME UP", "UFO!", "TAKE OFF",
         "MOTHERSHIP", "SPACE BOY", "NOT FROM HERE", "EARTHLINGS!",
         "01001101", "WHEEE!", "ORBIT!"]

# --- alien-themed picture animations ----------------------------------------
GREEN  = (110, 220, 120)
STEEL  = (170, 180, 200)
DOME   = (120, 220, 255)
BEAM   = (255, 240, 130)

# pixel alien head: green skin, big black almond eyes, tiny mouth
ALIEN = [
    "....GGGG....",
    "..GGGGGGGG..",
    ".GGGGGGGGGG.",
    "GGGGGGGGGGGG",
    "GKKKGGGGKKKG",
    "GKKKKGGKKKKG",
    "GGKKGGGGKKGG",
    ".GGGGGGGGGG.",
    ".GGGGGGGGGG.",
    "..GGKKKKGG..",
    "..GGGGGGGG..",
    "...GGGGGG...",
]
ACMAP = {"G": GREEN, "K": (10, 10, 14)}


def _ufo(d, x, y, lights_on=True):
    """Classic saucer: steel disc, glass dome, a row of belly lights."""
    d.ellipse((x-46, y-10, x+46, y+14), fill=STEEL, outline=(90, 100, 120), width=2)
    d.ellipse((x-20, y-26, x+20, y+2), fill=DOME, outline=(80, 160, 200), width=2)
    if lights_on:
        for lx in (-30, -10, 10, 30):
            d.ellipse((x+lx-4, y+4, x+lx+4, y+12), fill=BEAM)


def _stars(d, W, H, n=14, seed=7):
    rng = random.Random(seed)
    for _ in range(n):
        sx, sy = rng.randint(4, W-4), rng.randint(4, H-4)
        d.ellipse((sx-1, sy-1, sx+1, sy+1), fill=(220, 220, 240))


def _anim_ufo(stop):                # saucer flies across, lights blinking
    f0, _, _ = _canvas()
    if not f0:
        return
    W, H = f0.width, f0.height
    for i, x in enumerate(range(-50, W + 60, 26)):
        f, img, d = _canvas()
        if not f:
            return
        _stars(d, W, H)
        _ufo(d, x, H//2 + int(12 * math.sin(i * 0.9)), lights_on=i % 2 == 0)
        f.display(img)
        _nap(stop, 0.11)
        if stop.is_set() or not _music_alive():
            return


def _anim_alien(stop):              # alien head bobs and blinks
    f0, _, _ = _canvas()
    if not f0:
        return
    W, H = f0.width, f0.height
    blink = [r.replace("K", "G") for r in ALIEN]     # eyes-closed frame
    for i in range(6):
        f, img, d = _canvas()
        if not f:
            return
        _stars(d, W, H, seed=3)
        rows = blink if i == 4 else ALIEN
        _sprite(d, rows, ACMAP, W//2, H//2 + (6 if i % 2 else -6), 14)
        f.display(img)
        _nap(stop, 0.18)
        if stop.is_set() or not _music_alive():
            return


def _anim_abduction(stop):          # UFO beams pixel Oliver up
    f0, _, _ = _canvas()
    if not f0:
        return
    W, H = f0.width, f0.height
    for i in range(8):
        f, img, d = _canvas()
        if not f:
            return
        _stars(d, W, H, seed=11)
        d.polygon([(W//2 - 12, 36), (W//2 + 12, 36),
                   (W//2 + 52, H), (W//2 - 52, H)], fill=(70, 66, 40))
        d.polygon([(W//2 - 8, 36), (W//2 + 8, 36),
                   (W//2 + 34, H), (W//2 - 34, H)], fill=BEAM)
        oy = H - 30 - i * 22                          # Oliver rises to the ship
        _sprite(d, OLIVER, OCMAP, W//2, oy, 4)
        _ufo(d, W//2, 26, lights_on=i % 2 == 0)
        f.display(img)
        _nap(stop, 0.16)
        if stop.is_set() or not _music_alive():
            return


def _anim_planet(stop):             # ringed planet drifting among stars
    f0, _, _ = _canvas()
    if not f0:
        return
    W, H = f0.width, f0.height
    for i in range(5):
        f, img, d = _canvas()
        if not f:
            return
        _stars(d, W, H, seed=5)
        cx, cy = W//2 + i*4 - 8, H//2
        d.ellipse((cx-42, cy-42, cx+42, cy+42), fill=(200, 140, 90))
        d.ellipse((cx-32, cy-30, cx+6, cy-6), fill=(220, 170, 120))   # shading
        d.arc((cx-64, cy-18, cx+64, cy+30), 15, 195, fill=(230, 210, 160), width=6)
        f.display(img)
        _nap(stop, 0.22)
        if stop.is_set() or not _music_alive():
            return


ALIEN_ANIMS = [_anim_ufo, _anim_alien, _anim_abduction, _anim_planet,
               _anim_oliver]

# For standalone playback (assistant's play_animation tool via play_anim.py).
ANIM_NAMES = {"ufo": _anim_ufo, "alien": _anim_alien,
              "abduction": _anim_abduction, "planet": _anim_planet}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="MELVINN performs Oliver Tree — Alien Boy.")
    ap.add_argument("--no-drive", action="store_true",
                    help="keep the wheels still (desk-safe); the arm carries it")
    args = ap.parse_args()
    perform(drive=not args.no_drive, source=SOURCE, song_path=SONG_PATH,
            intro=INTRO, outro=OUTRO, texts=TEXTS, extra_anims=ALIEN_ANIMS)
