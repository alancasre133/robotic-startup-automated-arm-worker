"""
Motor test for the robot car (4WD: front+rear motors paralleled per channel).

Drives the motors through an L9110S dual H-bridge, controlled directly from
the Raspberry Pi 3 GPIO via gpiozero. Three phases:

  1. Motor A (left pair) alone  — check both left wheels spin, same way, forward
  2. Motor B (right pair) alone — same check for the right pair
  3. BOTH channels together at full power — the real max-load test: this is
     the highest current the battery + driver will ever be asked for

Start with the wheels OFF the ground to verify directions safely; re-run on
the ground to see if it actually pulls the bot's weight.

Wiring (Pi GPIO -> L9110S, BCM numbers):
    Motor A : A-1A = GPIO16 (pin 36)   A-1B = GPIO20 (pin 38)
    Motor B : B-1A = GPIO27 (pin 13)   B-2A = GPIO22 (pin 15)
    L9110S GND  -> Pi pin 6 (GND)
    Battery (-) -> Pi pin 9 (GND)
    Battery (+) -> L9110S VCC          (motors run off the AA pack, NOT the Pi)

Dependencies (Raspberry Pi OS Lite):
    sudo apt install -y python3-gpiozero python3-lgpio

Run:
    python3 robot_code/tests/motor_test.py
"""

from gpiozero import Motor
from time import sleep

# pwm=False drives the L9110S inputs as plain digital HIGH/LOW — full battery
# voltage to the motors, no PWM duty cycle in the way. Maximum potency is
# simply forward() with nothing throttling it.
motor_a = Motor(forward=16, backward=20, pwm=False)
motor_b = Motor(forward=27, backward=22, pwm=False)

BOTH_SECS = 3  # long enough to watch all four wheels and hear the battery sag, if any

try:
    print("Phase 1: Motor A (left pair) forward, alone...")
    motor_a.forward()
    sleep(1)
    motor_a.stop()
    print("  -> did BOTH left wheels spin, the same way, toward the front?")

    sleep(0.5)

    print("Phase 2: Motor B (right pair) forward, alone...")
    motor_b.forward()
    sleep(1)
    motor_b.stop()
    print("  -> did BOTH right wheels spin, the same way, toward the front?")

    sleep(0.5)

    print(f"Phase 3: BOTH channels forward at full power for {BOTH_SECS}s (max load)...")
    motor_a.forward()
    motor_b.forward()
    sleep(BOTH_SECS)
    motor_a.stop()
    motor_b.stop()
    print("  -> all four wheels forward together? any slowdown vs the solo runs")
    print("     means the battery is sagging under the combined draw.")

    print("Test complete.")
finally:
    # Always leave the motors stopped, even on Ctrl+C or an error.
    motor_a.stop()
    motor_b.stop()
