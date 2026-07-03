"""
Motor wiring diagnostic — find out why the motor won't stop.

It drives the four L9110S input pins directly (no PWM, no Motor class) and pauses
at each step so you can WATCH the wheels and report what happens.

Run with the WHEELS OFF THE GROUND:
    python3 robot_code/motor_diag.py

For each step, note SPIN or STOP. The important ones:
  - the moment it starts (all pins LOW)  -> spinning already?
  - "A stop (both LOW)"                  -> does it stop?
  - "A brake (both HIGH)"                -> does it stop?
  - "RELEASE pins"                       -> does it stop?
"""

from gpiozero import OutputDevice

# L9110S inputs.  Motor A = 16/20, Motor B = 27/22 (same as assistant.py).
A1 = OutputDevice(16)   # motor A, input 1
A2 = OutputDevice(20)   # motor A, input 2
B1 = OutputDevice(27)   # motor B, input 1
B2 = OutputDevice(22)   # motor B, input 2
PINS = (A1, A2, B1, B2)


def state(a1, a2, b1, b2):
    A1.value, A2.value, B1.value, B2.value = a1, a2, b1, b2
    print(f"   pins: A1(16)={a1} A2(20)={a2}  B1(27)={b1} B2(22)={b2}   <-- watch the wheels")


STEPS = [
    ("Motor A FORWARD  (A1 HIGH, A2 LOW)", (1, 0, 0, 0)),
    ("Motor A STOP     (both LOW)",        (0, 0, 0, 0)),
    ("Motor A REVERSE  (A1 LOW,  A2 HIGH)", (0, 1, 0, 0)),
    ("Motor A STOP     (both LOW)",        (0, 0, 0, 0)),
    ("Motor A BRAKE?   (both HIGH)",       (1, 1, 0, 0)),
    ("Motor A STOP     (both LOW)",        (0, 0, 0, 0)),
    ("Motor B FORWARD  (B1 HIGH, B2 LOW)", (0, 0, 1, 0)),
    ("Motor B STOP     (both LOW)",        (0, 0, 0, 0)),
]

try:
    print("Devices created — all four pins are now driven LOW.")
    print(">>> Is anything spinning already? (that answers a lot)\n")
    for label, s in STEPS:
        input(f"Press Enter -> {label}")
        state(*s)
    input("\nPress Enter -> RELEASE all pins (back to floating/input, like app exit)")
    for d in PINS:
        d.close()
    print("   pins released. Did the motor stop NOW (and not before)?")
    input("Press Enter to quit")
except KeyboardInterrupt:
    pass
finally:
    for d in PINS:
        try:
            d.close()
        except Exception:
            pass
