"""
Distance calibration — teach the robot how apparent size (camera) maps to actual
distance (ultrasonic). This is the "learn how far things are" step.

It drives forward in short steps toward a coloured object, and at each step
records a pair: (how big the object looks, how far the ultrasonic says it is).
Those pairs are saved to ~/robot_distance_calib.json. Afterwards,
perception.estimate_distance(area_frac) can gauge distance from the camera alone
— useful when the object drifts out of the ultrasonic's narrow forward beam.

This is calibration/interpolation, not machine-learning training (a Pi 3 can't
train a model) — but it genuinely lets the robot judge distance from vision.

Prerequisites:
  - HC-SR04 wired (Trig pin 33 / Echo pin 35 via the 1k+2k divider).
  - Camera free:  sudo systemctl stop camera-stream
  - A coloured object ~30-40 cm ahead, clear path, WHEELS ON THE GROUND.

Run:
    python3 robot_code/tests/distance_calibrate.py [color]   # default red

Ctrl-C aborts (whatever was collected so far is still saved).
"""

import json
import os
import sys
import time

import assistant
import perception

OUT = os.path.expanduser("~/robot_distance_calib.json")
STEPS = 10          # how many forward steps to sample over
STOP_CM = 8.0       # stop sampling once this close


def main() -> None:
    color = sys.argv[1] if len(sys.argv) > 1 else "red"
    print(f"Calibrating distance for a {color} object over {STEPS} steps.\n")

    cam = perception.open_camera()
    time.sleep(1.0)
    samples = []
    try:
        for i in range(STEPS):
            r = perception.find_object(cam, color)
            d = assistant.distance_ahead()
            if r["seen"] and d >= 0:
                samples.append({"area_frac": round(r["area_frac"], 5), "cm": round(d, 1)})
                print(f"  step {i + 1:2d}: size={r['area_frac'] * 100:4.1f}%  dist={d:5.1f}cm")
                if d <= STOP_CM:
                    print("  close enough — stopping.")
                    break
            else:
                why = "object not seen" if not r["seen"] else "sensor read -1"
                print(f"  step {i + 1:2d}: skip ({why})")
            assistant.robot_drive("forward", 0.4)
            time.sleep(0.4)
    except KeyboardInterrupt:
        print("\nAborted — saving what we have.")
    finally:
        assistant.robot_drive("stop")
        cam.stop()

    if len(samples) >= 2:
        samples.sort(key=lambda s: s["area_frac"])
        with open(OUT, "w") as f:
            json.dump({"color": color, "samples": samples}, f, indent=2)
        print(f"\nSaved {len(samples)} samples to {OUT}")
        print("The robot can now estimate distance from the camera. Re-run to refine.")
    else:
        print("\nNot enough samples (need the object visible AND the HC-SR04 wired).")


if __name__ == "__main__":
    main()
