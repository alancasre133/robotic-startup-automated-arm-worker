#!/usr/bin/env python3
"""
Play a video on MELVINN's ST7789 face screen with audio -- as a STANDALONE
process so the assistant's input loop stays fully responsive (the decode +
per-frame SPI blit never touches the assistant's Python interpreter).

The assistant releases the face screen, launches this, and kills it on
stop/quit. One ffmpeg decodes video to RGB565 frames (blitted to the panel)
and audio to ALSA on the same clock.

Usage:
    python3 video_play.py <video_path>
Env:
    MELVINN_AUDIO  ALSA device (default plughw:1,0)
    MELVINN_VFPS   frames per second (default 8)
"""
import os
import shutil
import signal
import subprocess
import sys

from st7789_raw import ST7789Raw

AUDIO_DEVICE = os.environ.get("MELVINN_AUDIO", "plughw:1,0")
FPS = int(os.environ.get("MELVINN_VFPS", "8"))

if len(sys.argv) < 2:
    print("usage: video_play.py <video_path>", file=sys.stderr)
    sys.exit(2)
path = sys.argv[1]

disp = ST7789Raw(rotation=90)
W, H = disp.width, disp.height
frame_bytes = W * H * 2
vf = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
      f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,fps={FPS}")
nice = ["nice", "-n", "15"] if shutil.which("nice") else []
proc = subprocess.Popen(
    # -nostdin: DON'T read the terminal's stdin. Without it ffmpeg listens for
    # interactive keypresses and STEALS the keystrokes meant for the
    # assistant's input() prompt -- the real "can't type while a video plays"
    # bug. stdin=DEVNULL belt-and-suspenders in case the flag is unsupported.
    [*nice, "ffmpeg", "-nostdin", "-loglevel", "error", "-threads", "2",
     "-re", "-i", path, "-map", "0:v:0", "-vf", vf,
     "-f", "rawvideo", "-pix_fmt", "rgb565be", "pipe:1",
     "-map", "0:a:0?", "-f", "alsa", AUDIO_DEVICE],
    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
)


def _cleanup(*_):
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
    sys.exit(0)


signal.signal(signal.SIGTERM, _cleanup)
signal.signal(signal.SIGINT, _cleanup)

try:
    while True:
        data = proc.stdout.read(frame_bytes)
        if not data or len(data) < frame_bytes:
            break
        disp.display_raw565(data)
finally:
    if proc.poll() is None:
        proc.terminate()
