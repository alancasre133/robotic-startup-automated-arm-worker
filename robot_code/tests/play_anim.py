#!/usr/bin/env python3
"""Play one named LCD animation and exit.

Child-process runner for the assistant's play_animation tool: the assistant
releases the LCD, this process claims it for a few seconds, draws the
animation, and exits (a child process because the show modules import
assistant — running them inside the live assistant would create a second
module instance fighting over the LCD pins).

Run directly to test:  python3 play_anim.py witch
"""
import sys

import melvinn_performs as mp
import melvinn_cash_machine as mc

REGISTRY = {**mp.ANIM_NAMES, **mc.ANIM_NAMES}

name = " ".join(sys.argv[1:]).strip().lower()
fn = REGISTRY.get(name)
if fn is None:
    print("unknown animation:", name or "(none)")
    print("have:", ", ".join(sorted(REGISTRY)))
    sys.exit(2)
mp.run_animation(fn)
print("played", name)
