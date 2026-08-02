#!/usr/bin/env python3
"""
Weight and centre-of-gravity report for MELVINN, computed from the URDF.

    ros2 run melvinn_description mass_report.py            # centre pose
    python3 mass_report.py --arm-forward                   # arm reaching out

Walks the link tree, does forward kinematics at a given arm pose, and sums
mass * position to get the centre of gravity. Then compares the torque the
drivetrain needs against what the JGA25 gearmotors actually produce.

WHAT THIS CAN AND CANNOT TELL YOU
    It answers "how heavy is it, where is the weight, and is there torque
    margin". It CANNOT model battery internal resistance or voltage sag under
    load — and bench testing (motors spin freely when lifted, stall under
    load, jabs help) points at the electrical side as the bigger factor. Treat
    this as one half of the picture.
"""

import argparse
import math
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

G = 9.81

# JGA25-370 6V 60RPM metal gearmotor (installed Jul 2026, replaced the TT
# motors). Datasheet stall torque is ~2-5 kg-cm at 6V depending on the exact
# winding; both ends are shown in the report. (For reference the old TT motors
# were 0.8-1.2 kg-cm -- ~4x less, which is why the robot couldn't move.)
MOTOR_STALL_TORQUE_LOW = 2.0 * 0.0980665 / 10   # kg-cm -> N-m  = 0.0196
MOTOR_STALL_TORQUE_HIGH = 5.0 * 0.0980665 / 10  # = 0.0490

# Rolling resistance coefficients. Hard rubber on smooth hardwood is low;
# BREAKAWAY (static, getting it moving from rest) is several times higher,
# which is exactly the regime the robot fails in.
CRR_ROLLING = 0.03
CRR_BREAKAWAY = 0.12


