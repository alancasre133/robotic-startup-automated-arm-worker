"""
Enroll an object — SHOW it to the camera and teach the robot to recognize it.

Fill the camera frame with the object (as little background as possible, good
light, hold it still), then run this with a name. It captures a frame, extracts
ORB features, saves them, and writes a preview JPEG so you can check the framing.

    sudo systemctl stop camera-stream          # camera is single-user
    python3 enroll_object.py cup

Tips:
  - Textured / patterned objects work; plain, shiny, or transparent ones don't.
  - Re-run with the same name to replace a bad enrollment.
  - Check ~/robot_objects/<name>_preview.jpg to see exactly what was captured.
"""

import os
import sys
import time

import cv2

import perception
import object_recognition as orec


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python3 enroll_object.py <name>")
        return
    name = sys.argv[1]

    cam = perception.open_camera()
    time.sleep(1.0)     # let exposure settle
    try:
        input(f"Fill the frame with '{name}' (hold still), then press Enter to capture...")
        frame = cam.capture_array()
    finally:
        cam.stop()

    n = orec.enroll(frame, name)
    os.makedirs(orec.STORE_DIR, exist_ok=True)
    preview = os.path.join(orec.STORE_DIR, f"{name}_preview.jpg")
    cv2.imwrite(preview, frame)

    if n:
        print(f"\nEnrolled '{name}' with {n} features.")
        print(f"Enrolled objects: {orec.list_objects()}")
        print(f"Preview saved to {preview} (check the framing).")
    else:
        print("\nToo few features — the object is too plain, shiny, blurry, or far.")
        print("Try a more textured object, better light, or fill more of the frame.")
        print(f"Preview saved to {preview} so you can see what the camera got.")


if __name__ == "__main__":
    main()
