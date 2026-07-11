"""
Face-tracking vision demo.

Detects faces on the Pi with OpenCV, draws them on a live MJPEG stream, and
(optionally) turns the robot to keep the nearest face centered — a first taste
of "AI" reflexes running fully on the Pi 3A+.

Run on the Pi with SYSTEM python3 (picamera2 + OpenCV are system packages).
Install OpenCV + the cascade data first (one time):

    sudo apt install -y python3-opencv opencv-data

The camera can only be opened by one program at a time, so if the auto-start
stream service is running, stop it first:

    sudo systemctl stop camera-stream

Then run:

    python3 robot_code/tests/vision_track.py

Watch the annotated feed at  http://<pi-ip>:8000  (or the Tailscale IP from
anywhere). Every face is boxed; the tracked target is highlighted and the motor
decision (turn left / right / centered) is drawn on the frame.

SAFETY: motor driving is OFF by default (DRIVE_MOTORS = False) so you can watch
detection first. When you turn it on, put the WHEELS OFF THE GROUND for the first
test — the robot will pivot on its own.
"""

import io
import os
import time
import socketserver
from http import server
from threading import Condition, Thread

import cv2
from libcamera import Transform
from picamera2 import Picamera2

# ---- config -----------------------------------------------------------------
WIDTH, HEIGHT, PORT = 640, 480, 8000
DETECT_SCALE = 0.5        # detect on a half-size image => faster on the Pi 3
DEAD_ZONE = 0.15          # |offset| under this (fraction of width) counts as centered
PULSE = 0.12              # seconds the motors run per correction step
DRIVE_MOTORS = False      # <<< set True to let it actually turn (WHEELS UP first!)
FLIP_180 = True           # camera is physically mounted upside down on this robot

# ---- motors (only imported/used if DRIVE_MOTORS) ----------------------------
if DRIVE_MOTORS:
    from gpiozero import Motor
    # Same pins as motor_test.py. If it turns the WRONG way when you test,
    # swap LEFT/RIGHT here, or swap forward/backward on one motor.
    LEFT = Motor(forward=16, backward=20)    # motor A
    RIGHT = Motor(forward=27, backward=22)   # motor B

    def stop():
        LEFT.stop()
        RIGHT.stop()

    def turn_left():
        LEFT.backward(); RIGHT.forward()
        time.sleep(PULSE); stop()

    def turn_right():
        LEFT.forward(); RIGHT.backward()
        time.sleep(PULSE); stop()
else:
    def stop(): pass
    def turn_left(): pass
    def turn_right(): pass

# ---- face detector ----------------------------------------------------------
# cv2.data.haarcascades points at the bundled cascades; fall back to the apt
# opencv-data path if needed.
_cascade_dir = getattr(getattr(cv2, "data", None), "haarcascades", "")
_cascade = os.path.join(_cascade_dir, "haarcascade_frontalface_default.xml")
if not os.path.exists(_cascade):
    _cascade = "/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml"
FACE = cv2.CascadeClassifier(_cascade)
if FACE.empty():
    raise SystemExit(
        f"Could not load face cascade at {_cascade}\n"
        "Install it with:  sudo apt install -y opencv-data"
    )

# ---- MJPEG plumbing (same shape as camera_stream.py) ------------------------
class FrameBus:
    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def set(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()


bus = FrameBus()

PAGE = f"""<!doctype html>
<title>Robot vision</title>
<body style="margin:0;background:#111">
  <img src="stream.mjpg" style="width:100%;max-width:{WIDTH}px;display:block;margin:auto">
</body>
"""


class Handler(server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(301)
            self.send_header("Location", "/index.html")
            self.end_headers()
        elif self.path == "/index.html":
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/stream.mjpg":
            self.send_response(200)
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=FRAME")
            self.end_headers()
            try:
                while True:
                    with bus.condition:
                        bus.condition.wait()
                        frame = bus.frame
                    self.wfile.write(b"--FRAME\r\n")
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(frame)))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
            except Exception:
                pass  # client disconnected — fine
        else:
            self.send_error(404)
            self.end_headers()


class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


# ---- capture -> detect -> drive loop ----------------------------------------
def vision_loop():
    picam2 = Picamera2()
    # "RGB888" gives an array OpenCV reads as BGR (colors come out correct).
    transform = Transform(hflip=1, vflip=1) if FLIP_180 else Transform()
    picam2.configure(picam2.create_video_configuration(
        main={"size": (WIDTH, HEIGHT), "format": "RGB888"}, transform=transform))
    picam2.start()
    center_x = WIDTH / 2
    try:
        while True:
            frame = picam2.capture_array()                     # H x W x 3
            small = cv2.resize(frame, None, fx=DETECT_SCALE, fy=DETECT_SCALE)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            found = FACE.detectMultiScale(gray, scaleFactor=1.15,
                                          minNeighbors=5, minSize=(24, 24))
            # scale detections back up to the full frame
            faces = [(int(x / DETECT_SCALE), int(y / DETECT_SCALE),
                      int(w / DETECT_SCALE), int(h / DETECT_SCALE))
                     for (x, y, w, h) in found]

            for (x, y, w, h) in faces:
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 180, 0), 2)

            target = max(faces, key=lambda b: b[2] * b[3], default=None)
            action = "no face"
            if target is not None:
                x, y, w, h = target
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 255), 3)
                offset = ((x + w / 2) - center_x) / WIDTH       # -0.5 .. 0.5
                if offset < -DEAD_ZONE:
                    action = "turn left"; turn_left()
                elif offset > DEAD_ZONE:
                    action = "turn right"; turn_right()
                else:
                    action = "centered"; stop()

            cv2.putText(frame, action, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                        1.0, (0, 255, 255), 2)
            ok, jpg = cv2.imencode(".jpg", frame)
            if ok:
                bus.set(jpg.tobytes())
    finally:
        stop()
        picam2.stop()


if __name__ == "__main__":
    Thread(target=vision_loop, daemon=True).start()
    print(f"Vision stream on http://<pi-ip>:{PORT}   (Ctrl-C to stop)")
    print(f"DRIVE_MOTORS = {DRIVE_MOTORS}  "
          f"(motors {'ARMED — wheels up!' if DRIVE_MOTORS else 'off, detection only'})")
    try:
        StreamingServer(("", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        pass
