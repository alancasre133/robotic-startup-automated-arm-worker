#!/usr/bin/env python3
"""
MELVINN performs Oliver Tree — "Cash Machine".

Thin wrapper over the melvinn_performs engine: same choreography (strictly
vertical arm spins/twists, varied wheels, lively LCD face show) — this file
swaps in the SONG, the spoken intro/outro, the on-screen text flashes, AND a
set of MONEY-themed picture animations (pulsing $, raining coins, a money bag,
fluttering bills) that get mixed into the LCD show for this track only.

The audio is fetched once to ~/music/oliver_tree_cash_machine.mp3, then played
from disk.

RUN (on the Pi)
    python3 robot_code/tests/melvinn_cash_machine.py            # full show
    python3 robot_code/tests/melvinn_cash_machine.py --no-drive # desk-safe
"""

import argparse
import math
import os
import random

# Reuse the engine + its LCD drawing helpers (_canvas builds a fresh frame,
# _nap sleeps in small chunks, _music_alive gates the loop).
from melvinn_performs import perform, MUSIC_DIR, _canvas, _nap, _music_alive

SOURCE    = "ytsearch1:Oliver Tree Cash Machine"
SONG_PATH = os.path.join(MUSIC_DIR, "oliver_tree_cash_machine.mp3")

INTRO = "Cash Machine! MELVINN is cashing out — let's go!"
OUTRO = "Ka-ching! Show's over — MELVINN out!"

TEXTS = ["CASH MACHINE", "KA-CHING!", "$$$", "MONEY!", "GET PAID", "CA$H",
         "MO MONEY", "BRRR!", "OLIVER TREE", "CASH OUT", "01001101", "WOO!"]

# --- money-themed picture animations ----------------------------------------
GREEN = (60, 200, 90)
GOLD  = (255, 205, 60)


def _font(size):
    from PIL import ImageFont
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "arialbd.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _coin(d, x, y, r):
    d.ellipse((x-r, y-r, x+r, y+r), fill=GOLD, outline=(180, 130, 20), width=2)
    d.text((x, y), "$", font=_font(max(10, int(r*1.3))), fill=(150, 100, 10),
           anchor="mm")


def _anim_dollar(stop):             # big pulsing green $
    for s in (120, 175, 140, 195, 150):
        f, img, d = _canvas()
        if not f:
            return
        d.text((f.width//2, f.height//2), "$", font=_font(s), fill=GREEN,
               anchor="mm")
        f.display(img)
        _nap(stop, 0.13)
        if stop.is_set() or not _music_alive():
            return


def _anim_coins(stop):              # gold coins raining down
    f0, _, _ = _canvas()
    if not f0:
        return
    W, H = f0.width, f0.height
    coins = [[random.randint(15, W-15), random.randint(-H, 0),
              random.randint(12, 20)] for _ in range(9)]
    for _ in range(10):
        f, img, d = _canvas()
        if not f:
            return
        for c in coins:
            _coin(d, c[0], c[1], c[2])
            c[1] += 34
            if c[1] > H + 20:
                c[1] = random.randint(-40, -10)
                c[0] = random.randint(15, W-15)
        f.display(img)
        _nap(stop, 0.11)
        if stop.is_set() or not _music_alive():
            return


def _anim_moneybag(stop):           # a tied sack with a $ on it, wobbling
    for wob in (-6, 6, -4, 4, 0):
        f, img, d = _canvas()
        if not f:
            return
        cx, cy = f.width//2 + wob, f.height//2 + 12
        d.ellipse((cx-56, cy-38, cx+56, cy+58), fill=(150, 110, 60))     # sack
        d.polygon([(cx-26, cy-38), (cx+26, cy-38), (cx+16, cy-64),
                   (cx-16, cy-64)], fill=(120, 88, 46))                  # neck
        d.line((cx-26, cy-38, cx+26, cy-38), fill=(90, 65, 34), width=6) # tie
        d.text((cx, cy+8), "$", font=_font(66), fill=GREEN, anchor="mm")
        f.display(img)
        _nap(stop, 0.14)
        if stop.is_set() or not _music_alive():
            return


def _anim_cashrain(stop):           # dollar bills fluttering down
    f0, _, _ = _canvas()
    if not f0:
        return
    W, H = f0.width, f0.height
    bills = [[random.randint(24, W-24), random.randint(-H, 0)] for _ in range(7)]
    for t in range(10):
        f, img, d = _canvas()
        if not f:
            return
        for b in bills:
            bx = b[0] + int(11 * math.sin((b[1] + t*20) / 30.0))   # sway
            d.rounded_rectangle((bx-26, b[1]-14, bx+26, b[1]+14), radius=4,
                                fill=(70, 150, 90), outline=(150, 220, 160),
                                width=2)
            d.text((bx, b[1]), "$", font=_font(20), fill=(225, 245, 225),
                   anchor="mm")
            b[1] += 30
            if b[1] > H + 20:
                b[1] = random.randint(-40, -10)
                b[0] = random.randint(24, W-24)
        f.display(img)
        _nap(stop, 0.12)
        if stop.is_set() or not _music_alive():
            return


MONEY_ANIMS = [_anim_dollar, _anim_coins, _anim_moneybag, _anim_cashrain]


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="MELVINN performs Oliver Tree — Cash Machine.")
    ap.add_argument("--no-drive", action="store_true",
                    help="keep the wheels still (desk-safe); the arm carries it")
    args = ap.parse_args()
    perform(drive=not args.no_drive, source=SOURCE, song_path=SONG_PATH,
            intro=INTRO, outro=OUTRO, texts=TEXTS, extra_anims=MONEY_ANIMS)
