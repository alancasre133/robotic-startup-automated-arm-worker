"""
BTS7960 4WD bring-up test — verify the two new drivers before assistant.py.

Two BTS7960 modules, one per side, each driving that side's two motors in
parallel. Standalone (no assistant.py import) so you can prove the wiring
before touching the main code.

WIRING (Pi GPIO -> BTS7960, reusing the freed-up L9110S pins):
    LEFT board  : RPWM = GPIO16 (pin 36)   LPWM = GPIO20 (pin 38)
    RIGHT board : RPWM = GPIO27 (pin 13)   LPWM = GPIO22 (pin 15)
    Both boards : R_EN + L_EN -> Pi 3.3V   (always enabled)
                  VCC -> Pi 3.3V,  GND -> Pi GND
                  B+ -> NiMH + (through the 7.5A fuse, thick wire), B- -> NiMH -
                  M+/M- -> that side's two motors, paralleled

gpiozero's Motor(forward, backward) drives one pin HIGH and the other LOW --
exactly the RPWM/LPWM pattern the BTS7960 wants. forward()=RPWM high, LPWM low;
backward()=the reverse. pwm=False keeps it plain digital (full speed).

SAFETY: run with all four wheels OFF THE GROUND the first time.

Run:
    python3 robot_code/tests/bts7960_test.py
"""

from gpiozero import Motor
from time import sleep

# Left BTS7960: RPWM=16, LPWM=20.  Right BTS7960: RPWM=27, LPWM=22.
left  = Motor(forward=16, backward=20, pwm=False)
right = Motor(forward=27, backward=22, pwm=False)

PAUSE = 1.5   # seconds per move


def step(label, action):
    input(f"\nENTER to run -> {label} ")
    action()
    sleep(PAUSE)
    left.stop()
    right.stop()


try:
    print("BTS7960 4WD test. Wheels OFF the ground. Ctrl-C to stop.")

    step("LEFT forward   (both left wheels toward the front?)",  left.forward)
    step("LEFT backward  (both left wheels reverse?)",           left.backward)
    step("RIGHT forward  (both right wheels toward the front?)", right.forward)
    step("RIGHT backward (both right wheels reverse?)",          right.backward)

    print("\n-- both together --")
    step("FORWARD  (all four toward the front)",  lambda: (left.forward(),  right.forward()))
    step("BACKWARD (all four reverse)",           lambda: (left.backward(), right.backward()))
    step("SPIN     (left fwd, right back)",       lambda: (left.forward(),  right.backward()))

    print("\nDone. If any wheel spun the wrong way, swap that motor's two M+/M- leads.")
    print("If a whole side reversed, swap that board's RPWM/LPWM (or its M+/M-).")
finally:
    left.stop()
    right.stop()
