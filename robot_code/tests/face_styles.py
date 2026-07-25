"""
MELVINN face style fashion show -- 20 different looks, 20 seconds each.

Cycles every style on the ST7789 face screen with its number + name in the
corner (and printed to the terminal) so you can pick the keeper. Loops until
Ctrl-C; ends on the classic smile.

Don't run while the assistant (or another face script) is using the screen.

Run:
    python3 robot_code/tests/face_styles.py
"""

import math
from time import sleep

from PIL import Image, ImageDraw, ImageFont

from st7789_raw import ST7789Raw

disp = ST7789Raw(rotation=90)
W, H = disp.width, disp.height
DWELL = 20                     # seconds per style

EX1, EX2 = W // 3, 2 * W // 3  # eye centres
EY = H // 2 - 15
MX, MY = W // 2, H - 60        # mouth centre


def base(bg):
    img = Image.new("RGB", (W, H), bg)
    return img, ImageDraw.Draw(img)


def smile(d, color=(230, 230, 255), width=8, dx=0):
    d.arc((MX - 40 + dx, MY - 25, MX + 40 + dx, MY + 25),
          start=20, end=160, fill=color, width=width)


def star_points(cx, cy, outer, inner, points=5):
    pts = []
    for i in range(points * 2):
        r = outer if i % 2 == 0 else inner
        a = math.pi * i / points - math.pi / 2
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


# --- the 20 styles -----------------------------------------------------------
def s_classic():
    img, d = base((16, 18, 30))
    for cx in (EX1, EX2):
        d.ellipse((cx - 45, EY - 55, cx + 45, EY + 55), fill=(230, 230, 255))
        d.ellipse((cx - 18, EY - 22, cx + 18, EY + 22), fill=(20, 60, 200))
        d.ellipse((cx - 6, EY - 16, cx + 4, EY - 6), fill=(255, 255, 255))
    smile(d)
    return img


def s_cyclops():
    img, d = base((25, 20, 35))
    cx = W // 2
    d.ellipse((cx - 70, EY - 70, cx + 70, EY + 70), fill=(235, 235, 245))
    d.ellipse((cx - 32, EY - 32, cx + 32, EY + 32), fill=(0, 160, 170))
    d.ellipse((cx - 14, EY - 14, cx + 14, EY + 14), fill=(10, 20, 25))
    d.ellipse((cx - 24, EY - 28, cx - 8, EY - 12), fill=(255, 255, 255))
    smile(d, (235, 235, 245))
    return img


