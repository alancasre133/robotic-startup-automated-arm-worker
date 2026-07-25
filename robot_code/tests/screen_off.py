"""
Blank and sleep the face screen (DISPOFF + SLPIN).

Clears whatever image is latched in the panel RAM and puts the controller
in minimal-power sleep. NOTE: this board's backlight is hardwired to VCC
(no BLK pin), so a faint glow remains -- only unplugging VCC kills that.

Any face script wakes the screen right back up (their init includes SLPOUT).

Run:
    python3 robot_code/tests/screen_off.py
"""

from time import sleep

import spidev
from gpiozero import OutputDevice

dc = OutputDevice(24)
spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 1_000_000

dc.off()                    # command mode
spi.writebytes([0x28])      # DISPOFF -- hide the image
sleep(0.05)
spi.writebytes([0x10])      # SLPIN -- controller to sleep
print("Screen off (backlight glow is hardwired -- unplug VCC to kill it).")
