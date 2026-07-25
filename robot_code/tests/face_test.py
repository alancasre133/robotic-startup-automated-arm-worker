"""
ST7789 face screen bring-up -- color fills, then MELVINN's first eyes.

Wiring (README "Wiring reference -> Face screen"): SPI0 with CS on CE0
(GPIO8), DC=GPIO24, RST=GPIO25, VCC on the shared 3.3V junction, BLK left
unconnected. Enable SPI once with:  sudo raspi-config nonint do_spi 0

The 2.0" IPS panel is 320x240 (ST7789V). If the image comes out rotated or
mirrored on your unit, adjust ROTATION below (0/90/180/270); if colors look
inverted, toggle INVERT.

Run:
    python3 robot_code/tests/face_test.py
"""

from time import sleep

import st7789
from PIL import Image, ImageDraw

# The st7789 lib only allows ROTATION 0/180 with 320x240, and 90/270 with
# 240x320 -- same physical landscape either way. If the image is upside
# down try the other value in the pair; if it comes out portrait, switch
# to the other WIDTH/HEIGHT + ROTATION combo.
WIDTH = 320
HEIGHT = 240
ROTATION = 0
INVERT = True     # most IPS ST7789 panels want inversion on
# 10 MHz is reliable over Dupont jumpers; raise toward 60 MHz once the
# panel is proven (blank-but-lit screens are usually speed or wiring).
SPI_HZ = 10_000_000

disp = st7789.ST7789(
    port=0,
    cs=0,                 # CE0 = GPIO8 (pin 24)
    dc=24,                # GPIO24 (pin 18)
    rst=25,               # GPIO25 (pin 22)
    backlight=None,       # BLK unconnected -- always on
    width=WIDTH,
    height=HEIGHT,
    rotation=ROTATION,
    invert=INVERT,
    spi_speed_hz=SPI_HZ,
)


def fill(color, seconds=1.5):
    img = Image.new("RGB", (WIDTH, HEIGHT), color)
    disp.display(img)
    sleep(seconds)


def eyes(pupil_dx=0, pupil_dy=0, blink=False, seconds=1.0):
    """Two round eyes on a dark face; pupils offset to 'look' around."""
    img = Image.new("RGB", (WIDTH, HEIGHT), (20, 20, 30))
    d = ImageDraw.Draw(img)
    for cx in (WIDTH // 3, 2 * WIDTH // 3):
        cy = HEIGHT // 2
        if blink:
            d.line((cx - 45, cy, cx + 45, cy), fill=(230, 230, 255), width=10)
        else:
            d.ellipse((cx - 45, cy - 55, cx + 45, cy + 55), fill=(230, 230, 255))
            px, py = cx + pupil_dx, cy + pupil_dy
            d.ellipse((px - 18, py - 22, px + 18, py + 22), fill=(20, 60, 200))
            d.ellipse((px - 6, py - 14, px + 4, py - 4), fill=(255, 255, 255))
    disp.display(img)
    sleep(seconds)


print("Color fills...")
fill((255, 0, 0))
fill((0, 255, 0))
fill((0, 0, 255))
fill((255, 255, 255), 1.0)

print("Eyes...")
eyes()                       # straight ahead
eyes(pupil_dx=-20)           # look left
eyes(pupil_dx=20)            # look right
eyes(pupil_dy=15)            # look down
eyes(blink=True, seconds=0.15)
eyes(seconds=2.0)            # and back

print("Done. If rotated/mirrored tweak ROTATION; if colors are off toggle INVERT.")
