"""
Record a sequence of arm poses AND wheel moves, save it, and replay it later.

Two recording modes, switch between them anytime with TAB, both writing into
the SAME sequence -- so one recording can mix arm poses and drive moves:

  ARM mode (arm_jog_test.py's jog UI): jog a joint with LEFT/RIGHT, switch
  joints with Enter/b, then SPACE to capture the current full pose as a step.

  WHEEL mode (wheel_jog_test.py's drive UI): each arrow key IS a step --
  press it and the robot drives immediately, then that move is captured.

Controls:
    TAB            switch between ARM mode and WHEEL mode
    u              undo (remove) the last captured step
    s              save the sequence and quit
    q              quit WITHOUT saving

  ARM mode:
    LEFT / RIGHT   nudge the current joint's angle by 5 degrees
    Enter          go to the next joint
    b              go back to the previous joint
    c              recenter the current joint (back to its center angle)
    SPACE          capture the current full pose as the next step

  WHEEL mode:
    UP / DOWN      drive forward / backward for 1s (captured automatically)
    LEFT / RIGHT   turn left / right for 1s (captured automatically)
    SPACE          spin in place for 1s (captured automatically)
    x              explicit stop step

SAFETY:
  - Arm: keep it free to move, power the servo battery BEFORE running this.
  - Wheels: keep them off the ground, or clear floor space to actually drive.
  - If anything strains, grinds, or runs away, quit immediately (q, or Ctrl-C).

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

from assistant import ARM_JOINTS, ARM_CENTER_ANGLES, robot_move_arm, robot_drive, _ensure_arm, _ensure_motors

STEP = 5.0
DRIVE_SECS = 1.0
STEP_PAUSE = 0.8  # seconds to wait between arm poses during playback, for the servos to get there

SEQUENCES_DIR = os.path.join(os.path.dirname(__file__), "arm_sequences")


def _sequence_path(name: str) -> str:
    return os.path.join(SEQUENCES_DIR, f"{name}.json")


def _draw_header(stdscr, name, mode, steps):
    stdscr.addstr(0, 0, f"Recording sequence '{name}'  [{mode.upper()} mode]  ({len(steps)} step(s) captured)")
    stdscr.addstr(1, 0, "TAB switch mode  |  u undo  |  s save+quit  |  q quit without saving")


def _record(stdscr, name: str):
    curses.curs_set(0)
    stdscr.keypad(True)
    stdscr.nodelay(False)

    if _ensure_arm() is None:
        stdscr.addstr(0, 0, "Could not reach the PCA9685 over I2C -- arm won't move, but wheel")
        stdscr.addstr(1, 0, "recording still works. Press any key to continue.")
        stdscr.refresh()
        stdscr.getch()

    angles = {j: ARM_CENTER_ANGLES[j] for j in ARM_JOINTS}
    for j in ARM_JOINTS:
        robot_move_arm(j, angles[j])
    _ensure_motors()

    steps: list = []
    idx = 0
    mode = "arm"
    saved = False
    while True:
        stdscr.clear()
        _draw_header(stdscr, name, mode, steps)

        if mode == "arm":
            joint = ARM_JOINTS[idx % len(ARM_JOINTS)]
            stdscr.addstr(3, 0, f"Joint {idx % len(ARM_JOINTS) + 1}/{len(ARM_JOINTS)}: {joint}")
            stdscr.addstr(4, 0, f"Angle: {angles[joint]:.0f} deg")
            stdscr.addstr(6, 0, "<-  / ->  nudge angle (-5 / +5 deg)")
            stdscr.addstr(7, 0, "Enter     next joint")
            stdscr.addstr(8, 0, "b         previous joint")
            stdscr.addstr(9, 0, "c         recenter this joint")
            stdscr.addstr(10, 0, "SPACE     capture this pose as the next step")
        else:
            stdscr.addstr(3, 0, "UP / DOWN     drive forward / backward 1s")
            stdscr.addstr(4, 0, "LEFT / RIGHT  turn left / right 1s")
            stdscr.addstr(5, 0, "SPACE         spin in place 1s")
            stdscr.addstr(6, 0, "x             explicit stop step")
            stdscr.addstr(8, 0, "(each move drives immediately and is captured automatically)")
        stdscr.refresh()

        key = stdscr.getch()
        if key == ord("\t"):
            mode = "wheel" if mode == "arm" else "arm"
        elif key in (ord("u"), ord("U")):
            if steps:
                steps.pop()
        elif key in (ord("s"), ord("S")):
            saved = True
            break
        elif key in (ord("q"), ord("Q")):
            break
        elif mode == "arm":
            joint = ARM_JOINTS[idx % len(ARM_JOINTS)]
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
            elif key == ord(" "):
                steps.append({"type": "arm", "pose": dict(angles)})
        else:  # wheel mode
            direction = None
            if key == curses.KEY_UP:
                direction = "forward"
            elif key == curses.KEY_DOWN:
                direction = "backward"
            elif key == curses.KEY_LEFT:
                direction = "left"
            elif key == curses.KEY_RIGHT:
                direction = "right"
            elif key == ord(" "):
                direction = "spin"
            elif key in (ord("x"), ord("X")):
                direction = "stop"
            if direction:
                secs = 0.0 if direction == "stop" else DRIVE_SECS
                robot_drive(direction, secs)
                steps.append({"type": "drive", "direction": direction, "seconds": secs})

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
    print(f"Playing '{name}' ({len(steps)} step(s))...")
    for i, step in enumerate(steps):
        if step["type"] == "arm":
            print(f"  step {i + 1}/{len(steps)}: arm pose {step['pose']}")
            if _ensure_arm() is None:
                print("    !! arm not connected, skipping")
                continue
            for joint, angle in step["pose"].items():
                robot_move_arm(joint, angle)
            sleep(STEP_PAUSE)
        else:
            print(f"  step {i + 1}/{len(steps)}: drive {step['direction']} for {step['seconds']}s")
            robot_drive(step["direction"], step["seconds"])
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
        arm_n = sum(1 for s in steps if s["type"] == "arm")
        drive_n = sum(1 for s in steps if s["type"] == "drive")
        print(f"  {n}  ({len(steps)} step(s): {arm_n} arm, {drive_n} drive)")


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
