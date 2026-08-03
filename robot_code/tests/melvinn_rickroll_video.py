"""
MELVINN rickroll, video edition -- plays the Never Gonna Give You Up VIDEO
on the face screen while the arm dances, and the screen ALTERNATES between
the video and a squircle-happy celebration face.

Same video + arm groove as melvinn_rickroll.py, but instead of lyric cards
the panel shows the real decoded video for a few seconds, then cuts to a
bouncing squircle-happy "party" face for a beat, back and forth, in time
with the music.

How the alternation stays in sync: one ffmpeg process decodes video to
RGB565 frames on a pipe and sends audio straight to the speaker on its own
clock. We read EVERY frame off the pipe (so ffmpeg + audio never stall) --
during a celebration window we just blit the party face instead of the
frame we read. Audio keeps flowing; only what's shown changes.

SAFETY: arm free to move before running.

Run:
    python3 robot_code/tests/melvinn_rickroll_video.py
"""

import os
import shutil
import subprocess
import threading
from time import monotonic, sleep

from PIL import Image, ImageDraw

from st7789_raw import ST7789Raw

VIDEO_DIR = os.path.expanduser("~/videos")
VIDEO_QUERY = "Rick Astley Never Gonna Give You Up official video"
AUDIO_DEVICE = "plughw:1,0"     # USB speakerphone (same as assistant.py)
VIDEO_FPS = 12

VIDEO_WINDOW = 6.0              # seconds of real video before a celebration
CELEBRATE_WINDOW = 2.0         # seconds of party face
CEL_FRAME = 0.18               # party-face animation step (seconds)

disp = ST7789Raw(rotation=90)
W, H = disp.width, disp.height
FRAME_BYTES = W * H * 2

# squircle palette (matches face_styles.py)
EX1, EX2 = W // 3, 2 * W // 3
EY = H // 2 - 15
MX, MY = W // 2, H - 55
SQ_BG, SQ_EYE, SQ_PUP = (14, 22, 34), (235, 240, 245), (10, 40, 90)


def celebrate_face(i):
    """Squircle-happy 'party' face: pupils bounce, big grin, sparkles blink."""
    img = Image.new("RGB", (W, H), SQ_BG)
    d = ImageDraw.Draw(img)
    dx = (-14, 0, 14, 0)[i % 4]
    for cx in (EX1, EX2):
        d.rounded_rectangle((cx - 40, EY - 45, cx + 40, EY + 45), radius=20, fill=SQ_EYE)
        d.rounded_rectangle((cx - 16 + dx, EY - 18, cx + 16 + dx, EY + 18),
                            radius=10, fill=SQ_PUP)
    for sgn, cx in ((1, EX1), (-1, EX2)):          # raised happy brows
        d.line((cx - sgn * 38, EY - 64, cx + sgn * 38, EY - 64), fill=SQ_EYE, width=9)
    d.arc((MX - 45, MY - 30, MX + 45, MY + 25), start=15, end=165,
          fill=SQ_EYE, width=10)                   # big open smile
    if i % 2 == 0:                                 # blinking sparkles
        for sx, sy in ((30, 42), (W - 30, 52), (42, H - 40), (W - 42, H - 46)):
            d.line((sx - 9, sy, sx + 9, sy), fill=(255, 220, 120), width=4)
            d.line((sx, sy - 9, sx, sy + 9), fill=(255, 220, 120), width=4)
    return img


# --- video file --------------------------------------------------------------
def find_video():
    if not os.path.isdir(VIDEO_DIR):
        return None
    vids = [os.path.join(VIDEO_DIR, f) for f in os.listdir(VIDEO_DIR)
            if f.lower().endswith((".mp4", ".mkv", ".webm"))
            and ("never gonna" in f.lower() or "rick astley" in f.lower())]
    return max(vids, key=os.path.getmtime) if vids else None


def download_video():
    print("Downloading the video (first time only)...")
    os.makedirs(VIDEO_DIR, exist_ok=True)
    subprocess.run(
        ["yt-dlp", "-f", "b[height<=360]",
         "--output", os.path.join(VIDEO_DIR, "%(title)s.%(ext)s"),
         f"ytsearch1:{VIDEO_QUERY}"],
        check=True,
    )
    return find_video()


