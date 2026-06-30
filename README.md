# Robotic Startup Automated Arm Worker

A Raspberry Pi 3 based robotic arm project.

## What works today

- ✅ **Drive** — two DC motors via an L9110S driver, controlled from the Pi
- ✅ **Camera** — IMX219: stills + a **live browser stream over WiFi** (no screen on the Pi)
- ✅ **Reproducible** — setup steps, boot config, wiring, and code all live in this repo
- ⏳ **Arm** — 6 servos via a PCA9685 (waiting on parts)
- ⏳ **Voice assistant** — mic → Claude → speak / act (design + code skeleton done)

## Build it from scratch

Each step links to the details further down (or to a file in the repo):

1. **Get the parts** — [HARDWARE.md](HARDWARE.md) (bill of materials + wiring diagram)
2. **Flash the SD card** — see **Requirements**, then **SD Card Setup & Required Boot Fix**
3. **First boot + connect** — see **First Boot**, then **Connecting via SSH**
4. **Install software** — see **Software Setup**: `bash setup.sh`
5. **Boot config** — match [config/config.txt](config/config.txt); apply steps in **Camera (IMX219)**
6. **Wire + test motors** — see **Motors (L9110S)**, then `python3 robot_code/motor_test.py`
7. **Test the camera** — see **Camera (IMX219)**, then `python3 robot_code/camera_test.py`
8. **Stream the camera live** — `python3 robot_code/camera_stream.py`, then open `http://<pi-ip>:8000`
9. *(planned)* **Arm** — [docs/pico-setup.md](docs/pico-setup.md) + [docs/voice-assistant.md](docs/voice-assistant.md)
10. *(planned)* **Voice** — [docs/voice-assistant.md](docs/voice-assistant.md) + `robot_code/assistant.py`

## Repository map

| Path | What it is |
|------|-----------|
| `setup.sh` | One-command dependency install + camera enable |
| `HARDWARE.md` | Parts list, prices, wiring quick-reference |
| `config/config.txt` | Known-good `/boot/firmware/config.txt` snapshot |
| `docs/wiring-overview.svg` | System wiring diagram |
| `docs/voice-assistant.md` | Voice assistant design + STT/TTS options |
| `docs/voice-pipeline.svg` | Voice pipeline diagram |
| `docs/pico-setup.md` | Pico W MicroPython flashing |
| `robot_code/motor_test.py` | Drive both motors (test) |
| `robot_code/camera_test.py` | Capture a still photo |
| `robot_code/camera_stream.py` | Live camera stream to a browser |
| `robot_code/assistant.py` | Claude "brain" — tool-use loop (drive wired) |

---

## Requirements

### Hardware
- Raspberry Pi 3 Model B / B+
- MicroSD card (16GB or more recommended)

### OS
> **Important:** Use **Raspberry Pi OS Full (32-bit) Lite** when flashing the SD card with Raspberry Pi Imager.
>
> - Version: Raspberry Pi OS Lite (32-bit) — based on Debian Trixie
> - Do **not** use the 64-bit version — the Pi 3 runs best on 32-bit (armhf)
> - Do **not** use the Desktop version — Lite is sufficient for headless robot operation

---

## SD Card Setup & Required Boot Fix

After flashing the SD card with Raspberry Pi Imager, the `bootfs` partition is mounted on your computer. You **must** apply the following fix before inserting the card into the Pi.

### Problem
Raspberry Pi Imager stores the Wi-Fi password as a **pre-hashed WPA PSK** (64-character hex string) in `network-config`. This format is not accepted by cloud-init/netplan, causing Wi-Fi to silently fail on first boot — the Pi will not connect to the network.

### Fix — Edit `network-config` on the bootfs partition

1. Open the `network-config` file on the mounted `bootfs` volume:

```
/Volumes/bootfs/network-config
```

2. Find the Wi-Fi password field — it will look like this (broken):

