"""
MELVINN face style show, round 2 -- the four finalist styles, each with a
full set of emotions.

Finalists (picked from the 20-style runway): PIXEL, EVE, GHOST, SQUIRCLE.
Each family renders 7 emotions -- happy, neutral, sad, angry, surprised,
sleepy, love -- so you can judge how a style carries MELVINN's whole
emotional range, not just one pose. The liked "angry" and "sleepy" designs
from round 1 live on as the angry/sleepy emotions of every family.

Cycles family by family, DWELL seconds per emotion, looping until Ctrl-C.

Run:
    python3 robot_code/tests/face_styles.py
"""

from time import sleep

from PIL import Image, ImageDraw, ImageFont

from st7789_raw import ST7789Raw

disp = ST7789Raw(rotation=90)
W, H = disp.width, disp.height
DWELL = 4                       # seconds per emotion frame

EX1, EX2 = W // 3, 2 * W // 3   # eye centres
EY = H // 2 - 15
MX, MY = W // 2, H - 55         # mouth centre

EMOTIONS = ["happy", "neutral", "sad", "angry", "surprised", "sleepy", "love"]


def base(bg):
    img = Image.new("RGB", (W, H), bg)
    return img, ImageDraw.Draw(img)


def _font(size, bold=True):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(f"/usr/share/fonts/truetype/dejavu/{name}", size)
    except OSError:
        return ImageFont.load_default()


def zzz(d, color):
    d.text((W - 70, 18), "Z z", font=_font(30), fill=color)


