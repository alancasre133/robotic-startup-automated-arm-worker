"""
Vision find test — point the camera at a coloured object and check detection.

Prints, every frame, whether the object is seen, its bearing (left/CENTER/right),
and its apparent size. No motors, no arm — use this FIRST to confirm the camera
sees your object and to pick a colour that detects cleanly before wiring it into
the grab behaviour.

Stop the stream service if it's running (camera is single-user):
    sudo systemctl stop camera-stream

Run:
    python3 robot_code/tests/vision_find_test.py [color]
    color = red (default) | green | blue | yellow

If your object doesn't detect well, tune COLOR_RANGES in perception.py (HSV).
Ctrl-C to stop.
"""

import sys
import time

import perception


def main() -> None:
    color = sys.argv[1] if len(sys.argv) > 1 else "red"
    print(f"Looking for a {color} object. Ctrl-C to stop.\n")
    cam = perception.open_camera()
    time.sleep(1.0)     # let auto-exposure settle
    try:
        while True:
            r = perception.find_object(cam, color)
            if r["seen"]:
                off = r["offset"]
                side = ("left" if off < -perception.CENTER_DEADZONE
                        else "right" if off > perception.CENTER_DEADZONE else "CENTER")
                est = perception.estimate_distance(r["area_frac"])
                est_s = f"  ~{est:.0f}cm (calibrated)" if est >= 0 else ""
                print(f"seen  {side:6s}  offset={off:+.2f}  "
                      f"size={r['area_frac'] * 100:4.1f}% of frame{est_s}")
            else:
                print("not seen")
            time.sleep(0.3)
    except KeyboardInterrupt:
        pass
    finally:
        cam.stop()


if __name__ == "__main__":
    main()
