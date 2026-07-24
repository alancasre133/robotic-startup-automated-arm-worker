"""
Drive forward until ENTER is pressed.

Starts all four wheels forward the moment it launches (same BTS7960 pins as
assistant.py: left RPWM/LPWM = GPIO16/20, right = GPIO27/22) and keeps them
running until you press ENTER -- or Ctrl-C; either way the finally stops
both sides before the script exits.

Run (robot ON THE FLOOR with room ahead):
    python3 robot_code/tests/drive_forward.py
"""

from gpiozero import Motor

left  = Motor(forward=16, backward=20, pwm=False)
right = Motor(forward=27, backward=22, pwm=False)

try:
    left.forward()
    right.forward()
    input("Driving FORWARD -- press ENTER to stop. ")
finally:
    left.stop()
    right.stop()
    print("Stopped.")