def heart(d, cx, cy, r, color):
    d.ellipse((cx - r, cy - r, cx + 2, cy + 2), fill=color)
    d.ellipse((cx - 2, cy - r, cx + r, cy + 2), fill=color)
    d.polygon([(cx - r + 3, cy - r // 4), (cx + r - 3, cy - r // 4),
               (cx, cy + r)], fill=color)


# ===========================================================================
# PIXEL family -- chunky blocks on near-black
# ===========================================================================
PXC = (255, 60, 200)            # magenta
PXR = (255, 70, 60)             # angry red
PX = 14


def _blk(d, cx, cy, gx, gy, color):
    d.rectangle((cx + gx * PX - PX // 2, cy + gy * PX - PX // 2,
                 cx + gx * PX + PX // 2, cy + gy * PX + PX // 2), fill=color)


def _px_eye(d, cx, color, hole=(0, 0), rows=range(-2, 3)):
    for gx in range(-2, 3):
        for gy in rows:
            if abs(gx) == 2 and abs(gy) == 2:
                continue
            _blk(d, cx, EY, gx, gy, color)
    if hole is not None:
        _blk(d, cx, EY, hole[0], hole[1], (5, 5, 12))


def _px_mouth_row(d, color, corners=0):
    for gx in range(-2, 3):
        _blk(d, MX, MY, gx, 0, color)
    if corners:
        _blk(d, MX, MY, -3, -corners, color)
        _blk(d, MX, MY, 3, -corners, color)


def pixel_face(emotion):
    img, d = base((5, 5, 12))
    c = PXR if emotion == "angry" else PXC
    if emotion == "love":
        pat = [" X X ", "XXXXX", "XXXXX", " XXX ", "  X  "]
        for cx in (EX1, EX2):
            for gy, row in enumerate(pat):
                for gx, ch in enumerate(row):
                    if ch == "X":
                        _blk(d, cx, EY, gx - 2, gy - 2, (255, 80, 120))
        _px_mouth_row(d, PXC, corners=1)
    elif emotion == "sleepy":
        for cx in (EX1, EX2):
            _px_eye(d, cx, c, hole=None, rows=range(1, 3))
        _px_mouth_row(d, c)
        zzz(d, c)
    elif emotion == "surprised":
        for cx in (EX1, EX2):
            _px_eye(d, cx, c, hole=None)
            _blk(d, cx, EY, 0, 0, (5, 5, 12))
            _blk(d, cx, EY, -1, 0, (5, 5, 12))
            _blk(d, cx, EY, 0, -1, (5, 5, 12))
            _blk(d, cx, EY, -1, -1, (5, 5, 12))
        for gx, gy in ((-1, -1), (0, -1), (1, -1), (-1, 1), (0, 1), (1, 1),
                       (-1, 0), (1, 0)):
            _blk(d, MX, MY, gx, gy, c)
    else:
        hole = {"happy": (0, 0), "neutral": (0, 0), "sad": (0, 1),
                "angry": (0, 0)}[emotion]
        for cx in (EX1, EX2):
            _px_eye(d, cx, c, hole=hole)
        if emotion == "angry":
            for sgn, cx in ((1, EX1), (-1, EX2)):
                _blk(d, cx, EY, -2 * sgn, -4, c)
                _blk(d, cx, EY, -1 * sgn, -4, c)
                _blk(d, cx, EY, 0, -3, c)
                _blk(d, cx, EY, 1 * sgn, -3, c)
            for gx in range(-3, 4):
                _blk(d, MX, MY, gx, 0 if gx % 2 == 0 else -1, c)
        elif emotion == "happy":
            _px_mouth_row(d, c, corners=1)
        elif emotion == "sad":
            for gx in range(-2, 3):
                _blk(d, MX, MY, gx, 0, c)
            _blk(d, MX, MY, -3, 1, c)
            _blk(d, MX, MY, 3, 1, c)
        else:
            _px_mouth_row(d, c)
    return img


# ===========================================================================
# EVE family -- glowing shapes on near-black, no mouth (it's all in the eyes)
# ===========================================================================
EVC = (60, 200, 255)


def _eve_almond(d, cx, tilt, color):
    d.polygon([(cx - 45, EY + tilt), (cx - 20, EY - 28 + tilt // 2),
               (cx + 20, EY - 28 - tilt // 2), (cx + 45, EY - tilt),
               (cx + 20, EY + 28 - tilt // 2), (cx - 20, EY + 28 + tilt // 2)],
              fill=color)


def eve_face(emotion):
    img, d = base((2, 4, 8))
    if emotion == "happy":
        for cx in (EX1, EX2):
            d.arc((cx - 40, EY - 25, cx + 40, EY + 55),
                  start=200, end=340, fill=EVC, width=16)
    elif emotion == "neutral":
        _eve_almond(d, EX1, 12, EVC)
        _eve_almond(d, EX2, -12, EVC)
    elif emotion == "sad":
        dim = (30, 110, 150)
        _eve_almond(d, EX1, -14, dim)
        _eve_almond(d, EX2, 14, dim)
    elif emotion == "angry":
        _eve_almond(d, EX1, -24, (255, 80, 50))
        _eve_almond(d, EX2, 24, (255, 80, 50))
    elif emotion == "surprised":
        for cx in (EX1, EX2):
            d.ellipse((cx - 42, EY - 42, cx + 42, EY + 42), outline=EVC, width=10)
            d.ellipse((cx - 10, EY - 10, cx + 10, EY + 10), fill=EVC)
    elif emotion == "sleepy":
        dim = (35, 120, 155)
        for cx in (EX1, EX2):
            d.rounded_rectangle((cx - 40, EY - 8, cx + 40, EY + 8),
                                radius=8, fill=dim)
        zzz(d, dim)
    elif emotion == "love":
        for cx in (EX1, EX2):
            heart(d, cx, EY, 40, (120, 220, 255))
    return img


# ===========================================================================
# GHOST family -- ink on white
# ===========================================================================
INK = (25, 25, 35)
PAPER = (238, 240, 245)


def _ghost_eyes(d, tall=42, wide=26):
    for cx in (EX1, EX2):
        d.ellipse((cx - wide, EY - tall, cx + wide, EY + tall), fill=INK)
        d.ellipse((cx - wide + 10, EY - tall + 12,
                   cx - wide + 24, EY - tall + 30), fill=PAPER)


def ghost_face(emotion):
    img, d = base(PAPER)
    if emotion == "happy":
        _ghost_eyes(d)
        d.arc((MX - 35, MY - 25, MX + 35, MY + 20), start=20, end=160,
              fill=INK, width=8)
    elif emotion == "neutral":
        _ghost_eyes(d)
        d.ellipse((MX - 12, MY - 14, MX + 12, MY + 14), fill=INK)
    elif emotion == "sad":
        _ghost_eyes(d)
        d.arc((MX - 30, MY - 4, MX + 30, MY + 34), start=200, end=340,
              fill=INK, width=8)
        d.ellipse((EX1 + 20, EY + 46, EX1 + 34, EY + 70), fill=(110, 160, 255))
    elif emotion == "angry":
        _ghost_eyes(d, tall=30)
        for sgn, cx in ((1, EX1), (-1, EX2)):
            d.polygon([(cx - sgn * 40, EY - 62), (cx + sgn * 30, EY - 34),
                       (cx + sgn * 36, EY - 50)], fill=INK)
        pts = [(MX - 30 + i * 12, MY + (8 if i % 2 else -6)) for i in range(6)]
        d.line(pts, fill=INK, width=7)
    elif emotion == "surprised":
        _ghost_eyes(d, tall=50, wide=24)
        d.ellipse((MX - 20, MY - 24, MX + 20, MY + 24), fill=INK)
        d.ellipse((MX - 10, MY - 12, MX + 10, MY + 12), fill=PAPER)
    elif emotion == "sleepy":
        for cx in (EX1, EX2):
            d.arc((cx - 30, EY - 20, cx + 30, EY + 24), start=20, end=160,
                  fill=INK, width=8)
        zzz(d, INK)
        d.line((MX - 20, MY, MX + 20, MY), fill=INK, width=7)
    elif emotion == "love":
        for cx in (EX1, EX2):
            heart(d, cx, EY, 36, (255, 90, 120))
        d.arc((MX - 30, MY - 22, MX + 30, MY + 18), start=20, end=160,
              fill=INK, width=8)
    return img


# ===========================================================================
# SQUIRCLE family -- rounded rects, navy bg, expressive eyebrows
# ===========================================================================
SQ_BG = (14, 22, 34)
SQ_EYE = (235, 240, 245)
SQ_PUP = (10, 40, 90)


def _sq_eyes(d, pupil=SQ_PUP, tall=45, pupil_dy=0, pupil_small=False,
             hearts=False, lids=False):
    for cx in (EX1, EX2):
        d.rounded_rectangle((cx - 40, EY - tall, cx + 40, EY + 45), radius=20,
                            fill=SQ_EYE)
        if hearts:
            heart(d, cx, EY + 2, 26, (230, 60, 90))
        elif pupil_small:
            d.ellipse((cx - 9, EY - 9 + pupil_dy, cx + 9, EY + 9 + pupil_dy),
                      fill=pupil)
        else:
            d.rounded_rectangle((cx - 16, EY - 18 + pupil_dy,
                                 cx + 16, EY + 18 + pupil_dy), radius=10,
                                fill=pupil)
        if lids:
            d.rectangle((cx - 42, EY - tall - 2, cx + 42, EY + 4), fill=SQ_BG)
            d.line((cx - 40, EY + 4, cx + 40, EY + 4), fill=SQ_EYE, width=7)


def _sq_brows(d, inner_dy=0, y=-62):
    """inner_dy: inner brow end offset. negative = raised (sad), positive = down (angry)."""
    for sgn, cx in ((1, EX1), (-1, EX2)):
        d.line((cx - sgn * 38, EY + y, cx + sgn * 38, EY + y + inner_dy),
               fill=SQ_EYE, width=9)


def squircle_face(emotion):
    img, d = base(SQ_BG)
    if emotion == "happy":
        _sq_eyes(d)
        _sq_brows(d)
        d.arc((MX - 38, MY - 25, MX + 38, MY + 20), start=20, end=160,
              fill=SQ_EYE, width=8)
    elif emotion == "neutral":
        _sq_eyes(d)
        _sq_brows(d)
        d.line((MX - 30, MY, MX + 30, MY), fill=SQ_EYE, width=8)
    elif emotion == "sad":
        _sq_eyes(d, pupil_dy=12)
        _sq_brows(d, inner_dy=-16)
        d.arc((MX - 32, MY - 2, MX + 32, MY + 36), start=200, end=340,
              fill=SQ_EYE, width=8)
    elif emotion == "angry":
        _sq_eyes(d, pupil=(200, 40, 40))
        _sq_brows(d, inner_dy=22, y=-70)
        d.rounded_rectangle((MX - 34, MY - 10, MX + 34, MY + 12), radius=8,
                            fill=SQ_EYE)
        for gx in (-17, 0, 17):
            d.line((MX + gx, MY - 10, MX + gx, MY + 12), fill=SQ_BG, width=4)
    elif emotion == "surprised":
        _sq_eyes(d, tall=55, pupil_small=True)
        _sq_brows(d, y=-78)
        d.ellipse((MX - 16, MY - 18, MX + 16, MY + 18), outline=SQ_EYE, width=8)
    elif emotion == "sleepy":
        _sq_eyes(d, lids=True)
        _sq_brows(d, y=-56)
        zzz(d, SQ_EYE)
        d.line((MX - 20, MY, MX + 20, MY), fill=SQ_EYE, width=7)
    elif emotion == "love":
        _sq_eyes(d, hearts=True)
        _sq_brows(d)
        d.arc((MX - 38, MY - 25, MX + 38, MY + 20), start=20, end=160,
              fill=SQ_EYE, width=8)
    return img


# ===========================================================================
FAMILIES = [
    ("pixel", pixel_face),
    ("eve", eve_face),
    ("ghost", ghost_face),
    ("squircle", squircle_face),
]


def _label(img, fam, emo, i, n):
    d = ImageDraw.Draw(img)
    f = _font(18, bold=False)
    text = f"{fam} - {emo}  ({i}/{n})"
    d.rectangle((4, H - 30, 14 + d.textlength(text, font=f), H - 6), fill=(0, 0, 0))
    d.text((9, H - 27), text, font=f, fill=(200, 200, 200))


total = len(FAMILIES) * len(EMOTIONS)
print(f"{len(FAMILIES)} families x {len(EMOTIONS)} emotions = {total} frames, "
      f"{DWELL}s each. Ctrl-C to stop.")
try:
    while True:
        i = 0
        for fam, fn in FAMILIES:
            for emo in EMOTIONS:
                i += 1
                img = fn(emo)
                _label(img, fam, emo, i, total)
                disp.display(img)
                print(f"  [{i:2d}/{total}] {fam:9s} {emo}")
                sleep(DWELL)
except KeyboardInterrupt:
    print("\nShow over.")
    disp.display(squircle_face("happy"))