# --- arm dance (same routine as melvinn_rickroll.py) ------------------------
ARM_JOINTS = ("base", "shoulder", "elbow", "wrist", "wrist_rotate", "gripper")
ARM_CENTER = {"base": 90, "shoulder": 180, "elbow": 45,
              "wrist": 90, "wrist_rotate": 90, "gripper": 90}
DANCE_MOVES = [
    {"wrist": 130, "base": 70},
    {"wrist": 60,  "base": 110},
    {"wrist": 130, "wrist_rotate": 60},
    {"wrist": 60,  "wrist_rotate": 120},
    {"base": 60,   "gripper": 40},
    {"base": 120,  "gripper": 120},
    {"wrist": 120, "elbow": 60},
    {"wrist": 70,  "elbow": 35},
]
BEAT = 0.53

try:
    import board
    import busio
    from adafruit_pca9685 import PCA9685
    from adafruit_motor import servo as servo_lib

    # PCA9685 is on the software i2c-gpio bus 3 (GPIO4 SDA / GPIO23 SCL); the
    # Pi's hardware I2C (bus 1, GPIO2/3) was damaged. Override w/ MELVINN_I2C_BUS.
    import os
    _bus = int(os.environ.get("MELVINN_I2C_BUS", "3"))
    try:
        from adafruit_extended_bus import ExtendedI2C
        _i2c = ExtendedI2C(_bus)
    except ImportError:
        _i2c = busio.I2C(board.SCL, board.SDA)
    _pca = PCA9685(_i2c)
    _pca.frequency = 50
    ARM = {j: servo_lib.Servo(_pca.channels[i], min_pulse=500, max_pulse=2500)
           for i, j in enumerate(ARM_JOINTS)}
except Exception as e:
    print(f"(arm unavailable: {e} -- video plays without the dance)")
    ARM = None


def arm_dance(stop_evt):
    for j, a in ARM_CENTER.items():
        ARM[j].angle = a
    sleep(0.5)
    i = 0
    while not stop_evt.is_set():
        for joint, angle in DANCE_MOVES[i % len(DANCE_MOVES)].items():
            ARM[joint].angle = angle
        i += 1
        stop_evt.wait(BEAT)
    for j, a in ARM_CENTER.items():
        ARM[j].angle = a


# --- the show ----------------------------------------------------------------
if not shutil.which("ffmpeg"):
    raise SystemExit("ffmpeg is not installed.")
video = find_video() or download_video()
if not video:
    raise SystemExit("Could not find or download the video.")

print(f"Playing: {os.path.basename(video)}")
vf = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
      f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,fps={VIDEO_FPS}")
ff = subprocess.Popen(
    ["ffmpeg", "-loglevel", "error", "-re", "-i", video,
     "-map", "0:v:0", "-vf", vf,
     "-f", "rawvideo", "-pix_fmt", "rgb565be", "pipe:1",
     "-map", "0:a:0?", "-f", "alsa", AUDIO_DEVICE],
    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
)

stop_evt = threading.Event()
dancer = None
if ARM is not None:
    dancer = threading.Thread(target=arm_dance, args=(stop_evt,), daemon=True)
    dancer.start()

print("Playing! Screen alternates video <-> party face. Ctrl-C to stop.")
mode = "video"
phase_start = monotonic()
cel_i = 0
last_cel = 0.0
try:
    while True:
        data = ff.stdout.read(FRAME_BYTES)          # always drain -> audio flows
        if not data or len(data) < FRAME_BYTES:
            break
        now = monotonic()
        if mode == "video" and now - phase_start >= VIDEO_WINDOW:
            mode, phase_start = "celebrate", now
        elif mode == "celebrate" and now - phase_start >= CELEBRATE_WINDOW:
            mode, phase_start, last_cel = "video", now, 0.0

        if mode == "video":
            disp.display_raw565(data)
        elif now - last_cel >= CEL_FRAME:
            disp.display(celebrate_face(cel_i))
            cel_i += 1
            last_cel = now
except KeyboardInterrupt:
    print("\nShow's over, folks.")
finally:
    stop_evt.set()
    if dancer is not None:
        dancer.join(timeout=3)
    if ff.poll() is None:
        ff.terminate()
        try:
            ff.wait(timeout=2)
        except subprocess.TimeoutExpired:
            ff.kill()
    disp.display(celebrate_face(0))
    print("Never gonna give you up. o7")
