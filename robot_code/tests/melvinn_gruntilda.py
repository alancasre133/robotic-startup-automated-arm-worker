#!/usr/bin/env python3
"""
MELVINN performs "Gruntilda's Challenge" — Banjo-Kazooie: Nuts & Bolts [OST].

Thin wrapper over the melvinn_performs engine: same choreography (strictly
vertical arm spins/twists, varied wheels, lively LCD face show) — only the
SONG, spoken intro/outro, and on-screen text change here. A witch-boss
challenge theme, so the face's mischief/angry/surprised moods fit right in.

The audio is fetched once from the exact YouTube clip to
~/music/gruntildas_challenge.mp3, then played from disk.

RUN (on the Pi)
    python3 robot_code/tests/melvinn_gruntilda.py            # full show
    python3 robot_code/tests/melvinn_gruntilda.py --no-drive # desk-safe

SAFETY: the arm stays vertical (spins/twists in place), clear of the mic +
batteries on the tier. Wheels move unless --no-drive — floor + room, please.
"""

import argparse
import os

from melvinn_performs import perform, MUSIC_DIR

SOURCE    = "https://www.youtube.com/watch?v=tcxGv-8Z6_o"   # exact clip
SONG_PATH = os.path.join(MUSIC_DIR, "gruntildas_challenge.mp3")

# Spoken bookends (robot voice). Original lines — no game dialogue quoted.
INTRO = "Gruntilda's challenge — game on! MELVINN accepts!"
OUTRO = "Challenge complete — MELVINN wins! Game over!"

# LCD text flashes — game/witch themed (titles + generic hype only).
TEXTS = ["GRUNTILDA", "GAME ON!", "CHALLENGE!", "NUTS & BOLTS", "BANJO-KAZOOIE",
         "WITCH BOSS", "GRUNTY", "SPELL CAST!", "8-BIT", "PLAYER 1", "01001101",
         "VICTORY!"]


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="MELVINN performs Gruntilda's Challenge (Banjo-Kazooie OST).")
    ap.add_argument("--no-drive", action="store_true",
                    help="keep the wheels still (desk-safe); the arm carries it")
    args = ap.parse_args()
    perform(drive=not args.no_drive, source=SOURCE, song_path=SONG_PATH,
            intro=INTRO, outro=OUTRO, texts=TEXTS)
