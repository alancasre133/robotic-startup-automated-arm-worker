"""
MELVINN gets rickrolled -- song + lyric face + arm dance, all at once.

Finds (or downloads, first run) Never Gonna Give You Up into ~/music the
same way assistant.py does, plays it with mpg123, and while it plays:
  - the face cycles lyric cards and dancing eyes on the ST7789
  - the arm grooves in a background thread (safe angles around center)

Stops when the song ends or on Ctrl-C / ENTER. Arm returns to center,
face ends on a smile.

SAFETY: arm free to move before running.

Run:
    python3 robot_code/tests/melvinn_rickroll.py
"""

import os
import shutil
import subprocess
import threading
from time import sleep

from PIL import Image, ImageDraw, ImageFont

from st7789_raw import ST7789Raw

MUSIC_DIR = os.path.expanduser("~/music")
SONG_QUERY = "Rick Astley Never Gonna Give You Up official"
BEAT = 0.53                    # the song is ~113 BPM

disp = ST7789Raw(rotation=90)
W, H = disp.width, disp.height
BG = (20, 20, 30)
EYE = (230, 230, 255)
IRIS = (20, 60, 200)
ACCENT = (255, 120, 40)

# --- arm (same setup as assistant.py / melvinn_hello.py) --------------------
ARM_JOINTS = ("base", "shoulder", "elbow", "wrist", "wrist_rotate", "gripper")
ARM_CENTER = {"base": 90, "shoulder": 180, "elbow": 45,
              "wrist": 90, "wrist_rotate": 90, "gripper": 90}

try:
    import board
    import busio
    from adafruit_pca9685 import PCA9685
    from adafruit_motor import servo as servo_lib

    _pca = PCA9685(busio.I2C(board.SCL, board.SDA))
    _pca.frequency = 50
    ARM = {j: servo_lib.Servo(_pca.channels[i], min_pulse=500, max_pulse=2500)
           for i, j in enumerate(ARM_JOINTS)}
except Exception as e:
    print(f"(arm unavailable: {e} -- no dance, just song + face)")
    ARM = None


# --- music -------------------------------------------------------------------
def find_song():
    if os.path.isdir(MUSIC_DIR):
        for f in sorted(os.listdir(MUSIC_DIR)):
            if "never gonna" in f.lower() or "rick astley" in f.lower():
                return os.path.join(MUSIC_DIR, f)
    return None


def download_song():
    print("Downloading the song (first time only)...")
    os.makedirs(MUSIC_DIR, exist_ok=True)
    subprocess.run(
        ["yt-dlp", "-x", "--audio-format", "mp3", "--audio-quality", "5",
         "--output", os.path.join(MUSIC_DIR, "%(title)s.%(ext)s"),
         f"ytsearch1:{SONG_QUERY}"],
        check=True,
    )
    return find_song()


# --- face frames -------------------------------------------------------------
def _font(size):
    try:
        return ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
    except OSError:
        return ImageFont.load_default()


def lyric_card(line1, line2):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    f = _font(40)
    d.text((W // 2, H // 2 - 35), line1, font=f, fill=ACCENT, anchor="mm")
    d.text((W // 2, H // 2 + 25), line2, font=f, fill=EYE, anchor="mm")
    disp.display(img)


def dancing_eyes(dx, smile=True):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    for cx in (W // 3, 2 * W // 3):
        cy = H // 2 - 15
        d.ellipse((cx - 45, cy - 55, cx + 45, cy + 55), fill=EYE)
        d.ellipse((cx + dx - 18, cy - 22, cx + dx + 18, cy + 22), fill=IRIS)
    if smile:
        d.arc((W // 2 - 40, H - 85, W // 2 + 40, H - 35),
              start=20, end=160, fill=ACCENT, width=8)
    disp.display(img)


FACE_SEQUENCE = [
    lambda: lyric_card("NEVER", "GONNA"),
    lambda: dancing_eyes(-20),
    lambda: lyric_card("GIVE", "YOU UP"),
    lambda: dancing_eyes(20),
    lambda: lyric_card("NEVER", "GONNA"),
    lambda: dancing_eyes(-20),
    lambda: lyric_card("LET", "YOU DOWN"),
    lambda: dancing_eyes(20),
]


# --- arm dance (background thread) ------------------------------------------
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
    for j, a in ARM_CENTER.items():          # bow out gracefully
        ARM[j].angle = a


# --- the show ----------------------------------------------------------------
song = find_song() or download_song()
if not song:
    raise SystemExit("Could not find or download the song.")

print(f"Playing: {os.path.basename(song)}")
music = subprocess.Popen(
    ["mpg123", "-q", song],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)

stop_evt = threading.Event()
dancer = None
if ARM is not None:
    dancer = threading.Thread(target=arm_dance, args=(stop_evt,), daemon=True)
    dancer.start()

print("Dancing! Ctrl-C to stop early.")
try:
    i = 0
    while music.poll() is None:
        FACE_SEQUENCE[i % len(FACE_SEQUENCE)]()
        i += 1
        sleep(BEAT)
except KeyboardInterrupt:
    print("\nShow's over, folks.")
finally:
    stop_evt.set()
    if dancer is not None:
        dancer.join(timeout=3)
    if music.poll() is None:
        music.terminate()
    dancing_eyes(0, smile=True)
    print("Never gonna give you up. o7")
