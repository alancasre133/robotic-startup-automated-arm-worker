"""
Interactive, face-aware robot console.

While it runs it does BOTH at once:
  - watches the camera and reacts when it sees a face (default: says "papoi"),
    with a 5-second cooldown so it doesn't spam;
  - takes commands you type, e.g.:

      say hello everyone              -> speaks the text out loud
      forward 2 seconds               -> drives (forward / back / left / right / turn)
      turn 1                          -> turn for 1 second
      stop                            -> stops the motors immediately
      when you see my face say hi     -> change what it does when it spots a face
      when you identify my face do forward 2
      quit                            -> exit

Command understanding + the voice are reused from assistant.py, so it uses the
Claude brain when a key is set and falls back to the free offline parser otherwise.
Voice INPUT (talking instead of typing) is the next step — see docs/voice-assistant.md.

Run on the Pi with SYSTEM python3 (picamera2 + OpenCV are system packages):
    python3 robot_code/tests/papoi.py

One-time: sudo apt install -y python3-opencv opencv-data espeak-ng
The camera is single-user — stop any other camera program first
(`sudo systemctl stop camera-stream`, or Ctrl-C camera_stream.py). Ctrl-C to stop.
"""

import os
import time
import threading

import cv2
from libcamera import Transform
from picamera2 import Picamera2

# Reuse the robot's voice + brain from assistant.py (same folder).
from assistant import speak, think, robot_drive

WIDTH, HEIGHT = 640, 480
DETECT_SCALE = 0.5              # detect on a half-size frame => faster on the Pi 3
COOLDOWN = 5.0                 # seconds of quiet after each face reaction
DEFAULT_FACE_ACTION = "say papoi"
FLIP_180 = True                 # camera is physically mounted upside down on this robot

# --- face detector -----------------------------------------------------------
_dir = getattr(getattr(cv2, "data", None), "haarcascades", "")
_cascade = os.path.join(_dir, "haarcascade_frontalface_default.xml")
if not os.path.exists(_cascade):
    _cascade = "/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml"
FACE = cv2.CascadeClassifier(_cascade)
if FACE.empty():
    raise SystemExit(f"Could not load face cascade at {_cascade}")

# --- shared state ------------------------------------------------------------
history: list = []                  # conversation memory for the brain
face_action = DEFAULT_FACE_ACTION   # what to do when a face is seen
action_lock = threading.Lock()      # run one action (move/speak) at a time
stop_event = threading.Event()


def set_face_action(text: str) -> str:
    """Parse 'when you see my face do X' -> store X as the face reaction."""
    global face_action
    low = text.lower()
    if " do " in low:
        action = text[low.index(" do ") + 4:].strip()
    elif "face" in low:
        action = text[low.index("face") + 4:].lstrip(" ,").strip()
    else:
        action = ""
    face_action = action or DEFAULT_FACE_ACTION
    return f"Okay. When I see your face I will: {face_action}"


def handle_command(text: str) -> str:
    """Turn one command into a spoken reply (and any motion it triggers)."""
    low = text.lower().strip()
    # reprogram the face-trigger action
    if "face" in low and (
        any(k in low for k in ("when", "if", "whenever", "identify", "each time"))
        or low.startswith("on face")
    ):
        return set_face_action(text)
    # everything else (say / move / chat) goes to the brain (Claude or offline)
    return think(text, history)


def face_loop():
    """Background: watch the camera, react when a face appears."""
    try:
        picam2 = Picamera2()
        transform = Transform(hflip=1, vflip=1) if FLIP_180 else Transform()
        picam2.configure(picam2.create_video_configuration(
            main={"size": (WIDTH, HEIGHT), "format": "RGB888"}, transform=transform))
        picam2.start()
    except Exception as exc:
        print(f"[camera unavailable: {exc}] — face greeting off; typed commands still work")
        return
    last = 0.0
    try:
        while not stop_event.is_set():
            frame = picam2.capture_array()
            small = cv2.resize(frame, None, fx=DETECT_SCALE, fy=DETECT_SCALE)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            faces = FACE.detectMultiScale(gray, scaleFactor=1.15,
                                          minNeighbors=5, minSize=(24, 24))
            now = time.time()
            if len(faces) and now - last >= COOLDOWN:
                last = now
                # don't queue up if a typed command / previous reaction is running
                if action_lock.acquire(blocking=False):
                    try:
                        print(f"[face] -> {face_action}")
                        speak(handle_command(face_action))
                    finally:
                        action_lock.release()
            time.sleep(0.03)
    finally:
        picam2.stop()


def main():
    print("Interactive robot console — watching for faces + taking commands.")
    print("Try:  say hello   |   forward 2 seconds   |   when you see my face say hi")
    print("Type 'quit' to exit.\n")
    threading.Thread(target=face_loop, daemon=True).start()
    speak("Hi, I am ready.")
    try:
        while True:
            text = input("you> ").strip()
            if not text:
                continue
            if text.lower() in ("quit", "exit", "q"):
                break
            if "stop" in text.lower():        # instant stop, no waiting on the brain
                speak(robot_drive("stop"))
                continue
            with action_lock:
                speak(handle_command(text))
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        stop_event.set()
        robot_drive("stop")
        print("\nbye")


if __name__ == "__main__":
    main()
