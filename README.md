# MELVINN — Robotic Startup Automated Arm Worker

**MELVINN** — **M**odular **E**xperimental **L**earning **V**ehicle with **I**ntegrated **N**eural **N**etworks.

(The name also nods to *Melvin*, an old Celtic name meaning **"strong friend"** — a good omen for a helper robot with a gripper.)

A Raspberry Pi 3 based robotic arm project.

## What works today

- 🧪 **Drive** — 4WD chassis (4× TT motors via an L9110S, front+rear paralleled per side) — moving under the arm's weight is still being tuned
- ✅ **Camera** — IMX219: stills + a **live browser stream** (no screen on the Pi)
- ✅ **Remote access** — watch the camera **from anywhere over the internet** via Tailscale
- 🧪 **Vision** — on-device **face detection + motor tracking** (experimental)
- ✅ **Voice I/O** — USB speakerphone (mic + speaker) records + plays back
- ✅ **Talk to it** — voice **or** typed commands → the robot acts + speaks, via a **Claude brain or a free offline fallback**
- ✅ **Voice input** — offline speech-to-text (Vosk); talk to it, no typing needed
- ✅ **Arm** — 6-DOF servo arm via a PCA9685 (base / shoulder / elbow / wrist / wrist_rotate / gripper) — all 6 joints tested
- ✅ **Obstacle sensing** — HC-SR04 ultrasonic (distance + stop-before-hitting)
- ✅ **Music** — download + play songs by voice (yt-dlp + mpg123)
- ✅ **Interactive face console** — `papoi.py` greets faces **and** takes live commands
- ✅ **Reproducible** — setup steps, boot config, wiring, and code all live in this repo

## Build it from scratch

Each step links to the details further down (or to a file in the repo):

1. **Get the parts** — [HARDWARE.md](HARDWARE.md) (bill of materials + wiring diagram)
2. **Flash the SD card** — see **Requirements**, then **SD Card Setup**
3. **First boot + connect** — see **First Boot**, then **Connecting via SSH**
4. **Get the code onto the Pi** — see **Get the Code (git)**
5. **Install software** — see **Software Setup**: `bash setup.sh`
6. **Boot config** — match [config/config.txt](config/config.txt); apply steps in **Camera (IMX219)**
7. **Wire + test motors** — see **Motors (L9110S)**, then `python3 robot_code/tests/motor_test.py`
8. **Test the camera** — see **Camera (IMX219)**, then `python3 robot_code/tests/camera_test.py`
9. **Stream the camera live** — `python3 robot_code/tests/camera_stream.py`, then open `http://<pi-ip>:8000`
10. **View from anywhere + auto-start on boot** — Tailscale + a systemd service: [docs/remote-access.md](docs/remote-access.md)
11. **Talk to the robot** — `python3 robot_code/tests/assistant.py` (works offline; add a key for the Claude brain) — see **Talk to the Robot**
12. **Wire + test the arm** — see **HARDWARE.md → Robotic arm**, then `python3 robot_code/tests/arm_test.py` (arm free to move)
13. **Wire + test obstacle sensing** — see **HARDWARE.md → Obstacle sensing**, then `python3 robot_code/tests/obstacle_avoid.py`
14. **Talk with your voice** — `python3 robot_code/tests/assistant.py` (voice mode is the default; `--type` for keyboard)

## Repository map

Everything currently lives under `robot_code/tests/` — old builds getting
reworked for new plans.

