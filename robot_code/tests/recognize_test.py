"""
Recognition test — see which enrolled object the camera recognizes, live.

Prints, each frame, the best-matching enrolled object, its bearing
(left/CENTER/right), apparent size, and match count (higher = more confident).
Use this to confirm ORB recognition works on your objects BEFORE wiring it into
the grab behaviour.

    sudo systemctl stop camera-stream            # camera is single-user
    python3 recognize_test.py            # match against all enrolled objects
    python3 recognize_test.py cup        # look only for 'cup'

Enroll objects first with enroll_object.py. Ctrl-C to stop.
"""

import sys
import time

import perception
import object_recognition as orec


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else None
    objs = orec.list_objects()
    if not objs:
        print("No objects enrolled yet. Run:  python3 enroll_object.py <name>")
        return
    print(f"Enrolled: {objs}")
    print(f"Looking for: {name or 'any'}. Ctrl-C to stop.\n")

    cam = perception.open_camera()
    time.sleep(1.0)
    try:
        while True:
            r = orec.recognize(cam.capture_array(), name)
            if r["seen"]:
                off = r["offset"]
                side = ("left" if off < -perception.CENTER_DEADZONE
                        else "right" if off > perception.CENTER_DEADZONE else "CENTER")
                print(f"{r['name']:12s} {side:6s} offset={off:+.2f} "
                      f"size={r['area_frac'] * 100:4.1f}% matches={r['matches']}")
            else:
                print("nothing recognized")
            time.sleep(0.3)
    except KeyboardInterrupt:
        pass
    finally:
        cam.stop()


if __name__ == "__main__":
    main()
