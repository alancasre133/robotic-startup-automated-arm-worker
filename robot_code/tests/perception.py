"""
Vision perception for the grab behaviour — find a coloured object with the
camera and report WHERE it is (bearing) and HOW BIG it looks (a proxy for
distance). Runs on the Pi 3 with picamera2 + OpenCV (both system packages,
already installed by setup.sh — no new dependencies for colour detection).

This is COLOUR-BLOB detection: it finds the largest patch of a target colour
(e.g. a red ball). It's fast and reliable on the Pi 3, but it only finds objects
of that colour. A general object detector (TFLite MobileNet-SSD, etc.) could be
dropped in behind the same find_object() interface later — it would recognise
arbitrary objects but run only ~1 frame every few seconds on a Pi 3.

The camera is single-user. If the auto-start stream service holds it, stop it
first:  sudo systemctl stop camera-stream
"""

import json
import os

import cv2
import numpy as np
from libcamera import Transform
from picamera2 import Picamera2

WIDTH, HEIGHT = 640, 480
FLIP_180 = False           # camera now mounted right-side-up (matches vision_track.py)
MIN_AREA_FRAC = 0.002      # ignore blobs smaller than this fraction of the frame (noise)
CENTER_DEADZONE = 0.15     # |offset| under this counts as "centred"

CALIB_PATH = os.path.expanduser("~/robot_distance_calib.json")

# HSV colour ranges. Red wraps around hue 0, so it needs two ranges.
COLOR_RANGES = {
    "red":    [((0, 120, 70), (10, 255, 255)), ((170, 120, 70), (180, 255, 255))],
    "green":  [((40, 80, 40), (85, 255, 255))],
    "blue":   [((95, 120, 40), (130, 255, 255))],
    "yellow": [((20, 120, 80), (35, 255, 255))],
}


def open_camera():
    """Open and start the camera. Caller must call .stop() when done."""
    picam2 = Picamera2()
    transform = Transform(hflip=1, vflip=1) if FLIP_180 else Transform()
    picam2.configure(picam2.create_video_configuration(
        main={"size": (WIDTH, HEIGHT), "format": "RGB888"}, transform=transform))
    picam2.start()
    return picam2


def find_object(picam2, color="red"):
    """Locate the largest patch of `color` in the current frame.

    Returns a dict:
      seen      -> bool
      offset    -> -0.5 (far left) .. +0.5 (far right), 0.0 = centred
      area_frac -> blob area as a fraction of the whole frame (bigger = closer)
      cx, cy    -> blob centre in pixels
    """
    miss = {"seen": False, "offset": 0.0, "area_frac": 0.0, "cx": 0, "cy": 0}
    frame = picam2.capture_array()                       # H x W x 3, BGR
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    ranges = COLOR_RANGES.get(color, COLOR_RANGES["red"])
    mask = None
    for lo, hi in ranges:
        m = cv2.inRange(hsv, np.array(lo), np.array(hi))
        mask = m if mask is None else cv2.bitwise_or(mask, m)
    # knock out specks, fill small holes
    mask = cv2.erode(mask, None, iterations=2)
    mask = cv2.dilate(mask, None, iterations=2)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return miss
    biggest = max(contours, key=cv2.contourArea)
    area_frac = cv2.contourArea(biggest) / float(WIDTH * HEIGHT)
    if area_frac < MIN_AREA_FRAC:
        return miss

    M = cv2.moments(biggest)
    if not M["m00"]:
        return miss
    cx = int(M["m10"] / M["m00"])
    cy = int(M["m01"] / M["m00"])
    offset = (cx - WIDTH / 2) / WIDTH                     # -0.5 .. 0.5
    return {"seen": True, "offset": offset, "area_frac": area_frac, "cx": cx, "cy": cy}


def estimate_distance(area_frac, calib_path=CALIB_PATH):
    """Estimate distance in cm from apparent size, using a saved calibration.

    Returns -1 if there's no calibration yet (run distance_calibrate.py to make
    one). This is the "learned" size->distance mapping: it lets the robot gauge
    distance from the camera when the object is outside the ultrasonic's narrow
    forward beam. The ultrasonic is still the ground truth when it can see the
    object; this is the fallback.
    """
    if not os.path.exists(calib_path):
        return -1.0
    try:
        data = json.load(open(calib_path))
    except (OSError, ValueError):
        return -1.0
    samples = sorted(data.get("samples", []), key=lambda s: s["area_frac"])
    if len(samples) < 2:
        return -1.0
    if area_frac <= samples[0]["area_frac"]:
        return samples[0]["cm"]
    if area_frac >= samples[-1]["area_frac"]:
        return samples[-1]["cm"]
    for a, b in zip(samples, samples[1:]):
        if a["area_frac"] <= area_frac <= b["area_frac"]:
            span = b["area_frac"] - a["area_frac"]
            t = 0.0 if span == 0 else (area_frac - a["area_frac"]) / span
            return a["cm"] + t * (b["cm"] - a["cm"])
    return -1.0
