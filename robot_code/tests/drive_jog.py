"""
Drive MELVINN around live with the keyboard — RC-style continuous control.

Like arm_jog_test.py but for the wheels: press a direction and the robot KEEPS
moving that way until you steer somewhere else or stop. Uses the SAME left/right
BTS7960 motor objects assistant.py drives (one board per side, that side's two
wheels paralleled), so it behaves exactly like the voice/typed drive commands.

The motors hold their state between keypresses (gpiozero keeps the pins set), so
there's no stutter — one tap of W and it rolls forward until you press something
else.

Controls:
    W / Up        drive forward
    S / Down      drive backward
    A / Left      turn left   (left wheels back, right forward — pivots in place)
    D / Right     turn right  (left forward, right back)
    Space         stop
    q             quit (stops first)

SAFETY:
    Check directions with the wheels OFF THE GROUND first, THEN put it on the
    floor. It moves at full speed on the JGA25 gearmotors — give it room, and
    keep the charger handy (a sagging battery makes it crawl/veer).

Run (needs a real interactive terminal — an SSH session, not a scripted one):
    python3 robot_code/tests/drive_jog.py
"""

import curses

from assistant import _ensure_motors   # reuse the real motor objects

HELP = [
    "MELVINN — keyboard drive (RC style)",
    "",
    "  W / Up      forward",
    "  S / Down    backward",
    "  A / Left    turn left",
    "  D / Right   turn right",
    "  Space       stop",
    "  q           quit",
]


def run(stdscr):
    curses.curs_set(0)
    stdscr.keypad(True)     # decode the arrow keys
    stdscr.nodelay(False)   # block until a key is pressed

    left, right = _ensure_motors()

    def stop():
        left.stop()
        right.stop()

    state = "stopped"
    while True:
        stdscr.clear()
        for i, line in enumerate(HELP):
            stdscr.addstr(i, 0, line)
        stdscr.addstr(len(HELP) + 1, 0, f"Now driving: {state}        ")
        stdscr.refresh()

        key = stdscr.getch()
        if key in (curses.KEY_UP, ord("w"), ord("W")):
            left.forward(); right.forward(); state = "FORWARD"
        elif key in (curses.KEY_DOWN, ord("s"), ord("S")):
            left.backward(); right.backward(); state = "BACKWARD"
        elif key in (curses.KEY_LEFT, ord("a"), ord("A")):
            left.backward(); right.forward(); state = "TURNING LEFT"
        elif key in (curses.KEY_RIGHT, ord("d"), ord("D")):
            left.forward(); right.backward(); state = "TURNING RIGHT"
        elif key == ord(" "):
            stop(); state = "stopped"
        elif key in (ord("q"), ord("Q")):
            break

    stop()


if __name__ == "__main__":
    try:
        curses.wrapper(run)
    except KeyboardInterrupt:
        pass
    finally:
        # belt-and-suspenders: make sure nothing keeps rolling on exit
        try:
            from assistant import motor_left, motor_right
            if motor_left is not None:
                motor_left.stop()
            if motor_right is not None:
                motor_right.stop()
        except Exception:
            pass
