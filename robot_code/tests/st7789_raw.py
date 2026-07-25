"""
Minimal ST7789V driver for the GMT020-02-7P face screen -- no display lib.

The Pimoroni st7789 python library never initialized this panel (lit
backlight, blank image); the bare datasheet sequence in st7789_raw_test.py
did. So MELVINN's face runs on this ~90-line driver instead.

Wiring (README "Wiring reference -> Face screen"): SPI0 CE0, DC=GPIO24,
RST=GPIO25.

Usage:
    from st7789_raw import ST7789Raw
    disp = ST7789Raw(rotation=90)          # 320x240 landscape
    disp.display(pil_image)                # any PIL RGB image, panel-sized
"""

from time import sleep

import numpy as np
import spidev
from gpiozero import OutputDevice

# MADCTL value and visible window per rotation (ST7789V RAM is 240x320).
_ROTATIONS = {
    0:   (0x00, 240, 320),
    90:  (0x60, 320, 240),
    180: (0xC0, 240, 320),
    270: (0xA0, 320, 240),
}


class ST7789Raw:
    def __init__(self, rotation=90, spi_hz=32_000_000, dc=24, rst=25,
                 port=0, cs=0, bgr=False):
        if rotation not in _ROTATIONS:
            raise ValueError(f"rotation must be one of {sorted(_ROTATIONS)}")
        madctl, self.width, self.height = _ROTATIONS[rotation]
        if bgr:                      # set True if red and blue come out swapped
            madctl |= 0x08
        self._dc = OutputDevice(dc)
        self._rst = OutputDevice(rst)
        self._spi = spidev.SpiDev()
        self._spi.open(port, cs)
        self._spi.max_speed_hz = spi_hz
        self._spi.mode = 0

        # Hardware reset, then the datasheet init that this panel likes.
        self._rst.on(); sleep(0.05)
        self._rst.off(); sleep(0.05)
        self._rst.on(); sleep(0.15)
        self._cmd(0x01); sleep(0.15)             # SWRESET
        self._cmd(0x11); sleep(0.12)             # SLPOUT
        self._cmd(0x3A, 0x55)                    # COLMOD: RGB565
        self._cmd(0x36, madctl)                  # MADCTL: rotation
        self._cmd(0x21)                          # INVON (IPS)
        self._cmd(0x13)                          # NORON
        self._cmd(0x29); sleep(0.05)             # DISPON

    def _cmd(self, c, *data):
        self._dc.off()
        self._spi.writebytes([c])
        if data:
            self._dc.on()
            self._spi.writebytes(list(data))

    def display(self, img):
        """Blit a PIL RGB image (must match self.width x self.height)."""
        if img.size != (self.width, self.height):
            raise ValueError(f"image must be {self.width}x{self.height}, got {img.size}")
        arr = np.asarray(img.convert("RGB"), dtype=np.uint16)
        rgb565 = (
            ((arr[..., 0] & 0xF8) << 8)
            | ((arr[..., 1] & 0xFC) << 3)
            | (arr[..., 2] >> 3)
        )
        w, h = self.width, self.height
        self._cmd(0x2A, 0, 0, (w - 1) >> 8, (w - 1) & 0xFF)   # CASET
        self._cmd(0x2B, 0, 0, (h - 1) >> 8, (h - 1) & 0xFF)   # RASET
        self._cmd(0x2C)                                       # RAMWR
        self._dc.on()
        self._spi.writebytes2(rgb565.byteswap().view(np.uint8).reshape(-1))

    def display_raw565(self, data):
        """Blit a pre-formatted RGB565 big-endian frame (width*height*2 bytes).

        For video: ffmpeg's -pix_fmt rgb565be output is exactly this layout,
        so frames go straight from the decoder pipe to the panel untouched.
        """
        w, h = self.width, self.height
        if len(data) != w * h * 2:
            raise ValueError(f"frame must be {w * h * 2} bytes, got {len(data)}")
        self._cmd(0x2A, 0, 0, (w - 1) >> 8, (w - 1) & 0xFF)   # CASET
        self._cmd(0x2B, 0, 0, (h - 1) >> 8, (h - 1) & 0xFF)   # RASET
        self._cmd(0x2C)                                       # RAMWR
        self._dc.on()
        self._spi.writebytes2(np.frombuffer(data, dtype=np.uint8))
