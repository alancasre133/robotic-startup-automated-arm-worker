"""
Drive forward until ENTER is pressed.

Starts all four wheels forward the moment it launches (same BTS7960 pins as
assistant.py: left RPWM/LPWM = GPIO16/20, right = GPIO27/22) and keeps them
running until you press ENTER -- or Ctrl-C; either way the finally stops
both sides before the script exits.

ROCK_START jabs the motors a few times first to break static friction from
a standstill (same pattern as assistant.py), then commits to steady drive.

Run (robot ON THE FLOOR with room ahead):
    python3 robot_code/tests/drive_forward.py
"""

from time import sleep

from gpiozero import Motor

left  = Motor(forward=20, backward=16, pwm=False)
right = Motor(forward=27, backward=22, pwm=False)

ROCK_START = True   # jab before steady drive to jolt the bot off a standstill
ROCK_ROUNDS = 3


def rock():
    for _round in range(ROCK_ROUNDS):
        for _ in range(3):
            left.forward()
            right.forward()
            sleep(0.12)
            left.stop()
            right.stop()
            sleep(0.06)
        if _round < ROCK_ROUNDS - 1:
            sleep(0.25)  # let it settle before the next round


try:
    if ROCK_START:
        print("Rock-starting...")
        rock()
    left.forward()
    right.forward()
    input("Driving FORWARD -- press ENTER to stop. ")
finally:
    left.stop()
    right.stop()
    print("Stopped.")