def rpy_to_matrix(r, p, y):
    cr, sr = math.cos(r), math.sin(r)
    cp, sp = math.cos(p), math.sin(p)
    cy, sy = math.cos(y), math.sin(y)
    return [
        [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
        [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
        [-sp,     cp * sr,                cp * cr],
    ]


def mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def mat_vec(m, v):
    return [sum(m[i][k] * v[k] for k in range(3)) for i in range(3)]


def axis_angle_matrix(axis, angle):
    x, y, z = axis
    n = math.sqrt(x * x + y * y + z * z) or 1.0
    x, y, z = x / n, y / n, z / n
    c, s, t = math.cos(angle), math.sin(angle), 1 - math.cos(angle)
    return [
        [t * x * x + c,     t * x * y - s * z, t * x * z + s * y],
        [t * x * y + s * z, t * y * y + c,     t * y * z - s * x],
        [t * x * z - s * y, t * y * z + s * x, t * z * z + c],
    ]


def parse_origin(elem):
    o = elem.find("origin")
    xyz = [0.0, 0.0, 0.0]
    rpy = [0.0, 0.0, 0.0]
    if o is not None:
        if o.get("xyz"):
            xyz = [float(v) for v in o.get("xyz").split()]
        if o.get("rpy"):
            rpy = [float(v) for v in o.get("rpy").split()]
    return xyz, rpy


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--urdf", help="expanded URDF; default: run xacro on the package file")
    ap.add_argument("--arm-forward", action="store_true",
                    help="pose the arm reaching forward instead of the neutral centre")
    args = ap.parse_args()

    if args.urdf:
        urdf_xml = open(args.urdf).read()
    else:
        here = os.path.dirname(os.path.abspath(__file__))
        xacro_file = os.path.join(here, "..", "urdf", "melvinn.urdf.xacro")
        urdf_xml = subprocess.run(["xacro", xacro_file], capture_output=True,
                                  text=True, check=True).stdout

    root = ET.fromstring(urdf_xml)

    links = {l.get("name"): l for l in root.findall("link")}
    joints = root.findall("joint")

    # Arm pose. Zero = each joint's ARM_CENTER_ANGLES value.
    pose = {}
    if args.arm_forward:
        # shoulder swung down/forward from its 180 centre, elbow out
        pose = {"shoulder": math.radians(90), "elbow": math.radians(45)}

    # Build the tree and do forward kinematics.
    children = {}
    for j in joints:
        parent = j.find("parent").get("link")
        children.setdefault(parent, []).append(j)

    world = {"base_footprint": ([0.0, 0.0, 0.0],
                                [[1, 0, 0], [0, 1, 0], [0, 0, 1]])}
    stack = ["base_footprint"]
    while stack:
        parent = stack.pop()
        p_pos, p_rot = world[parent]
        for j in children.get(parent, []):
            child = j.find("child").get("link")
            xyz, rpy = parse_origin(j)
            rot = mat_mul(p_rot, rpy_to_matrix(*rpy))

            angle = pose.get(j.get("name"), 0.0)
            if j.get("type") in ("revolute", "continuous") and angle:
                ax = j.find("axis")
                axis = [float(v) for v in ax.get("xyz").split()] if ax is not None else [0, 0, 1]
                rot = mat_mul(rot, axis_angle_matrix(axis, angle))

            pos = [p_pos[i] + mat_vec(p_rot, xyz)[i] for i in range(3)]
            world[child] = (pos, rot)
            stack.append(child)

    # Accumulate mass and first moment.
    total = 0.0
    moment = [0.0, 0.0, 0.0]
    rows = []
    for name, link in links.items():
        inertial = link.find("inertial")
        if inertial is None:
            continue
        mass = float(inertial.find("mass").get("value"))
        cxyz, _ = parse_origin(inertial)
        pos, rot = world[name]
        com = [pos[i] + mat_vec(rot, cxyz)[i] for i in range(3)]
        total += mass
        for i in range(3):
            moment[i] += mass * com[i]
        rows.append((mass, name, com))

    cog = [m / total for m in moment]

    print("=" * 66)
    print(f"  MELVINN mass report — arm {'FORWARD' if args.arm_forward else 'at centre pose'}")
    print("=" * 66)
    print(f"{'mass (g)':>9}  {'%':>5}  link                       x      y      z")
    print("-" * 66)
    for mass, name, com in sorted(rows, reverse=True):
        print(f"{mass*1000:9.1f}  {mass/total*100:4.1f}%  {name:<22}"
              f"{com[0]:+6.3f} {com[1]:+6.3f} {com[2]:+6.3f}")
    print("-" * 66)
    print(f"{total*1000:9.1f}  100.0%  TOTAL")
    print()
    print(f"Centre of gravity:  x {cog[0]:+.3f} m   y {cog[1]:+.3f} m   z {cog[2]:+.3f} m")
    print(f"  (x+ is forward, z is height above the ground)")

    # ---- traction / torque -------------------------------------------------
    weight = total * G
    print()
    print("=" * 66)
    print("  Can the drivetrain move it?")
    print("=" * 66)
    print(f"Weight:                     {weight:.2f} N  ({total:.2f} kg)")

    for label, crr in (("rolling", CRR_ROLLING), ("BREAKAWAY from rest", CRR_BREAKAWAY)):
        force = crr * weight
        torque_per_wheel = force * 0.0325 / 4.0
        print()
        print(f"{label}  (Crr = {crr})")
        print(f"  force needed:             {force:.2f} N")
        print(f"  torque needed per wheel:  {torque_per_wheel*1000:.1f} mN-m")
        for spec, tq in (("low-spec JGA25", MOTOR_STALL_TORQUE_LOW),
                         ("high-spec JGA25", MOTOR_STALL_TORQUE_HIGH)):
            margin = tq / torque_per_wheel if torque_per_wheel else float("inf")
            verdict = "OK" if margin >= 1.0 else "NOT ENOUGH"
            print(f"    {spec:<13} {tq*1000:5.1f} mN-m  ->  margin x{margin:.1f}  {verdict}")

    print()
    print("NOTE: those motor figures are STALL torque at a full 6 V. Two motors")
    print("share each BTS7960 board and the NiMH sags under load, so delivered")
    print("torque is somewhat below the numbers above -- but with the JGA25s the")
    print("margin is large enough that the robot drives under the arm's weight.")


if __name__ == "__main__":
    main()
