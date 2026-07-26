"""
Smart-grab test — the vision-GUIDED grab where the arm aims itself.

Unlike grab_test.py (which reaches dead-ahead from a fixed pose), this reads
where the camera sees the object and swings the arm's BASE to face it before
reaching. So it adapts to an object that's off to the left or right.

No wheels — it only moves the arm, so it's safe to run with the drivetrain
unplugged. Put the object within arm's reach (~15-25 cm ahead), a bit off to
one side to see the aiming work, then:

    python3 robot_code/tests/smart_grab_test.py yellow
    python3 robot_code/tests/smart_grab_test.py            # defaults to red

Tuning lives in controllers/arm_controller.py: if it aims the WRONG way
left/right, flip BASE_SIGN; if it doesn't swing far enough, raise BASE_GAIN.

Ctrl-C aborts.
"""

import sys

import assistant


def main() -> None:
    color = sys.argv[1] if len(sys.argv) > 1 else "red"
    print(f"Target colour: {color}")
    print("Smart (vision-guided) grab — the arm aims itself. Ctrl-C to abort.\n")
    try:
        result = assistant.smart_grab(color)
        print(f"\nResult: {result}")
    except KeyboardInterrupt:
        print("\nAborted.")
    finally:
        assistant.robot_drive("stop")


if __name__ == "__main__":
    main()
