"""
Robot arm jog test — nudge each servo live with the arrow keys.

Like arm_test.py, but interactive instead of a scripted sweep: move a joint
with LEFT/RIGHT, then step to the next or previous joint whenever you want.
Uses the SAME robot_move_arm() / ARM_JOINTS the assistant uses, so what you
see here is exactly what voice/typed commands will do too.

Controls:
    LEFT / RIGHT   nudge the current joint's angle by 5 degrees
    Enter          go to the next joint
    b              go back to the previous joint
    c              recenter the current joint (back to its center angle)
    q              quit

SAFETY:
  - Keep the arm free to move — nothing should block a joint's travel.
  - Power the servo battery (6V NiMH -> PCA9685 V+) BEFORE running this. The
    Pi's 3.3V VCC alone runs the PCA9685 chip but not the servos.
  - If a joint strains or grinds, quit immediately (q, or Ctrl-C).

One-time install (on the Pi) — same as arm_test.py:
    sudo raspi-config nonint do_i2c 0 && sudo reboot   # enable I2C
    pip install adafruit-circuitpython-pca9685 adafruit-circuitpython-motor adafruit-blinka
    i2cdetect -y 1                                      # confirm address 40 shows up

Run (needs a real terminal — an interactive SSH session, not a scripted one):
    python3 robot_code/tests/arm_jog_test.py
"""

import curses

from assistant import ARM_JOINTS, ARM_CENTER_ANGLES, robot_move_arm, _ensure_arm  # reuse the real arm code

STEP = 5.0


def run(stdscr):
    curses.curs_set(0)     # hide the cursor
    stdscr.keypad(True)    # decode arrow keys into curses.KEY_LEFT / KEY_RIGHT
    stdscr.nodelay(False)  # block until a key is pressed

    if _ensure_arm() is None:
        stdscr.addstr(0, 0, "Could not reach the PCA9685 over I2C. Check:")
        stdscr.addstr(1, 0, "  - I2C enabled?  i2cdetect -y 1  should show address 40")
        stdscr.addstr(2, 0, "  - Pi -> PCA9685: 3.3V->VCC, GND->GND, SDA(pin3)->SDA, SCL(pin5)->SCL")
        stdscr.addstr(3, 0, "  - adafruit-circuitpython-pca9685 / adafruit-blinka installed?")
        stdscr.addstr(5, 0, "Press any key to exit.")
        stdscr.refresh()
        stdscr.getch()
        return

    angles = {j: ARM_CENTER_ANGLES[j] for j in ARM_JOINTS}
    for j in ARM_JOINTS:
        robot_move_arm(j, angles[j])

    idx = 0
    while 0 <= idx < len(ARM_JOINTS):
        joint = ARM_JOINTS[idx]
        stdscr.clear()
        stdscr.addstr(0, 0, f"Joint {idx + 1}/{len(ARM_JOINTS)}: {joint}")
        stdscr.addstr(1, 0, f"Angle: {angles[joint]:.0f} deg  (center: {ARM_CENTER_ANGLES[joint]:.0f})")
        stdscr.addstr(3, 0, "<-  / ->  nudge angle (-5 / +5 deg)")
        stdscr.addstr(4, 0, "Enter     next joint")
        stdscr.addstr(5, 0, "b         previous joint")
        stdscr.addstr(6, 0, "c         recenter this joint")
        stdscr.addstr(7, 0, "q         quit")
        stdscr.refresh()

        key = stdscr.getch()
        if key == curses.KEY_LEFT:
            angles[joint] = max(0.0, angles[joint] - STEP)
            robot_move_arm(joint, angles[joint])
        elif key == curses.KEY_RIGHT:
            angles[joint] = min(180.0, angles[joint] + STEP)
            robot_move_arm(joint, angles[joint])
        elif key in (curses.KEY_ENTER, ord("\n"), ord("\r")):
            idx += 1
        elif key in (ord("b"), ord("B")):
            idx -= 1
        elif key in (ord("c"), ord("C")):
            angles[joint] = ARM_CENTER_ANGLES[joint]
            robot_move_arm(joint, angles[joint])
        elif key in (ord("q"), ord("Q")):
            break

    stdscr.clear()
    stdscr.addstr(0, 0, "Final angles:")
    for i, j in enumerate(ARM_JOINTS):
        stdscr.addstr(i + 1, 0, f"  {j}: {angles[j]:.0f} deg")
    stdscr.addstr(len(ARM_JOINTS) + 2, 0, "Press any key to exit.")
    stdscr.refresh()
    stdscr.getch()


if __name__ == "__main__":
    try:
        curses.wrapper(run)  # wrapper restores the terminal cleanly even on Ctrl-C / errors
    except KeyboardInterrupt:
        pass