```yaml
wifis:
  wlan0:
    dhcp4: true
    regulatory-domain: "US"
    access-points:
      "YOUR_WIFI_SSID":
        password: "5afe08be3851c35e23c2d3c6dea7fcf02e1db90580d3c525085f87a7ec62988a"
    optional: true
```

3. Replace the hashed password with your **plain-text Wi-Fi password**:

```yaml
wifis:
  wlan0:
    dhcp4: true
    regulatory-domain: "US"
    access-points:
      "YOUR_WIFI_SSID":
        password: "your_actual_wifi_password"
    optional: true
```

4. Save the file and **safely eject** the SD card before inserting it into the Pi.

> **Note:** Ethernet (`eth0`) is configured with DHCP and works without any fix — if you plug the Pi directly into your router via cable, it will connect automatically without needing this fix.

---

## First Boot

1. Insert the SD card into the Raspberry Pi 3
2. Power it on
3. Wait **90 seconds** — cloud-init runs setup on first boot (installs packages, configures user, sets hostname)
4. The green LED will blink during boot — this is normal

---

## Connecting via SSH

Once booted, connect from your computer:

```bash
ssh alanacr@roboticsstartup.local
```

Or by IP (find it in your router's DHCP list or with a ping sweep):

```bash
ssh alanacr@192.168.x.x
```

If you get a **"WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED"** error (e.g. after re-flashing), clear the old key:

```bash
ssh-keygen -R roboticsstartup.local
ssh-keygen -R 192.168.x.x
```

Then SSH again and accept the new fingerprint.

---

## Pinging the Pi

```bash
ping roboticsstartup.local
# or by IP
ping 192.168.x.x
```

---

## Locale Fix (First Boot Warning)

After first SSH login you may see locale warnings. Fix them by running on the Pi:

```bash
sudo update-locale LANG=en_GB.UTF-8 LC_ALL=en_GB.UTF-8 LC_CTYPE=en_GB.UTF-8
sudo touch /var/lib/cloud/instance/locale-check.skip
sudo reboot
```

---

## Finding the Pi on the Network

If `roboticsstartup.local` doesn't resolve, scan your subnet:

```bash
for i in $(seq 1 254); do (ping -c1 -W1 192.168.16.$i >/dev/null 2>&1 && echo "192.168.16.$i") & done; wait
```

The new IP that appears is your Pi (MAC prefix `b8:27:eb` confirms it's a Raspberry Pi 3).

---

## Transferring Files Remotely with FileZilla (SFTP)

You can upload, download, and manage files on the Pi wirelessly using **FileZilla** over SFTP — no need to remove the SD card.

### 1. Install FileZilla
Download it from [https://filezilla-project.org](https://filezilla-project.org) and install it on your computer.

### 2. Open the Site Manager
- Launch FileZilla
- Go to **File → Site Manager** (or press `Cmd+S` on Mac)
- Click **New Site** and name it `roboticsstartup`

### 3. Enter the Connection Settings

| Field      | Value                          |
|------------|--------------------------------|
| Protocol   | SFTP – SSH File Transfer Protocol |
| Host       | `roboticsstartup.local`        |
| Port       | `22`                           |
| Logon Type | Normal                         |
| User       | `alanacr`                      |
| Password   | your Pi password               |

### 4. Connect
- Click **Connect**
- Accept the host key fingerprint if prompted
- You are now browsing the Pi's filesystem on the right panel

### 5. Transfer Files
- **Left panel** = your computer
- **Right panel** = your Raspberry Pi
- Drag and drop files between panels to upload or download
- Navigate to `/home/alanacr/` to access your robot code folder

### Tips
- Make sure the Pi is **powered on and connected to Wi-Fi** before connecting
- You can also use the IP address (`192.168.16.60`) instead of `roboticsstartup.local` if the hostname doesn't resolve
- To quickly get to your robot code on the Pi, navigate to:
  ```
  /home/alanacr/robotic-startup-automated-arm-worker/robot_code/
  ```

---

## Software Setup (after first boot)

Once you can SSH in, install all dependencies with one command:

```bash
bash setup.sh
```

This installs the motor libraries (`gpiozero`, `lgpio`), the camera stack
(`picamera2`, `rpicam-apps`), and enables the IMX219 camera overlay.

See [HARDWARE.md](HARDWARE.md) for the full parts list and wiring diagram, and
[config/config.txt](config/config.txt) for a known-good snapshot of the Pi's
`/boot/firmware/config.txt`.

---

## Motors (L9110S)

Two DC motors driven from the Pi GPIO through an L9110S dual H-bridge.

| L9110S pin | Pi pin | GPIO |
|------------|--------|------|
| A-1A | 36 | GPIO16 |
| A-1B | 38 | GPIO20 |
| B-1A | 13 | GPIO27 |
| B-2A | 15 | GPIO22 |
| GND  | 6  | (ground reference) |

Power: battery **+** → L9110S **VCC**; battery **−** → L9110S **GND**.
The Pi is powered separately by a USB power bank.

Test (wheels off the ground):

```bash
python3 robot_code/motor_test.py
```

**Gotcha — WiFi drops when motors run:** if the motor return current flows
through the Pi, the surge can knock the WiFi offline (SSH "connection reset").
Keep motor current out of the Pi — join battery **−** directly to the L9110S
**GND**, and run only a thin reference wire from L9110S GND to the Pi's pin 6.
Do **not** put the battery negative on a Pi GPIO pin.

---

## Camera (IMX219)

Confirmed working with an **Arducam IMX219 (8 MP)**. The Pi already has the
driver — no extra Arducam software is needed for the standard module.

Enable it in `/boot/firmware/config.txt`:

```bash
sudo sed -i 's/^camera_auto_detect=1/camera_auto_detect=0/' /boot/firmware/config.txt
grep -q '^dtoverlay=imx219' /boot/firmware/config.txt || echo 'dtoverlay=imx219' | sudo tee -a /boot/firmware/config.txt
sudo reboot
```

Verify and capture:

```bash
rpicam-hello --list-cameras                                   # should list: imx219
rpicam-jpeg -o ~/test.jpg -t 2000 -n --width 1920 --height 1080
```

Copy the photo to your computer to view it (run on your PC, not the Pi):

```bash
scp alanacr@<pi-ip>:~/test.jpg .
```

Or capture from Python: [robot_code/camera_test.py](robot_code/camera_test.py).

**Live stream to a browser** (no screen on the Pi needed) — run it with system
Python, then open the URL on any device on the same WiFi:

```bash
python3 robot_code/camera_stream.py     # then visit http://<pi-ip>:8000
```

**Gotchas:**
- **"No cameras available"** is almost always the **ribbon orientation** — flip
  the cable at the Pi end. Also confirm it's in the **CAMERA (CSI)** connector,
  not the look-alike **DISPLAY (DSI)** one.
- **Avoid OV5647 "v1.3" clones** — ours was detected on I²C but never streamed
  (CSI-2 timeout) and couldn't be fixed in software. The IMX219 just works.
- CMA is set to `cma-64`, fine up to 1920×1080. For full 8 MP (3280×2464),
  raise it to `cma-128` in the `dtoverlay=vc4-kms-v3d,cma-…` line.

---

## Voice Assistant (planned)

The end goal: a voice-controlled assistant that listens, thinks with the
**Claude API**, and acts (drives, moves the arm, answers out loud).

Pipeline: **mic → speech-to-text → Claude (brain) → speak + act → listen again.**

- Design + component options: [docs/voice-assistant.md](docs/voice-assistant.md)
- Code skeleton (Claude tool-use loop wired to the motors): [robot_code/assistant.py](robot_code/assistant.py)

Claude runs in the cloud — the Pi 3A+ can't run a large model locally, so the Pi
captures audio, calls the API, and carries out the actions Claude chooses.

---

## Raspberry Pi Pico W

The Pico W (flashed with MicroPython) can drive the arm's servos via PWM. Flashing
and verifying it: [docs/pico-setup.md](docs/pico-setup.md).
