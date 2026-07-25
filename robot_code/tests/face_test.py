"""
ST7789 face screen test -- color fills, then MELVINN's first eyes.

Runs on the raw in-repo driver (st7789_raw.py): the Pimoroni st7789 lib
never initialized this GMT020-02-7P panel, the bare datasheet sequence
does. Wiring per README "Wiring reference -> Face screen".

If the image is upside down use ROTATION 270; if red/blue are swapped set
BGR = True. If the screen stays blank, drop SPI_HZ (1_000_000 is the
proven-safe floor from st7789_raw_test.py).

Run:
    python3 robot_code/tests/face_test.py
"""

from time import sleep

from PIL import Image, ImageDraw

from st7789_raw import ST7789Raw

ROTATION = 90          # 90/270 = landscape 320x240, 0/180 = portrait
SPI_HZ = 32_000_000    # raw init proven at 1 MHz; data usually fine much faster
BGR = False            # True if red and blue come out swapped

disp = ST7789Raw(rotation=ROTATION, spi_hz=SPI_HZ, bgr=BGR)
WIDTH, HEIGHT = disp.width, disp.height


def fill(color, seconds=1.5):
    disp.display(Image.new("RGB", (WIDTH, HEIGHT), color))
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

print("Done. Upside down -> ROTATION=270. Colors swapped -> BGR=True.")
