"""
Robot wheel jog test — nudge each motor live with the arrow keys.

Like arm_jog_test.py, but for the drive motors: pick a motor with Enter/b,
then pulse it forward or backward with the arrow keys and watch which wheel
spins which way. Uses the SAME left/right motor objects assistant.py drives
(one BTS7960 per side, that side's two wheels paralleled onto it), so what you
see here is exactly what voice/typed drive commands will do too.

Controls:
    RIGHT          pulse the current motor FORWARD for PULSE_SECS
    LEFT           pulse the current motor BACKWARD for PULSE_SECS
    Enter          go to the next motor
    b              go back to the previous motor
    q              quit

SAFETY:
    Run with the wheels OFF THE GROUND (or the car will drive off the desk).

Run (needs a real terminal — an interactive SSH session, not a scripted one):
    python3 robot_code/tests/wheel_jog_test.py
"""

import curses
from time import sleep

from assistant import _ensure_motors  # reuse the real motor objects

PULSE_SECS = 0.4
MOTOR_NAMES = ("Left side", "Right side")


def run(stdscr):
    curses.curs_set(0)
    stdscr.keypad(True)
    stdscr.nodelay(False)

    motor_left, motor_right = _ensure_motors()
    motors = (motor_left, motor_right)

    idx = 0
    last_action = "(none yet)"
    while 0 <= idx < len(motors):
        motor = motors[idx]
        stdscr.clear()
        stdscr.addstr(0, 0, f"Motor {idx + 1}/{len(motors)}: {MOTOR_NAMES[idx]}")
        stdscr.addstr(1, 0, f"Last action: {last_action}")
        stdscr.addstr(3, 0, "<-  pulse BACKWARD   ->  pulse FORWARD")
        stdscr.addstr(4, 0, "Enter     next motor")
        stdscr.addstr(5, 0, "b         previous motor")
        stdscr.addstr(6, 0, "q         quit")
        stdscr.refresh()

        key = stdscr.getch()
        if key == curses.KEY_RIGHT:
            motor.forward()
            sleep(PULSE_SECS)
            motor.stop()
            last_action = f"{MOTOR_NAMES[idx]} forward"
        elif key == curses.KEY_LEFT:
            motor.backward()
            sleep(PULSE_SECS)
            motor.stop()
            last_action = f"{MOTOR_NAMES[idx]} backward"
        elif key in (curses.KEY_ENTER, ord("\n"), ord("\r")):
            idx += 1
        elif key in (ord("b"), ord("B")):
            idx -= 1
        elif key in (ord("q"), ord("Q")):
            break

    motor_left.stop()
    motor_right.stop()
    stdscr.clear()
    stdscr.addstr(0, 0, "Done. Report which wheel moved and which way for each motor/direction.")
    stdscr.addstr(2, 0, "Press any key to exit.")
    stdscr.refresh()
    stdscr.getch()


if __name__ == "__main__":
    try:
        curses.wrapper(run)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            from assistant import motor_left, motor_right
            if motor_left is not None:
                motor_left.stop()
            if motor_right is not None:
                motor_right.stop()
        except Exception:
            pass
