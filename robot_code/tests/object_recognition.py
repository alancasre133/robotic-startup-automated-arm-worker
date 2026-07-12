"""
Object recognition by ORB feature enrollment — teach the robot specific objects
by SHOWING them to the camera, then recognize them live. No training, no model
downloads: fully on-device, using OpenCV's free ORB features.

How it works:
  ENROLL     fill the frame with the object -> extract ORB keypoints +
             descriptors -> save them under a name.
  RECOGNIZE  on a live frame, extract ORB features, match against each enrolled
             object (Hamming distance + Lowe's ratio test), and report the best
             match with its bearing (left/right) and apparent size.

Best for TEXTURED, RIGID, fairly FLAT objects with a distinctive pattern (a
labeled box, a book cover, a patterned can). It does NOT work on plain
solid-colour, shiny/reflective, transparent, or deformable objects — those have
no stable features to match. If recognition is poor, that's usually why.

Enrolled objects live in ~/robot_objects/ : one <name>.npz per object plus a
registry.json that also holds each object's (future) grasp profile.
"""

import json
import os

import cv2
import numpy as np

STORE_DIR = os.path.expanduser("~/robot_objects")
REGISTRY = os.path.join(STORE_DIR, "registry.json")

N_FEATURES = 500        # ORB keypoints per frame
RATIO = 0.75            # Lowe's ratio test (lower = stricter matches)
MIN_GOOD_MATCHES = 12   # fewer good matches than this = not a confident detection

_orb = None
_matcher = None


def _engine():
    global _orb, _matcher
    if _orb is None:
        _orb = cv2.ORB_create(nfeatures=N_FEATURES)
        _matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    return _orb, _matcher


def _load_registry() -> dict:
    if os.path.exists(REGISTRY):
        try:
            return json.load(open(REGISTRY))
        except (OSError, ValueError):
            return {}
    return {}


def _save_registry(reg: dict) -> None:
    os.makedirs(STORE_DIR, exist_ok=True)
    with open(REGISTRY, "w") as f:
        json.dump(reg, f, indent=2)


def enroll(frame, name: str) -> int:
    """Extract ORB features from `frame` and save them under `name`.

    Fill the frame with the object (minimal background) for the cleanest result.
    Returns the number of features stored, or 0 if too few (object too plain /
    shiny / blurry to recognize reliably). Re-enrolling a name replaces it.
    """
    orb, _ = _engine()
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    kp, des = orb.detectAndCompute(gray, None)
    if des is None or len(des) < MIN_GOOD_MATCHES:
        return 0
    os.makedirs(STORE_DIR, exist_ok=True)
    fname = f"{name}.npz"
    np.savez(os.path.join(STORE_DIR, fname), des=des)
    reg = _load_registry()
    # keep any existing grasp profile for this name (learned separately, later)
    grasp = reg.get(name, {}).get("grasp", {})
    reg[name] = {"file": fname, "grasp": grasp}
    _save_registry(reg)
    return len(des)


def list_objects() -> list:
    return list(_load_registry().keys())


def grasp_profile(name: str) -> dict:
    """The saved grasp profile for an object (empty until calibrated in Stage 2)."""
    return _load_registry().get(name, {}).get("grasp", {})


def _load_descriptors(name: str):
    reg = _load_registry()
    if name not in reg:
        return None
    path = os.path.join(STORE_DIR, reg[name]["file"])
    if not os.path.exists(path):
        return None
    return np.load(path)["des"]


def recognize(frame, name: str = None) -> dict:
    """Recognize enrolled objects in `frame`.

    If `name` is given, look only for that object; otherwise return the best
    match among all enrolled objects. Returns:
      seen      -> bool
      name      -> matched object name (or None)
      offset    -> -0.5 (far left) .. +0.5 (far right), 0.0 = centred
      area_frac -> matched region as a fraction of the frame (bigger = closer)
      matches   -> number of good feature matches (confidence)
    """
    orb, matcher = _engine()
    miss = {"seen": False, "name": None, "offset": 0.0, "area_frac": 0.0, "matches": 0}
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    kp, des = orb.detectAndCompute(gray, None)
    if des is None or len(des) < 2:
        return miss
    h, w = gray.shape

    names = [name] if name else list_objects()
    best = miss
    for nm in names:
        ref = _load_descriptors(nm)
        if ref is None or len(ref) < 2:
            continue
        good = []
        for pair in matcher.knnMatch(des, ref, k=2):
            if len(pair) == 2 and pair[0].distance < RATIO * pair[1].distance:
                good.append(pair[0])
        if len(good) < MIN_GOOD_MATCHES or len(good) <= best["matches"]:
            continue
        # locate: centroid + bounding box of the matched live-frame keypoints
        pts = np.float32([kp[m.queryIdx].pt for m in good])
        cx = float(pts[:, 0].mean())
        bbox_w = float(pts[:, 0].max() - pts[:, 0].min())
        bbox_h = float(pts[:, 1].max() - pts[:, 1].min())
        best = {
            "seen": True,
            "name": nm,
            "offset": (cx - w / 2) / w,
            "area_frac": (bbox_w * bbox_h) / float(w * h),
            "matches": len(good),
        }
    return best
