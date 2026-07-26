"""
Smart arm control — the "where should the arm go" logic, kept out of the brain.

MELVINN's camera is FIXED to the chassis (not on the gripper), so this is
vision-GUIDED aiming, not closed-loop eye-in-hand servoing: it reads where the
object sits in the camera frame (its horizontal bearing) and rotates the arm's
base to face it, then reaches. So a grab adapts to a left/right object instead
of assuming it's dead centre — the arm "aims itself".

Future upgrades live here too:
  - true visual servoing (needs the camera moved onto the arm/gripper),
  - inverse kinematics (compute joint angles for a target x,y,z — e.g. via
    `ikpy`), pairing an IK coarse reach with camera correction for the slop.

These are PURE functions — no hardware, no import of assistant — so the brain
(assistant.py) does the moving/speaking and this just decides the angles. That
keeps the logic testable and swappable.
"""

# --- Tuning ----------------------------------------------------------------
BASE_CENTER = 90.0    # base servo angle that points the arm straight ahead
BASE_GAIN = 70.0      # degrees of base swing per unit camera offset (-0.5..0.5)
BASE_SIGN = -1.0      # flip to +1.0 if the arm aims the WRONG way left/right
BASE_LIMIT = 45.0     # never swing the base more than this from centre (safety)


def bearing_to_base(offset: float) -> float:
    """Map a camera horizontal offset to a base servo angle.

    offset: -0.5 = object at far left of frame, 0 = centred, +0.5 = far right.
    Returns a base angle clamped near centre so the arm can't swing wildly.
    """
    swing = BASE_SIGN * BASE_GAIN * float(offset)
    swing = max(-BASE_LIMIT, min(BASE_LIMIT, swing))
    base = BASE_CENTER + swing
    return max(0.0, min(180.0, base))


def plan_reach(reach_pose: dict, base_angle: float) -> dict:
    """The joint angles to reach the object: the calibrated reach pose, but with
    the base swung to face the object's bearing instead of straight ahead.

    reach_pose: the tuned {joint: angle} reach dict from assistant.ARM_POSES.
    Returns a new dict (doesn't mutate the input).
    """
    plan = dict(reach_pose)
    plan["base"] = base_angle
    return plan


def aim_side(base_angle: float) -> str:
    """Human-readable direction the arm aimed, for narration."""
    if base_angle > BASE_CENTER + 3:
        return "left" if BASE_SIGN < 0 else "right"
    if base_angle < BASE_CENTER - 3:
        return "right" if BASE_SIGN < 0 else "left"
    return "centre"
