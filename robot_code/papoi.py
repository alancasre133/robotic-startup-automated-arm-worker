"""
Face greeter — say "papoi" through the USB speaker whenever the camera sees a face.

A 5-second cooldown keeps it from repeating every frame: it greets once, then
stays quiet for 5s before it can say "papoi" again.

Run on the Pi with SYSTEM python3 (picamera2 + OpenCV are system packages):

    python3 ~/papoi.py

One-time install (OpenCV + a text-to-speech voice):

    sudo apt install -y python3-opencv opencv-data espeak-ng

The camera is single-user — stop any other camera program first
(e.g. `sudo systemctl stop camera-stream`, or Ctrl-C camera_stream.py).
Press Ctrl-C to stop.
"""

import os
import time
import shutil
import subprocess
from threading import Thread

import cv2
from picamera2 import Picamera2

WIDTH, HEIGHT = 640, 480
DETECT_SCALE = 0.5          # detect on a half-size frame => faster on the Pi 3
COOLDOWN = 5.0              # seconds of quiet after each "papoi"
AUDIO_DEVICE = "plughw:1,0"  # the USB speakerphone (card 1)
PHRASE = "papoi"

# --- face detector -----------------------------------------------------------
_dir = getattr(getattr(cv2, "data", None), "haarcascades", "")
_cascade = os.path.join(_dir, "haarcascade_frontalface_default.xml")
if not os.path.exists(_cascade):
    _cascade = "/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml"
FACE = cv2.CascadeClassifier(_cascade)
if FACE.empty():
    raise SystemExit(f"Could not load face cascade at {_cascade}")

for _tool in ("espeak-ng", "aplay"):
    if shutil.which(_tool) is None:
        print(f"WARNING: '{_tool}' not found — no sound. "
              f"Install with: sudo apt install -y espeak-ng alsa-utils")


def say(text):
    """Speak `text` through the USB speaker without blocking the loop."""
    def _run():
        try:
            tts = subprocess.Popen(["espeak-ng", text, "--stdout"],
                                   stdout=subprocess.PIPE)
            subprocess.run(["aplay", "-q", "-D", AUDIO_DEVICE], stdin=tts.stdout)
            tts.stdout.close()
            tts.wait()
        except FileNotFoundError:
            pass  # espeak-ng / aplay missing — see the warning above
    Thread(target=_run, daemon=True).start()


picam2 = Picamera2()
picam2.configure(picam2.create_video_configuration(
    main={"size": (WIDTH, HEIGHT), "format": "RGB888"}))
picam2.start()
print("Watching for faces — say hi to the camera!  (Ctrl-C to stop)")

last_papoi = 0.0
try:
    while True:
        frame = picam2.capture_array()
        small = cv2.resize(frame, None, fx=DETECT_SCALE, fy=DETECT_SCALE)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        faces = FACE.detectMultiScale(gray, scaleFactor=1.15,
                                      minNeighbors=5, minSize=(24, 24))
        now = time.time()
        if len(faces) and now - last_papoi >= COOLDOWN:
            print(f"face detected -> {PHRASE}")
            say(PHRASE)
            last_papoi = now
        time.sleep(0.05)   # small floor to keep CPU sane
except KeyboardInterrupt:
    pass
finally:
    picam2.stop()