def s_pixel():
    img, d = base((5, 5, 12))
    px = 14
    for cx in (EX1, EX2):
        for gx in range(-2, 3):
            for gy in range(-2, 3):
                if abs(gx) == 2 and abs(gy) == 2:
                    continue                      # knock out corners
                d.rectangle((cx + gx * px - px // 2, EY + gy * px - px // 2,
                             cx + gx * px + px // 2, EY + gy * px + px // 2),
                            fill=(255, 60, 200))
        d.rectangle((cx - px // 2, EY - px // 2, cx + px // 2, EY + px // 2),
                    fill=(5, 5, 12))
    for gx in range(-3, 4):
        d.rectangle((MX + gx * px - px // 2, MY - px // 2,
                     MX + gx * px + px // 2, MY + px // 2),
                    fill=(255, 60, 200) if abs(gx) < 3 else (150, 30, 120))
    return img


def s_eve():
    img, d = base((2, 4, 8))
    for cx, tilt in ((EX1, 12), (EX2, -12)):
        d.polygon([(cx - 45, EY + tilt), (cx - 20, EY - 28 + tilt // 2),
                   (cx + 20, EY - 28 - tilt // 2), (cx + 45, EY - tilt),
                   (cx + 20, EY + 28 - tilt // 2), (cx - 20, EY + 28 + tilt // 2)],
                  fill=(60, 200, 255))
    return img                                   # no mouth -- EVE is all eyes


def s_visor():
    img, d = base((12, 8, 8))
    d.rounded_rectangle((30, EY - 26, W - 30, EY + 26), radius=26,
                        fill=(40, 0, 0), outline=(90, 20, 20), width=3)
    d.rounded_rectangle((MX - 45, EY - 14, MX + 45, EY + 14), radius=14,
                        fill=(255, 40, 30))
    d.ellipse((MX - 10, EY - 8, MX + 10, EY + 8), fill=(255, 160, 140))
    return img


def s_kawaii():
    img, d = base((255, 190, 200))
    for cx in (EX1, EX2):
        d.arc((cx - 38, EY - 30, cx + 38, EY + 40),
              start=200, end=340, fill=(60, 30, 40), width=10)
        d.ellipse((cx - 28, EY + 34, cx + 28, EY + 58), fill=(255, 130, 150))
    d.arc((MX - 22, MY - 14, MX, MY + 8), start=0, end=180, fill=(60, 30, 40), width=6)
    d.arc((MX, MY - 14, MX + 22, MY + 8), start=0, end=180, fill=(60, 30, 40), width=6)
    return img


def s_cat():
    img, d = base((20, 16, 26))
    for cx in (EX1, EX2):
        d.ellipse((cx - 42, EY - 48, cx + 42, EY + 48), fill=(255, 185, 40))
        d.ellipse((cx - 9, EY - 40, cx + 9, EY + 40), fill=(15, 10, 15))
    d.polygon([(MX - 10, MY - 8), (MX + 10, MY - 8), (MX, MY + 6)], fill=(255, 130, 150))
    for side in (-1, 1):
        x0 = MX + side * 30
        for dy in (-10, 0, 10):
            d.line((x0, MY + dy, x0 + side * 55, MY + dy - 4 + dy // 2),
                   fill=(200, 200, 210), width=3)
    return img


def s_neon():
    img, d = base((0, 0, 0))
    for cx in (EX1, EX2):
        d.ellipse((cx - 40, EY - 40, cx + 40, EY + 40), outline=(57, 255, 20), width=7)
        d.ellipse((cx - 8, EY - 8, cx + 8, EY + 8), fill=(57, 255, 20))
    d.line((MX - 35, MY, MX + 35, MY), fill=(57, 255, 20), width=7)
    return img


def s_matrix():
    img, d = base((0, 8, 0))
    for cx in (EX1, EX2):
        d.rectangle((cx - 38, EY - 42, cx + 38, EY + 42), outline=(0, 220, 70), width=5)
        d.rectangle((cx - 14, EY - 16, cx + 14, EY + 16), fill=(0, 220, 70))
    for gx in range(-3, 4):
        d.rectangle((MX + gx * 14 - 4, MY - 4, MX + gx * 14 + 4, MY + 4),
                    fill=(0, 180, 60))
    for y in range(0, H, 6):                    # scanlines
        d.line((0, y, W, y), fill=(0, 20, 0))
    return img


def s_hearts():
    img, d = base((30, 12, 24))
    for cx in (EX1, EX2):
        RED = (255, 70, 110)
        d.ellipse((cx - 34, EY - 34, cx + 3, EY + 3), fill=RED)
        d.ellipse((cx - 3, EY - 34, cx + 34, EY + 3), fill=RED)
        d.polygon([(cx - 31, EY - 8), (cx + 31, EY - 8), (cx, EY + 38)], fill=RED)
    smile(d, (255, 150, 180))
    return img


def s_stars():
    img, d = base((10, 12, 42))
    for cx in (EX1, EX2):
        d.polygon(star_points(cx, EY, 48, 19), fill=(255, 220, 60))
    smile(d, (255, 240, 200))
    return img


def s_sleepy():
    img, d = base((18, 16, 28))
    for cx in (EX1, EX2):
        d.ellipse((cx - 45, EY - 55, cx + 45, EY + 55), fill=(200, 200, 220))
        d.rectangle((cx - 47, EY - 57, cx + 47, EY + 8), fill=(18, 16, 28))
        d.line((cx - 45, EY + 8, cx + 45, EY + 8), fill=(200, 200, 220), width=6)
    try:
        f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 34)
    except OSError:
        f = ImageFont.load_default()
    d.text((W - 70, 22), "Z z", font=f, fill=(200, 200, 220))
    d.line((MX - 25, MY, MX + 25, MY), fill=(200, 200, 220), width=6)
    return img


def s_angry():
    img, d = base((22, 10, 10))
    for cx, sgn in ((EX1, 1), (EX2, -1)):
        d.ellipse((cx - 42, EY - 45, cx + 42, EY + 45), fill=(240, 235, 235))
        d.ellipse((cx - 17, EY - 17, cx + 17, EY + 17), fill=(200, 30, 30))
        d.polygon([(cx - sgn * 55, EY - 70), (cx + sgn * 45, EY - 30),
                   (cx + sgn * 50, EY - 48)], fill=(240, 235, 235))
    d.arc((MX - 40, MY - 5, MX + 40, MY + 45), start=200, end=340,
          fill=(240, 235, 235), width=8)
    return img


def s_ghost():
    img, d = base((238, 240, 245))
    for cx in (EX1, EX2):
        d.ellipse((cx - 26, EY - 42, cx + 26, EY + 42), fill=(25, 25, 35))
        d.ellipse((cx - 16, EY - 30, cx - 2, EY - 12), fill=(238, 240, 245))
    d.ellipse((MX - 16, MY - 20, MX + 16, MY + 20), fill=(25, 25, 35))
    return img


def s_baymax():
    img, d = base((245, 245, 248))
    for cx in (EX1, EX2):
        d.ellipse((cx - 15, EY - 15, cx + 15, EY + 15), fill=(20, 20, 24))
    d.line((EX1 + 15, EY, EX2 - 15, EY), fill=(20, 20, 24), width=5)
    return img


def s_puppy():
    img, d = base((32, 24, 18))
    for cx in (EX1, EX2):
        d.ellipse((cx - 45, EY - 52, cx + 45, EY + 52), fill=(240, 235, 225))
        d.ellipse((cx - 36, EY - 40, cx + 36, EY + 44), fill=(120, 70, 30))
        d.ellipse((cx - 18, EY - 20, cx + 18, EY + 22), fill=(30, 18, 10))
        d.ellipse((cx - 20, EY - 32, cx + 2, EY - 12), fill=(255, 255, 255))
        d.ellipse((cx + 8, EY + 8, cx + 20, EY + 20), fill=(255, 255, 255))
    smile(d, (240, 235, 225))
    d.rounded_rectangle((MX - 14, MY + 2, MX + 14, MY + 30), radius=12,
                        fill=(255, 120, 140))
    return img


def s_odd():
    img, d = base((16, 18, 30))
    for cx, iris in ((EX1, (20, 60, 200)), (EX2, (255, 140, 20))):
        d.ellipse((cx - 45, EY - 55, cx + 45, EY + 55), fill=(230, 230, 255))
        d.ellipse((cx - 18, EY - 22, cx + 18, EY + 22), fill=iris)
        d.ellipse((cx - 6, EY - 16, cx + 4, EY - 6), fill=(255, 255, 255))
    smile(d, dx=22)                              # smirk
    return img


def s_squircle():
    img, d = base((14, 22, 34))
    for cx in (EX1, EX2):
        d.rounded_rectangle((cx - 40, EY - 45, cx + 40, EY + 45), radius=20,
                            fill=(235, 240, 245))
        d.rounded_rectangle((cx - 16, EY - 18, cx + 16, EY + 18), radius=10,
                            fill=(10, 40, 90))
        d.line((cx - 38, EY - 62, cx + 38, EY - 62), fill=(235, 240, 245), width=9)
    smile(d, (235, 240, 245))
    return img


def s_fire():
    img, d = base((18, 8, 4))
    for cx in (EX1, EX2):
        d.polygon([(cx, EY - 58), (cx + 32, EY - 6), (cx + 22, EY + 34),
                   (cx - 22, EY + 34), (cx - 32, EY - 6)], fill=(255, 150, 30))
        d.polygon([(cx, EY - 30), (cx + 16, EY + 2), (cx + 10, EY + 24),
                   (cx - 10, EY + 24), (cx - 16, EY + 2)], fill=(255, 230, 90))
    smile(d, (255, 150, 30), width=10)
    return img


def s_galaxy():
    img, d = base((28, 14, 58))
    specks = [(-25, -30), (10, -38), (28, -12), (-32, 8), (-8, 15),
              (20, 25), (-18, 32), (5, -8), (32, 30), (-30, -8)]
    for cx in (EX1, EX2):
        d.ellipse((cx - 44, EY - 50, cx + 44, EY + 50), fill=(12, 8, 30),
                  outline=(180, 160, 255), width=4)
        for sx, sy in specks:
            d.ellipse((cx + sx - 2, EY + sy - 2, cx + sx + 2, EY + sy + 2),
                      fill=(255, 255, 255))
    d.arc((MX - 35, MY - 22, MX + 35, MY + 22), start=20, end=160,
          fill=(255, 230, 150), width=8)
    return img


STYLES = [
    ("classic", s_classic), ("cyclops", s_cyclops), ("pixel", s_pixel),
    ("eve", s_eve), ("visor", s_visor), ("kawaii", s_kawaii),
    ("cat", s_cat), ("neon", s_neon), ("matrix", s_matrix),
    ("hearts", s_hearts), ("stars", s_stars), ("sleepy", s_sleepy),
    ("angry", s_angry), ("ghost", s_ghost), ("baymax", s_baymax),
    ("puppy", s_puppy), ("odd eyes", s_odd), ("squircle", s_squircle),
    ("fire", s_fire), ("galaxy", s_galaxy),
]


def _label(img, i, name):
    d = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    except OSError:
        f = ImageFont.load_default()
    text = f"{i}/{len(STYLES)} {name}"
    d.rectangle((4, 4, 14 + d.textlength(text, font=f), 28), fill=(0, 0, 0))
    d.text((9, 7), text, font=f, fill=(200, 200, 200))


print(f"{len(STYLES)} styles, {DWELL}s each. Ctrl-C to stop. Note your favourites!")
try:
    while True:
        for i, (name, fn) in enumerate(STYLES, 1):
            img = fn()
            _label(img, i, name)
            disp.display(img)
            print(f"  [{i:2d}/{len(STYLES)}] {name}")
            sleep(DWELL)
except KeyboardInterrupt:
    print("\nShow over.")
    disp.display(s_classic())