| Path | What it is |
|------|-----------|
| `setup.sh` | One-command dependency install + camera enable |
| `HARDWARE.md` | Parts list, prices, wiring quick-reference |
| `config/config.txt` | Known-good `/boot/firmware/config.txt` snapshot |
| `docs/wiring-overview.svg` | System wiring diagram |
| `docs/voice-assistant.md` | Voice assistant design + STT/TTS options |
| `docs/voice-pipeline.svg` | Voice pipeline diagram |
| `docs/pico-setup.md` | Pico W MicroPython flashing |
| `docs/remote-access.md` | View the camera from anywhere (Tailscale) |
| `docs/vision.md` | AI vision — faces / objects / hands + roadmap |
| `robot_code/tests/assistant.py` | Talk to the robot — voice/text, Claude brain + offline fallback, arm, music |
| `robot_code/tests/camera_stream.py` | Live camera stream to a browser |
| `robot_code/tests/vision_track.py` | Face detection + motor tracking + stream |
| `robot_code/tests/papoi.py` | Interactive face console — greets faces + takes live commands |
| `robot_code/tests/obstacle_avoid.py` | Stop/turn before hitting things (HC-SR04) |
| `robot_code/tests/motor_test.py` | Drive both motors (bring-up test) |
| `robot_code/tests/motor_diag.py` | Diagnose raw L9110S motor pin states |
| `robot_code/tests/camera_test.py` | Capture a still photo |
| `robot_code/tests/arm_test.py` | Step-by-step PCA9685 + servo bring-up test |
| `robot_code/tests/arm_jog_test.py` | Jog each servo live with arrow keys (Enter/`b` to switch joints) |
| `robot_code/tests/arm_sequence.py` | Record a sequence of arm poses + wheel moves (TAB to switch), save it, replay it later |
| `robot_code/tests/hello.py` | Trivial "Python works" smoke test |

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

## SD Card Setup

Flash the card with Raspberry Pi Imager (see **Requirements** above for the OS
choice), then just insert it and boot — no manual editing needed on a current
Imager version. Wi-Fi credentials entered in Imager's settings work as-is.

<details>
<summary>If Wi-Fi doesn't connect on first boot (older Imager versions)</summary>

Older releases of Raspberry Pi Imager stored the Wi-Fi password as a
**pre-hashed WPA PSK** (64-character hex string) in `network-config`, which
cloud-init/netplan rejects — Wi-Fi would silently fail with no error. If you
hit this:

1. Open `network-config` on the mounted `bootfs` partition:
   ```
   /Volumes/bootfs/network-config
   ```
2. Find the password field — broken form looks like:
   ```yaml
   wifis:
     wlan0:
       dhcp4: true
       access-points:
         "YOUR_WIFI_SSID":
           password: "5afe08be3851c35e23c2d3c6dea7fcf02e1db90580d3c525085f87a7ec62988a"
       optional: true
   ```
3. Replace it with your **plain-text** Wi-Fi password, save, and safely eject
   the card before inserting it into the Pi.

Ethernet (`eth0`) always works via DHCP regardless — plugging in a cable
sidesteps this entirely.

</details>

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

## Troubleshooting — SSH connects, authenticates, then closes immediately

**Symptom:** `ssh alanacr@<pi-ip>` accepts your password (`Authenticated ... using "password"`) but the session dies right after — `Connection to ... closed by remote host`, no shell, no error text. Non-interactive commands still work fine (`ssh host "echo hi"` succeeds); only a *real* login (or `ssh -t`) fails. Often **intermittent** — sometimes power-cycling the Pi lets you back in, sometimes not.

**Root cause (confirmed via `strace`):** a bug in `libwtmpdb0` (the library that logs login history to `/var/log/wtmp.db`, an SQLite file) segfaults every time a real terminal session is set up — `sudo apt` had 15 pending package updates that were never applied, and one of them carried the fix.

**Fix:**
```bash
ssh alanacr@<pi-ip> "sudo -S bash -c 'apt-get update && apt-get upgrade -y 2>&1 | tail -60'"
# type your sudo password right after running this, then Enter — no visible prompt
```
Then a normal `ssh alanacr@<pi-ip>` should work again.

> **The general escape hatch this relies on:** when interactive login is broken, `ssh host "command"` (no `-t`) still works, because it never opens a real terminal session — it's exactly the path that's crashing that gets skipped. `sudo` normally needs a terminal for its password prompt, so plain `sudo` fails here with *"a terminal is required to read the password"* — the fix is `sudo -S`, which reads the password from stdin instead. Run the command, then **type your sudo password immediately** (it won't be masked/hidden, since there's no terminal to suppress the echo — fine for your own local network, not something to do over an untrusted connection). This isn't specific to the `apt upgrade` fix above — it's the general way to run **any** `sudo` command on the Pi while a normal login session is broken, useful for diagnosing whatever comes up next.

