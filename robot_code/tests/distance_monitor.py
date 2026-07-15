"""
Live ultrasonic distance readout — for calibrating the HC-SR04 and the grab
reach threshold.

Prints the median-filtered distance (the same value grab_sequence uses) a few
times a second, with a bar so you can watch it move an object in and out:

    cd ~/robotic-startup-automated-arm-worker/robot_code/tests
    python3 distance_monitor.py

Ctrl-C to stop. "no echo" means the sensor got nothing back this reading — the
object is too close, too far, too soft/angled, or outside the narrow forward
beam. Hold a flat object square to the sensor for the steadiest numbers.

Use this to pick ARM_REACH_CM in assistant.py: put the object where the arm's
reach pose lands on it, read the distance here, and set ARM_REACH_CM to that.
"""

import time
import warnings

import assistant

# gpiozero warns loudly ("DistanceSensorNoEcho: no echo received") on every
# missed ping — that spam makes the readout unreadable. Silence it; we already
# print a clean "no echo" ourselves.
warnings.filterwarnings("ignore")


def main() -> None:
    print("Ultrasonic distance — Ctrl-C to stop\n")
    try:
        while True:
            d = assistant.distance_ahead()
            if d >= 0:
                bar = "#" * min(int(d), 60)
                print(f"{d:6.1f} cm  {bar}")
            else:
                print("   -- cm  (no echo)")
            time.sleep(0.25)
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
