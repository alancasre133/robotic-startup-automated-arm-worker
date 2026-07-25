"""
Camera test for the robot car.

Captures a single still from the IMX219 camera using Picamera2 and saves it
to ~/camera_test.jpg.

Requires:
  - python3-picamera2 (installed by setup.sh)
  - the camera enabled in /boot/firmware/config.txt: dtoverlay=imx219
    (see the "Camera (IMX219)" section of README.md)

Run:
    python3 robot_code/tests/camera_test.py

Then copy it to your computer to view (from your PC, not the Pi):
    scp alanacr@<pi-ip>:~/camera_test.jpg .
"""

import os
from time import sleep

from libcamera import Transform
from picamera2 import Picamera2

FLIP_180 = False  # camera now mounted right-side-up (flip was for the old mount)

picam2 = Picamera2()

# 1920x1080 keeps memory use low (CMA is cma-64). Raise once cma is bumped.
transform = Transform(hflip=1, vflip=1) if FLIP_180 else Transform()
picam2.configure(picam2.create_still_configuration(main={"size": (1920, 1080)}, transform=transform))

picam2.start()
sleep(2)  # let auto-exposure / white balance settle

out = os.path.expanduser("~/camera_test.jpg")
picam2.capture_file(out)
picam2.stop()

print(f"Saved {out}")
