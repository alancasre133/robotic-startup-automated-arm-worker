"""
Grab test — run the ultrasonic approach-and-grab sequence directly.

This exercises the SAME grab_sequence() the offline brain uses: it reads the
HC-SR04, drives forward in short bursts until an object is within reach, then
extends the arm, closes the gripper, and lifts. No voice input or API key
needed — good for tuning the arm poses and reach distance.

Before trusting it:
  1. Calibrate the arm poses (ARM_POSES) and gripper angles in assistant.py
     using arm_jog_test.py — the defaults there are guesses, not tuned to your
     arm, and a wrong angle can make the arm hit the chassis.
  2. Wire the HC-SR04 (Trig pin 33 / Echo pin 35 via the 1k+2k divider). If it
     isn't connected, grab_sequence() reports it and does a single blind grab.

Run on the Pi, arm clear of obstacles, an object ~20-30 cm in front. Pass the
object's colour as an argument (default red):
    python3 robot_code/tests/grab_test.py yellow
    python3 robot_code/tests/grab_test.py            # defaults to red

Ctrl-C aborts.
"""

import sys

import assistant


def main() -> None:
    color = sys.argv[1] if len(sys.argv) > 1 else "red"
    print(f"Target colour: {color}")

    print("Distance sensor check...")
    d = assistant.distance_ahead()
    print(f"  distance_ahead() -> {d:.0f} cm" if d >= 0 else "  no sensor (-1)")

    print("\nRunning grab sequence (Ctrl-C to abort)...")
    try:
        result = assistant.grab_sequence(color)
        print(f"\nResult: {result}")
    except KeyboardInterrupt:
        print("\nAborted.")
    finally:
        # Leave the wheels stopped no matter how we exit.
        assistant.robot_drive("stop")


if __name__ == "__main__":
    main()