**Why this looked so confusing, and how it was actually diagnosed** (useful if something similar happens again): normal logs (`journalctl -u ssh`, `dmesg`, PAM, AppArmor, `systemd --user`) all looked completely clean — the crash wasn't visible anywhere *until* we ran a one-shot debug `sshd` instance under `strace` on a spare port and watched the syscalls live:
```bash
# 1. start a debug sshd on a spare port, straced, logging to a file
ssh alanacr@<pi-ip> "sudo -S bash -c 'nohup strace -f -tt -o /tmp/strace_sshd.log /usr/sbin/sshd -d -p 2223 -o PidFile=none > /tmp/sshd_debug.log 2>&1 & sleep 1; echo started'"
# 2. trigger the failure against it
ssh -t -p 2223 alanacr@<pi-ip> "echo test"
# 3. read the trace — the failure will be right at the end
ssh alanacr@<pi-ip> "tail -150 /tmp/strace_sshd.log"
```
That showed the exact crash: `pread64` on `/var/log/wtmp.db` immediately followed by `--- SIGSEGV ... +++ killed by SIGSEGV +++`. Deleting/recreating `wtmp.db` did **not** fix it (same crash, same address, on a totally empty file), which ruled out data corruption and pointed at the library build itself — confirming that only an update (not a data fix) would resolve it.

