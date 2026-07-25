"""
ST7789 configuration probe -- find which resolution/rotation combo this
panel variant actually displays.

Cycles through every legal (width, height, rotation) combination, filling
the screen RED then BLUE for each. Watch the screen: when color appears,
note the config number printed in the terminal -- that's this panel's
combo, and it goes into face_test.py.

Run:
    python3 robot_code/tests/face_probe.py
"""

from time import sleep

import st7789
from PIL import Image

CONFIGS = [
    (240, 320, 0),
    (240, 320, 90),
    (240, 320, 180),
    (240, 320, 270),
    (320, 240, 0),
    (320, 240, 180),
]

for i, (w, h, rot) in enumerate(CONFIGS, 1):
    print(f"[{i}/{len(CONFIGS)}] width={w} height={h} rotation={rot} -> RED then BLUE")
    disp = st7789.ST7789(
        port=0,
        cs=0,
        dc=24,
        rst=25,
        backlight=None,
        width=w,
        height=h,
        rotation=rot,
        invert=True,
        spi_speed_hz=10_000_000,
    )
    disp.display(Image.new("RGB", (w, h), (255, 0, 0)))
    sleep(2)
    disp.display(Image.new("RGB", (w, h), (0, 0, 255)))
    sleep(1)

print("Done. Which config number showed color? That combo goes in face_test.py.")
