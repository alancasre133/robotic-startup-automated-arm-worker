# AI Vision — Faces, Objects, Hands

Adding "AI" to the robot: detect things in the camera feed and react (drive the
motors, later move the arm). What's realistic depends heavily on the hardware —
the **Pi 3A+ has 512 MB RAM, a 32-bit OS, and no GPU/AI accelerator**, so
everything runs on the 4 CPU cores.

## What runs on the Pi 3A+ (and what doesn't)

| Task | Best tool | On this Pi? | Notes |
|------|-----------|-------------|-------|
| **Faces** | OpenCV Haar cascade | ✅ realtime-ish (~8–15 fps) | No new hardware. See `robot_code/tests/vision_track.py` |
| **Objects** (person, cup, bottle… 80 COCO classes) | TensorFlow Lite (SSD-MobileNet, quantized) | ⚠️ ~1–3 fps | Usable for slow reactions, not smooth tracking |
| **Hands** (21 finger landmarks / gestures) | Google MediaPipe | ❌ | No 32-bit-Pi pip wheels + too heavy for 512 MB |
| **Scene understanding** ("find the red cup", "is the person waving?") | **Claude vision API** | ✅ (cloud) | ~1–2 s round-trip — great for *decisions*, too slow for *tracking* |

**The takeaway:** think in two layers —
- **Reflexes** (fast, on-Pi): face/motion tracking that keeps a target centered.
- **Brain** (smart, cloud): Claude looks at a frame and decides *what to do*
  (ties into [voice-assistant.md](voice-assistant.md) / `robot_code/tests/assistant.py`).

## Tier 1 — Face tracking (works now): `vision_track.py`

Fully on-device, no extra hardware. Pipeline:

**capture frame → Haar face detect → pick the biggest face → compare its X to the
frame center → pulse the motors to re-center it → stream the annotated frame.**

You watch the boxed, labelled video in a browser (locally or over Tailscale) while
the robot physically turns to follow you.

### Setup (one time)
```bash
sudo apt install -y python3-opencv opencv-data
```

### Run
```bash
# the camera is single-user: stop the auto-start stream first
sudo systemctl stop camera-stream

python3 robot_code/tests/vision_track.py
# watch http://<pi-ip>:8000  (detection only until you arm the motors)
```

### Make it actually drive
1. Confirm faces get boxed in the stream.
2. **Put the wheels off the ground.**
3. Edit `vision_track.py`: set `DRIVE_MOTORS = True`.
4. Re-run. Move around — it should pivot to keep your face centered.
   - Turns the **wrong way**? Swap `LEFT`/`RIGHT` (or a motor's forward/backward).
   - Twitchy / overshoots? Raise `DEAD_ZONE` or lower `PULSE`.
   - Slow / low frame rate? Drop `WIDTH, HEIGHT` to `480, 360` or `320, 240`.

> ⚠️ Driving the motors can drop the WiFi (the grounding gotcha in the main
> README) — the stream may stutter while it turns until that fix is applied.

## Tier 2 — Object detection (next): TensorFlow Lite

For general objects, run a quantized **SSD-MobileNet** on TFLite. On Raspberry Pi
OS, `pip` pulls prebuilt ARM wheels from **piwheels**:
```bash
python3 -m venv ~/tflite && source ~/tflite/bin/activate
pip install tflite-runtime opencv-python-headless
# + a .tflite model and its COCO label file
```
Expect ~1–3 fps at 300×300. Good for "stop when you see a person" or "drive toward
the bottle", not for smooth tracking. (A follow-up `vision_objects.py` can reuse
the same capture + stream + motor scaffolding as `vision_track.py`.)

## Tier 3 — Hands & smooth objects: needs more muscle

MediaPipe (the good hand/pose tracker) won't run well here. Options, cheapest first:

1. **Cheap gesture hack** — no ML: detect motion / a waving hand with frame
   differencing (`cv2.absdiff`) to trigger an action. Crude but free.
2. **Coral USB Accelerator** (~$60, Edge TPU) — plugs into USB, runs object
   detection in *real time* and enables more models. Costs one USB port (use the
   planned hub). See [../HARDWARE.md](../HARDWARE.md).
3. **Move the vision to a Pi 4/5 (64-bit)** — unlocks MediaPipe hands/pose and
   much higher frame rates. The 3A+ stays as the driver, or gets replaced.
4. **Offload** — the Pi streams frames to your laptop/server (or Claude), which
   does the heavy detection and sends back commands. No robot hardware change.

## Roadmap — reflexes + brain

The end state combines both layers:
- **On-Pi reflexes** keep a target centered and avoid obstacles (fast loop).
- **Claude (brain)** periodically looks at a frame + hears a voice command and
  picks the goal ("go to the cup and pick it up"), issuing high-level actions
  that the reflex layer carries out. See `robot_code/tests/assistant.py`.