**The bigger pattern — this SD card has a history of corruption.** This is at least the third time a package has come up corrupted on this specific card (also: `numpy`/`picamera2` failing an AppArmor parse early in the project, and `liblcms2-2`'s dpkg metadata going unreadable more recently). That's not coincidence — it points at a **degrading SD card** (worn flash / developing bad sectors), where each unclean power-loss event corrupts whatever happened to be mid-write. If you hit another unexplained crash or `dpkg: ... Bad message` error:
1. Try the targeted fix first (`apt-get install --reinstall -y <package>`, clearing the specific corrupted file, etc. — cheap, sometimes enough).
2. If corruption keeps recurring across *different* unrelated packages, stop patching symptoms — **reflash to a fresh SD card.** The whole setup is scripted (this repo + `setup.sh`), so a full rebuild takes ~20–30 minutes: flash a new card (**SD Card Setup** above), boot it, `git clone` this repo, `bash setup.sh`, then redo the physical steps that aren't in git (Wi-Fi, Tailscale login, re-plugging the camera/motors/arm/sensor — wiring stays the same).
3. **Always let a shutdown fully complete** (green LED off/steady) before cutting power — see **Powering Off the Pi Safely** below. Cutting power while the LED is still active is the most likely cause of this corruption in the first place.

---

## Powering Off the Pi Safely

| Goal | Command | What happens |
|---|---|---|
| **Power off completely** | `sudo poweroff` or `sudo shutdown -h now` | Halts immediately, safely unmounts everything |
| **Reboot** | `sudo reboot` or `sudo shutdown -r now` | Restarts on its own — no need to touch power |
| ⚠️ **Avoid** | bare `sudo shutdown` (no arguments) | Schedules a halt **1 minute later** by default — easy to think nothing happened, and it doesn't reboot |

**The critical step, regardless of command:** after running it, **wait for the green activity LED to stop blinking and go dark/steady** (~15–20 seconds) before pulling the power. That LED blinking means the SD card is still being written to — cutting power while it's active is very likely why this card keeps developing corruption (see **Troubleshooting** above).

Full safe power-off sequence:
```bash
sudo poweroff
```
→ watch the LED → once it's dark/steady → **then** unplug the power bank. To power back on, just reconnect power — the Pi 3A+ has no power button.

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

## Get the Code (git)

Install git and clone this repo onto the Pi:

```bash
sudo apt install -y git
cd ~
git clone https://github.com/alancasre133/robotic-startup-automated-arm-worker.git
cd robotic-startup-automated-arm-worker
```

- **Private repo?** GitHub no longer accepts your account password over git. Create
  a **fine-grained Personal Access Token** (GitHub → Settings → Developer settings →
  Fine-grained tokens) with **Contents: Read-only**, and paste it as the *password*
  when prompted. Run `git config --global credential.helper store` first so the
  token is saved and future `git pull`s don't prompt.
- Pull updates any time with `git pull`.
- No git / prefer drag-and-drop? Copy files over with **FileZilla (SFTP)** — see
  the FileZilla section above.

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
python3 robot_code/tests/motor_test.py
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

Or capture from Python: [robot_code/tests/camera_test.py](robot_code/tests/camera_test.py).

**Live stream to a browser** (no screen on the Pi needed) — run it with system
Python, then open the URL on any device on the same WiFi:

```bash
python3 robot_code/tests/camera_stream.py     # then visit http://<pi-ip>:8000
```

To watch the camera from **anywhere on the internet** (not just your home WiFi),
see [docs/remote-access.md](docs/remote-access.md).

**Gotchas:**
- **"No cameras available"** is almost always the **ribbon orientation** — flip
  the cable at the Pi end. Also confirm it's in the **CAMERA (CSI)** connector,
  not the look-alike **DISPLAY (DSI)** one.
- CMA is set to `cma-64`, fine up to 1920×1080. For full 8 MP (3280×2464),
  raise it to `cma-128` in the `dtoverlay=vc4-kms-v3d,cma-…` line.

---

## AI Vision (experimental)

Detect things in the camera feed and react — starting with **face detection that
turns the robot to follow you**, running entirely on the Pi (no new hardware).

```bash
sudo apt install -y python3-opencv opencv-data
sudo systemctl stop camera-stream          # free the camera + port 8000
python3 robot_code/tests/vision_track.py         # then watch http://<pi-ip>:8000
```

Faces are boxed live in the stream; set `DRIVE_MOTORS = True` in the script
(wheels off the ground!) to let it pivot and track you. The full plan — objects
(TensorFlow Lite), hands (Coral / Pi 4 / offload), and combining fast on-Pi
reflexes with the Claude "brain" — is in [docs/vision.md](docs/vision.md).

---

## Talk to the Robot (assistant)

Talk (or type) a command and the robot **drives, moves its arm, plays music, or
just replies** — out loud. Two brains, automatic fallback:

- **Claude API (smart)** — natural language, when `ANTHROPIC_API_KEY` is set.
- **Offline rules (free)** — a keyword parser; no key, no internet, no extra
  installs. Used automatically if Claude isn't available.

```bash
python3 robot_code/tests/assistant.py           # VOICE mode — mic -> Vosk -> brain
python3 robot_code/tests/assistant.py --type    # TEXT  mode — keyboard -> brain
```

Example commands (spoken or typed):
```
move forward / go back / turn left / spin        -> drives the motors
move the shoulder to 45 / open the gripper        -> moves the arm (PCA9685)
play despacito / play a song                      -> plays from ~/music
download despacito                                -> downloads via yt-dlp
stop the music                                    -> stops playback
say hello                                         -> speaks the text
stop                                              -> stops motors instantly
```

Replies are spoken through the USB speaker (Piper if installed, else espeak-ng).

**Setup** — voice mode needs Vosk + a small offline model + `arecord` (alsa-utils);
the Claude brain needs a key. `bash setup.sh` installs all of it (or run offline/text
mode with nothing extra — it already works with the base install):
```bash
export ANTHROPIC_API_KEY=sk-ant-...       # optional — keep it secret, never commit it
```

**Arm + obstacle sensing** — bring-up/test scripts before trusting them to the
assistant: [robot_code/tests/arm_test.py](robot_code/tests/arm_test.py) (steps through each
servo) and [robot_code/tests/obstacle_avoid.py](robot_code/tests/obstacle_avoid.py) (stops +
turns before hitting something). See **HARDWARE.md** for wiring.

**Interactive face console** — [robot_code/tests/papoi.py](robot_code/tests/papoi.py) does both
at once: it watches the camera and greets faces (default: says "papoi", 5 s
cooldown) **while** taking the same commands — including `when you see my face do
X` to reprogram the greeting live.

Design, STT/TTS options, and the roadmap: [docs/voice-assistant.md](docs/voice-assistant.md).

---

## Raspberry Pi Pico W

The Pico W (flashed with MicroPython) can drive the arm's servos via PWM. Flashing
and verifying it: [docs/pico-setup.md](docs/pico-setup.md).
