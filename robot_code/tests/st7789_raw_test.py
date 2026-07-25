"""
ST7789 raw driver test -- no display library at all.

Bit-bangs the bare datasheet init sequence over spidev at a paranoid 1 MHz
and fills the panel RED, then GREEN. This is the second opinion to the
st7789 python lib: if even the raw sequence shows nothing, no software
theory survives -- the fault is physical (header solder / wiring).

Same wiring as face_test.py: CS=CE0, DC=GPIO24, RST=GPIO25.

Run:
    python3 robot_code/tests/st7789_raw_test.py
"""

from time import sleep

import spidev
from gpiozero import OutputDevice

dc = OutputDevice(24)
rst = OutputDevice(25)

spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 1_000_000
spi.mode = 0


def cmd(c, *data):
    dc.off()
    spi.writebytes([c])
    if data:
        dc.on()
        spi.writebytes(list(data))


def fill(r, g, b):
    # Full RAM window: 240 columns x 320 rows (ST7789V native).
    cmd(0x2A, 0x00, 0x00, 0x00, 0xEF)          # CASET 0..239
    cmd(0x2B, 0x00, 0x00, 0x01, 0x3F)          # RASET 0..319
    cmd(0x2C)                                  # RAMWR
    hi = ((r & 0xF8) | (g >> 5)) & 0xFF        # RGB565
    lo = (((g << 3) & 0xE0) | (b >> 3)) & 0xFF
    dc.on()
    row = [hi, lo] * 240
    for _ in range(320):
        spi.writebytes(row)


print("Hardware reset...")
rst.on(); sleep(0.05)
rst.off(); sleep(0.05)
rst.on(); sleep(0.15)

print("Init sequence...")
cmd(0x01); sleep(0.15)          # SWRESET
cmd(0x11); sleep(0.12)          # SLPOUT (wake up)
cmd(0x3A, 0x55)                 # COLMOD: 16-bit RGB565
cmd(0x36, 0x00)                 # MADCTL: default portrait
cmd(0x21)                       # INVON (IPS panels)
cmd(0x13)                       # NORON
cmd(0x29); sleep(0.05)          # DISPON

print("Filling RED (should be visible NOW)...")
fill(255, 0, 0)
sleep(3)
print("Filling GREEN...")
fill(0, 255, 0)
sleep(3)
print("Done. If the panel stayed blank through this, the fault is physical.")
