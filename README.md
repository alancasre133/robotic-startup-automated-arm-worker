# Robotic Startup Automated Arm Worker

A Raspberry Pi 3 based robotic arm project.

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
