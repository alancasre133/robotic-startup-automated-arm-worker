#!/usr/bin/env python3
"""
MELVINN performs Oliver Tree — "Cash Machine".

Thin wrapper over the melvinn_performs engine: the choreography (strictly
vertical arm spins/twists, varied wheels, and the lively LCD face show) is
identical — only the SONG, the spoken intro/outro, and the on-screen text
flashes change here.

The audio is fetched once from YouTube (top search result) to
~/music/oliver_tree_cash_machine.mp3, then played from disk.

RUN (on the Pi)
    python3 robot_code/tests/melvinn_cash_machine.py            # full show
    python3 robot_code/tests/melvinn_cash_machine.py --no-drive # desk-safe

SAFETY: the arm stays vertical (spins/twists in place), so it clears the mic +
batteries on the tier. Wheels move unless --no-drive — floor + room, please.
"""

import argparse
import os

from melvinn_performs import perform, MUSIC_DIR

# Anything yt-dlp accepts. A search grabs the top result (the official track)
# without pinning a possibly-wrong video id.
SOURCE    = "ytsearch1:Oliver Tree Cash Machine"
SONG_PATH = os.path.join(MUSIC_DIR, "oliver_tree_cash_machine.mp3")

# Spoken bookends (in the robot voice). Original lines — no song lyrics.
INTRO = "Cash Machine! MELVINN is cashing out — let's go!"
OUTRO = "Ka-ching! Show's over — MELVINN out!"

# LCD text flashes — money-themed, no lyrics (title + generic hype only).
TEXTS = ["CASH MACHINE", "KA-CHING!", "$$$", "MONEY!", "GET PAID", "CA$H",
         "MO MONEY", "BRRR!", "OLIVER TREE", "CASH OUT", "01001101", "WOO!"]


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="MELVINN performs Oliver Tree — Cash Machine.")
    ap.add_argument("--no-drive", action="store_true",
                    help="keep the wheels still (desk-safe); the arm carries it")
    args = ap.parse_args()
    perform(drive=not args.no_drive, source=SOURCE, song_path=SONG_PATH,
            intro=INTRO, outro=OUTRO, texts=TEXTS)
