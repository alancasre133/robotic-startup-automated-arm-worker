# Remote Access — View the Camera from Anywhere

By default the camera stream (`robot_code/camera_stream.py`) is only reachable on
your home WiFi (`http://<pi-ip>:8000`). To watch it from anywhere on the
internet, tunnel it out.

> ⚠️ **The stream has no password.** Do **not** just forward a router port to it —
> that puts a live camera of your space on the open internet. Use one of the
> methods below.

## Option A — Tailscale (recommended: private, just your devices)

> ✅ Confirmed working on a Raspberry Pi 3A+ (Raspberry Pi OS Trixie) — camera
> viewable from a phone on cellular data.

Tailscale puts the Pi and your devices on a private, encrypted network reachable
from any connection — no port-forwarding, no public exposure, works behind your
ISP's NAT. Free for personal use.

### 1. Install on the Pi
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up          # opens a login URL — sign in (Google/GitHub/email)
tailscale ip -4            # note the 100.x.x.x address it prints
```

### 2. Install on your phone/laptop
Get the app from <https://tailscale.com/download> and sign in with the **same
account**.

### 3. Watch from anywhere
```bash
# on the Pi (start the stream):
python3 robot_code/camera_stream.py
```
Then on your phone/laptop — on **any** network (cellular, other WiFi) — open:
```
http://100.x.x.x:8000            # the Pi's Tailscale IP from step 1
# or:  http://roboticsstartup:8000   (Tailscale MagicDNS name)
```

Tailscale runs as a background service and **stays on across reboots** — set it
up once. Only devices signed into your account can reach the Pi.

## Option B — ngrok (a public link anyone can open)

For quick sharing / demos — gives a public HTTPS URL.
```bash
# install ngrok (https://ngrok.com/download), then:
ngrok http 8000            # prints a public https URL
```
> ⚠️ Anyone with the link can watch. Add a password (ngrok basic auth) or use a
> Cloudflare Tunnel behind Cloudflare Access if it's more than a quick demo.

## Make the stream auto-start on boot

Both options need `camera_stream.py` running. To have it start automatically (so
you don't SSH in each time), install it as a systemd service.

First **stop any stream you started by hand** (Ctrl-C) so port 8000 is free.
Then create the service — paste the whole block (the heredoc writes the file):

```bash
sudo tee /etc/systemd/system/camera-stream.service > /dev/null <<'EOF'
[Unit]
Description=Robot camera MJPEG stream
After=network.target

[Service]
# adjust the path to wherever your camera_stream.py lives
ExecStart=/usr/bin/python3 /home/alanacr/robotic-startup-automated-arm-worker/robot_code/camera_stream.py
Restart=on-failure
User=alanacr

[Install]
WantedBy=multi-user.target
EOF
```
Enable it (starts now **and** on every boot) and confirm it came up:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now camera-stream
sudo systemctl status camera-stream      # should say: active (running)
```
Use `/usr/bin/python3` (system Python) so `picamera2` is found — not a venv.
Reboot to prove it: the camera should be live at `http://<tailscale-ip>:8000`
without you opening SSH at all.

## Notes
- Streaming uses upload bandwidth and stresses the Pi's WiFi. If it freezes,
  that's the WiFi (see the motor-ground note in the README); lowering the
  resolution in `camera_stream.py` helps.
- The stream port is `8000` (set at the top of `camera_stream.py`).
- **`Illegal instruction`, or the install fails** with a gzip "invalid code
  lengths" / "unexpected end of file" error → the `tailscale` download got
  corrupted (flaky WiFi or SD card). Fix: `sudo apt-get clean && sudo apt-get
  install --reinstall -y tailscale`, then re-run `sudo tailscale up`.
