# Raspberry Pi Pico W — MicroPython Setup

The Pico W can generate the servo PWM for the robot arm (an alternative to a
PCA9685 on the Pi), taking commands from the Raspberry Pi over USB. This is how
to flash MicroPython onto it and verify it.

## 1. Flash MicroPython

1. Download the **Pico W** MicroPython firmware (`.uf2`) — the Pico **W** build
   (it includes WiFi/Bluetooth), not the plain Pico build:
   <https://micropython.org/download/RPI_PICO_W/>
2. **Hold the BOOTSEL button** on the Pico while plugging it into USB (the Pi or
   your PC). Keep holding until it mounts.
3. It appears as a USB drive named **RPI-RP2**.
4. **Copy the `.uf2` file onto RPI-RP2.** The Pico reboots automatically and is
   now running MicroPython (the drive disappears).

## 2. Verify it's detected (on the Raspberry Pi)

With the Pico plugged into the Pi's USB:

```bash
lsusb               # "MicroPython Board in FS mode"  (or "RP2 Boot" if still in bootloader)
ls /dev/ttyACM*     # the Pico's serial port, usually /dev/ttyACM0
```

Seeing `/dev/ttyACM0` means MicroPython is running and reachable.

## 3. Talk to it

Use `mpremote` (the official MicroPython tool). In a virtualenv on Trixie:

```bash
pip install mpremote
mpremote connect /dev/ttyACM0 exec "print('hello from pico')"
```

Open an interactive REPL (Ctrl-X to exit):

```bash
mpremote            # auto-connects to /dev/ttyACM0
```

## 4. Run code on the Pico

`main.py` runs automatically at power-up. Copy a script to that name:

```bash
mpremote connect /dev/ttyACM0 cp servo.py :main.py
mpremote connect /dev/ttyACM0 reset
```

## Notes / gotchas

- **Two USB modes:** holding BOOTSEL = bootloader (RPI-RP2 drive, for flashing);
  a normal plug = MicroPython (serial `/dev/ttyACM0`). If `lsusb` shows
  "RP2 Boot", it's waiting for firmware — copy the `.uf2`.
- **Use the Pico W firmware**, not the plain Pico build — the W has WiFi and a
  different image.
- **The Pi 3A+ has only one USB port.** The Pico uses it; if you also need a USB
  mic or webcam, add a USB hub.
- Servo power: MG996R servos draw too much to run off the Pico — give them their
  own 5–6V supply. See [voice-assistant.md](voice-assistant.md) and
  [../HARDWARE.md](../HARDWARE.md) for the arm plan.
