"""
Motor test for the robot car.

Drives both DC motors through an L9110S dual H-bridge, controlled directly
from the Raspberry Pi 3 GPIO via gpiozero. Run with the wheels OFF the ground.

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

# Each Motor takes the two L9110S inputs for that channel.
# forward()/backward() just drive one input high and the other low.
motor_a = Motor(forward=16, backward=20)
motor_b = Motor(forward=27, backward=22)

try:
    print("Motor A forward...")
    motor_a.forward()
    sleep(1)
    motor_a.stop()

    sleep(0.5)

    print("Motor B forward...")
    motor_b.forward()
    sleep(1)
    motor_b.stop()

    print("Test complete.")
finally:
    # Always leave the motors stopped, even on Ctrl+C or an error.
    motor_a.stop()
    motor_b.stop()
