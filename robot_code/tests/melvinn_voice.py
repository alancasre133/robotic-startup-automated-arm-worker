"""
MELVINN's voice — a little chirp/tone language, Project-Hail-Mary "Rocky" style.

Instead of (or alongside) words, MELVINN can express its state in musical
chirps: a rising "hm?" when it wakes, a happy trill when it grabs something, a
sad descending tone when it misses. The tones are synthesized with SoX (already
installed for the voice effects), so there are no sound files to ship — the
whole personality is a handful of note sequences below.

Audition them:
    python3 melvinn_voice.py            # play every chirp, named
    python3 melvinn_voice.py happy      # play just one

Use it from code:
    from melvinn_voice import chirp
    chirp("wake")        # MELVINN perks up
    chirp("happy")       # MELVINN got it
"""

import os
import shutil
import subprocess
import sys
import tempfile

AUDIO_DEVICE = os.environ.get("MELVINN_AUDIO", "plughw:1,0")

# Each chirp is a sequence of (frequency Hz, duration seconds) notes, played in
# order. frequency 0 = a short rest. Voiced with SoX 'pluck' (a soft plucked
# tone) so it sounds warm and musical — like Rocky's notes — not a harsh beep.
CHIRPS = {
    "wake":    [(587, 0.10), (880, 0.14)],                              # "hm?" — perks up
    "yes":     [(784, 0.08), (1047, 0.12)],                             # cheerful acknowledge
    "happy":   [(659, 0.09), (880, 0.09), (1047, 0.09), (1319, 0.16)],  # success trill (rising)
    "found":   [(880, 0.07), (1175, 0.07), (1568, 0.14)],              # excited "there it is!"
    "search":  [(698, 0.11), (622, 0.11), (740, 0.11), (659, 0.13)],   # wandering / thinking
    "working": [(784, 0.07), (0, 0.05), (784, 0.07), (0, 0.05), (784, 0.10)],  # busy beeps
    "sad":     [(698, 0.13), (523, 0.13), (349, 0.24)],                # miss / error (falling)
    "no":      [(330, 0.15), (0, 0.05), (330, 0.15)],                  # low double "nuh-uh"
    "curious": [(523, 0.10), (659, 0.10), (831, 0.18)],                # rising question
    "bye":     [(880, 0.11), (659, 0.11), (440, 0.22)],                # gentle sign-off
}


def chirp(name: str) -> bool:
    """Play one of MELVINN's chirps. Returns False if it can't (no sox/unknown)."""
    notes = CHIRPS.get(name)
    if not notes or shutil.which("sox") is None:
        return False
    tmp = tempfile.mkdtemp()
    try:
        parts = []
        for i, (freq, dur) in enumerate(notes):
            p = os.path.join(tmp, f"n{i}.wav")
            if freq <= 0:                                  # a rest
                cmd = ["sox", "-n", "-r", "22050", "-c", "1", p,
                       "synth", str(dur), "sine", "0"]
            else:
                cmd = ["sox", "-n", "-r", "22050", "-c", "1", p,
                       "synth", str(dur), "pluck", str(freq),
                       "fade", "q", "0.005", str(dur), "0.03"]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            parts.append(p)
        out = os.path.join(tmp, "chirp.wav")
        subprocess.run(["sox", *parts, out],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["aplay", "-q", "-D", AUDIO_DEVICE, out],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    if len(sys.argv) > 1:
        name = sys.argv[1]
        if not chirp(name):
            print(f"Unknown chirp '{name}'. Options: {', '.join(CHIRPS)}")
        return
    print("MELVINN's voice — playing every chirp:")
    import time
    for name in CHIRPS:
        print(f"  {name}")
        chirp(name)
        time.sleep(0.5)


if __name__ == "__main__":
    main()
