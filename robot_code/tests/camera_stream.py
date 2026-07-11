"""
Live camera stream over WiFi — view the robot's camera in a browser.

No screen on the Pi required. Run on the Pi with SYSTEM Python (so picamera2 is
available — not inside a venv):

    python3 camera_stream.py

Then open  http://<pi-ip>:8000  on any device on the same WiFi
(e.g. http://192.168.16.60:8000). Press Ctrl-C on the Pi to stop.
"""

import io
import socketserver
from http import server
from threading import Condition

from libcamera import Transform
from picamera2 import Picamera2
from picamera2.encoders import JpegEncoder
from picamera2.outputs import FileOutput

WIDTH, HEIGHT, PORT = 640, 480, 8000  # modest size — kinder to flaky WiFi
FLIP_180 = True  # camera is physically mounted upside down on this robot

PAGE = f"""<!doctype html>
<title>Robot camera</title>
<body style="margin:0;background:#111">
  <img src="stream.mjpg" style="width:100%;max-width:{WIDTH}px;display:block;margin:auto">
</body>
"""


class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()


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
                    with output.condition:
                        output.condition.wait()
                        frame = output.frame
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


picam2 = Picamera2()
transform = Transform(hflip=1, vflip=1) if FLIP_180 else Transform()
picam2.configure(picam2.create_video_configuration(main={"size": (WIDTH, HEIGHT)}, transform=transform))
output = StreamingOutput()
picam2.start_recording(JpegEncoder(), FileOutput(output))
print(f"Streaming on http://<pi-ip>:{PORT}   (Ctrl-C to stop)")

try:
    StreamingServer(("", PORT), Handler).serve_forever()
finally:
    picam2.stop_recording()
