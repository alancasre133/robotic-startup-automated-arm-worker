"""
Record a sequence of arm poses, save it, and replay it later.

Record mode is arm_jog_test.py's jog UI (arrow keys move the current joint)
plus a capture key: whenever the arm is posed how you want, press SPACE to
save that full pose as one step in the sequence. Keep jogging + capturing to
build up a multi-step motion, then save it to a JSON file under
arm_sequences/. Play mode just replays the saved poses in order.

Controls (record mode):
    LEFT / RIGHT   nudge the current joint's angle by 5 degrees
    Enter          go to the next joint
    b              go back to the previous joint
    SPACE          capture the current full pose as the next step
    u              undo (remove) the last captured step
    s              save the sequence and quit
    q              quit WITHOUT saving

SAFETY:
  - Keep the arm free to move — nothing should block a joint's travel.
  - Power the servo battery (6V NiMH -> PCA9685 V+) BEFORE running this. The
    Pi's 3.3V VCC alone runs the PCA9685 chip but not the servos.
  - If a joint strains or grinds, quit immediately (q, or Ctrl-C).

Run:
    python3 robot_code/tests/arm_sequence.py record <name>   # interactive
    python3 robot_code/tests/arm_sequence.py play <name>     # replay it
    python3 robot_code/tests/arm_sequence.py list            # list saved sequences
"""

import curses
import json
import os
import sys
from time import sleep

from assistant import ARM_JOINTS, robot_move_arm, _ensure_arm  # reuse the real arm code

STEP = 5.0
START_ANGLE = 90.0
STEP_PAUSE = 0.8  # seconds to wait between poses during playback, for the servos to get there

SEQUENCES_DIR = os.path.join(os.path.dirname(__file__), "arm_sequences")


def _sequence_path(name: str) -> str:
    return os.path.join(SEQUENCES_DIR, f"{name}.json")


def _record(stdscr, name: str):
    curses.curs_set(0)
    stdscr.keypad(True)
    stdscr.nodelay(False)

    if _ensure_arm() is None:
        stdscr.addstr(0, 0, "Could not reach the PCA9685 over I2C. Check:")
        stdscr.addstr(1, 0, "  - I2C enabled?  i2cdetect -y 1  should show address 40")
        stdscr.addstr(2, 0, "  - Pi -> PCA9685: 3.3V->VCC, GND->GND, SDA(pin3)->SDA, SCL(pin5)->SCL")
        stdscr.addstr(3, 0, "  - adafruit-circuitpython-pca9685 / adafruit-blinka installed?")
        stdscr.addstr(5, 0, "Press any key to exit.")
        stdscr.refresh()
        stdscr.getch()
        return

    angles = {j: START_ANGLE for j in ARM_JOINTS}
    for j in ARM_JOINTS:
        robot_move_arm(j, angles[j])

    steps: list = []
    idx = 0
    saved = False
    while True:
        joint = ARM_JOINTS[idx % len(ARM_JOINTS)]
        stdscr.clear()
        stdscr.addstr(0, 0, f"Recording sequence '{name}'  ({len(steps)} step(s) captured)")
        stdscr.addstr(2, 0, f"Joint {idx % len(ARM_JOINTS) + 1}/{len(ARM_JOINTS)}: {joint}")
        stdscr.addstr(3, 0, f"Angle: {angles[joint]:.0f} deg")
        stdscr.addstr(5, 0, "<-  / ->  nudge angle (-5 / +5 deg)")
        stdscr.addstr(6, 0, "Enter     next joint")
        stdscr.addstr(7, 0, "b         previous joint")
        stdscr.addstr(8, 0, "SPACE     capture this pose as the next step")
        stdscr.addstr(9, 0, "u         undo last captured step")
        stdscr.addstr(10, 0, "s         save sequence and quit")
        stdscr.addstr(11, 0, "q         quit WITHOUT saving")
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
        elif key == ord(" "):
            steps.append(dict(angles))
        elif key in (ord("u"), ord("U")):
            if steps:
                steps.pop()
        elif key in (ord("s"), ord("S")):
            saved = True
            break
        elif key in (ord("q"), ord("Q")):
            break

    if saved:
        if not steps:
            stdscr.clear()
            stdscr.addstr(0, 0, "No steps captured -- nothing to save. Press any key to exit.")
            stdscr.refresh()
            stdscr.getch()
            return
        os.makedirs(SEQUENCES_DIR, exist_ok=True)
        with open(_sequence_path(name), "w") as f:
            json.dump(steps, f, indent=2)
        stdscr.clear()
        stdscr.addstr(0, 0, f"Saved {len(steps)} step(s) to {_sequence_path(name)}")
        stdscr.addstr(1, 0, f"Replay with: python3 arm_sequence.py play {name}")
        stdscr.addstr(3, 0, "Press any key to exit.")
        stdscr.refresh()
        stdscr.getch()


def record(name: str):
    try:
        curses.wrapper(lambda stdscr: _record(stdscr, name))
    except KeyboardInterrupt:
        pass


def play(name: str):
    path = _sequence_path(name)
    if not os.path.exists(path):
        print(f"No sequence named '{name}' at {path}")
        list_sequences()
        return
    with open(path) as f:
        steps = json.load(f)
    if _ensure_arm() is None:
        print("Could not reach the PCA9685 over I2C -- check wiring / I2C enabled.")
        return
    print(f"Playing '{name}' ({len(steps)} step(s))...")
    for i, pose in enumerate(steps):
        print(f"  step {i + 1}/{len(steps)}: {pose}")
        for joint, angle in pose.items():
            robot_move_arm(joint, angle)
        sleep(STEP_PAUSE)
    print("Done.")


def list_sequences():
    if not os.path.isdir(SEQUENCES_DIR):
        print("No sequences recorded yet.")
        return
    names = sorted(f[:-5] for f in os.listdir(SEQUENCES_DIR) if f.endswith(".json"))
    if not names:
        print("No sequences recorded yet.")
        return
    print("Saved sequences:")
    for n in names:
        with open(_sequence_path(n)) as f:
            steps = json.load(f)
        print(f"  {n}  ({len(steps)} step(s))")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("record", "play", "list"):
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "list":
        list_sequences()
    elif cmd in ("record", "play"):
        if len(sys.argv) < 3:
            print(f"Usage: python3 arm_sequence.py {cmd} <name>")
            sys.exit(1)
        (record if cmd == "record" else play)(sys.argv[2])
