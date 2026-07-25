"""
MELVINN introduces himself: blink -> "I'm MELVINN" -> arm wave.

Face runs on the in-repo raw ST7789V driver (st7789_raw.py). The arm is
the same PCA9685 setup as assistant.py (channels 0-5 in ARM_JOINTS order,
50 Hz, 500-2500us pulses); if the PCA9685 isn't reachable the show goes
on without the wave.

SAFETY: arm free to move before running.

Run:
    python3 robot_code/tests/melvinn_hello.py
"""

from time import sleep

from PIL import Image, ImageDraw, ImageFont

from st7789_raw import ST7789Raw

disp = ST7789Raw(rotation=90)
W, H = disp.width, disp.height

FACE_BG = (20, 20, 30)
EYE = (230, 230, 255)
IRIS = (20, 60, 200)

# --- arm (same constants as assistant.py) ----------------------------------
ARM_JOINTS = ("base", "shoulder", "elbow", "wrist", "wrist_rotate", "gripper")
ARM_CENTER = {"base": 90, "shoulder": 180, "elbow": 45,
              "wrist": 90, "wrist_rotate": 90, "gripper": 90}

try:
    import board
    import busio
    from adafruit_pca9685 import PCA9685
    from adafruit_motor import servo as servo_lib

    _i2c = busio.I2C(board.SCL, board.SDA)
    _pca = PCA9685(_i2c)
    _pca.frequency = 50
    ARM = {j: servo_lib.Servo(_pca.channels[i], min_pulse=500, max_pulse=2500)
           for i, j in enumerate(ARM_JOINTS)}
except Exception as e:
    print(f"(arm unavailable: {e} -- face-only show)")
    ARM = None


def glide(joint, start, end, step_delay=0.02):
    step = 1 if end >= start else -1
    for a in range(int(start), int(end) + step, step):
        ARM[joint].angle = a
        sleep(step_delay)


# --- face frames ------------------------------------------------------------
def eyes(openness=1.0, pupil_dx=0, mouth=None):
    """openness 1.0 = wide open, 0.0 = closed. mouth: None or 'smile'."""
    img = Image.new("RGB", (W, H), FACE_BG)
    d = ImageDraw.Draw(img)
    for cx in (W // 3, 2 * W // 3):
        cy = H // 2 - 15
        ry = max(4, int(55 * openness))
        if openness < 0.15:
            d.line((cx - 45, cy, cx + 45, cy), fill=EYE, width=10)
        else:
            d.ellipse((cx - 45, cy - ry, cx + 45, cy + ry), fill=EYE)
            px = cx + pupil_dx
            pry = min(22, ry - 2)
            d.ellipse((px - 18, cy - pry, px + 18, cy + pry), fill=IRIS)
            d.ellipse((px - 6, cy - pry + 6, px + 4, cy - pry + 16),
                      fill=(255, 255, 255))
    if mouth == "smile":
        d.arc((W // 2 - 40, H - 85, W // 2 + 40, H - 35),
              start=20, end=160, fill=EYE, width=8)
    disp.display(img)


def blink(times=1):
    for _ in range(times):
        for o in (0.6, 0.2, 0.0, 0.2, 0.6, 1.0):
            eyes(openness=o)
            sleep(0.04)


def _font(size):
    try:
        return ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
    except OSError:
        return ImageFont.load_default()


def say_name():
    img = Image.new("RGB", (W, H), FACE_BG)
    d = ImageDraw.Draw(img)
    small, big = _font(28), _font(52)
    d.text((W // 2, 60), "I'm", font=small, fill=EYE, anchor="mm")
    d.text((W // 2, 125), "MELVINN", font=big, fill=(80, 160, 255), anchor="mm")
    d.arc((W // 2 - 40, H - 75, W // 2 + 40, H - 30),
          start=20, end=160, fill=EYE, width=8)
    disp.display(img)


# --- the show ----------------------------------------------------------------
print("Waking up...")
eyes(openness=0.0)
sleep(0.8)
blink()
eyes()
sleep(0.6)
blink(2)
sleep(0.3)

print("Introducing...")
say_name()
sleep(2.5)

if ARM is not None:
    print("Waving...")
    eyes(mouth="smile")
    for j, a in ARM_CENTER.items():          # settle at safe center pose
        ARM[j].angle = a
    sleep(0.6)
    glide("wrist", 90, 130)                  # up
    for _ in range(2):                       # wave-wave
        glide("wrist", 130, 60, 0.012)
        glide("wrist", 60, 130, 0.012)
    glide("wrist", 130, 90)                  # back to rest
else:
    eyes(mouth="smile")
    sleep(1.5)

eyes(mouth="smile")
sleep(1.5)
blink()
eyes(mouth="smile")
print("That's MELVINN. o7")
