"""
Rock-start test — try to break a heavy/top-heavy bot loose from a standstill.

The TT motors are already driven at full voltage (L9110S, digital on/off), so
there is no "more power" to give. This instead JABS the motors in the drive
direction a few times to jolt the chassis past static friction, then drives
steady. It only helps the bot START moving — it cannot fix slow crawling once
moving (that needs more volts or less weight; see HARDWARE.md).

Run with the WHEELS ON THE GROUND (you want to see if it actually moves):
    python3 robot_code/tests/rock_test.py

Ctrl-C to stop.
"""

from gpiozero import Motor
from time import sleep

motor_a = Motor(forward=16, backward=20, pwm=False)
motor_b = Motor(forward=27, backward=22, pwm=False)

JABS = 4          # number of jolts
JAB_ON = 0.12     # seconds powered per jolt
JAB_OFF = 0.06    # seconds resting between jolts
DRIVE = 1.5       # seconds of steady drive after the rock


def drive_forward():
    motor_a.forward()
    motor_b.forward()


def stop():
    motor_a.stop()
    motor_b.stop()


try:
    print(f"Rocking: {JABS} jabs, then {DRIVE}s steady drive forward...")
    for i in range(JABS):
        print(f"  jab {i + 1}/{JABS}")
        drive_forward()
        sleep(JAB_ON)
        stop()
        sleep(JAB_OFF)

    print("Steady drive...")
    drive_forward()
    sleep(DRIVE)
    stop()
    print("Done. Did it break loose / move?")
except KeyboardInterrupt:
    pass
finally:
    stop()
