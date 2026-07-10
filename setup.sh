#!/usr/bin/env bash
#
# Setup script for the robot car project on Raspberry Pi OS (Trixie, headless).
# Installs the system packages the robot code needs. Safe to re-run.
#
# Usage (on the Pi, from the project folder):
#     bash setup.sh
#

FAILURES=()

# apt install can download 100+ packages for one command (e.g. the camera
# stack pulls in ~294 deps); a single flaky-WiFi drop mid-download aborts the
# WHOLE transaction with nothing installed, but this script has no `set -e`
# so it used to print the error and carry on -- ending in a misleading
# "Setup complete" even when e.g. python3-picamera2 never got installed.
# Retry a few times, and track real failures for an honest summary at the end.
apt_install() {
    local attempt=1
    local max_attempts=3
    while [ "$attempt" -le "$max_attempts" ]; do
        if sudo apt install -y "$@"; then
            return 0
        fi
        echo "    apt install failed (attempt $attempt/$max_attempts): $*"
        if [ "$attempt" -lt "$max_attempts" ]; then
            echo "    retrying in 5s..."
            sleep 5
        fi
        attempt=$((attempt + 1))
    done
    echo "    !! Giving up on: $*"
    FAILURES+=("$*")
    return 1
}

echo "==> Updating package lists..."
sudo apt update

echo
echo "==> Installing pip (needed for yt-dlp / Vosk / arm libraries below)..."
# Trixie doesn't put a `pip` binary on PATH by default — use `python3 -m pip`
# everywhere below instead of bare `pip`, which fails with "command not found".
apt_install python3-pip

echo
echo "==> Installing motor control libraries (gpiozero + lgpio)..."
# Used by robot_code/tests/motor_test.py to drive the L9110S from the Pi GPIO.
apt_install python3-gpiozero python3-lgpio

echo
echo "==> Installing camera stack (libcamera + picamera2)..."
# For the IMX219 camera module. Installing now is harmless even with no camera
# attached; it just makes things ready when the module is plugged in.
apt_install python3-picamera2 rpicam-apps

echo
echo "==> Enabling the IMX219 camera overlay in config.txt..."
# Confirmed-working setup for the Arducam IMX219. Harmless if no camera is
# attached. A reversed CSI ribbon shows up as "No cameras available" — flip it.
CONFIG=/boot/firmware/config.txt
sudo sed -i 's/^camera_auto_detect=1/camera_auto_detect=0/' "$CONFIG"
grep -q '^dtoverlay=imx219' "$CONFIG" || echo 'dtoverlay=imx219' | sudo tee -a "$CONFIG" >/dev/null
echo "    Done (a reboot is required for the camera to appear)."

echo
echo
echo "==> Installing audio tools (espeak-ng, aplay, mpg123)..."
apt_install espeak-ng alsa-utils mpg123

echo
echo "==> Installing Python audio input (sounddevice)..."
# No python3-sounddevice package on Trixie's repos — install via pip instead.
python3 -m pip install --break-system-packages sounddevice 2>/dev/null || python3 -m pip install sounddevice

echo
echo "==> Installing yt-dlp (song downloader)..."
python3 -m pip install --break-system-packages yt-dlp 2>/dev/null || python3 -m pip install yt-dlp

echo
echo "==> Installing Vosk (offline speech recognition)..."
python3 -m pip install --break-system-packages vosk 2>/dev/null || python3 -m pip install vosk

echo
echo "==> Patching vosk's native library (executable-stack workaround)..."
# vosk's bundled libvosk.so can fail to load with:
#   OSError: cannot enable executable stack as shared object requires
# on Debian trixie/armhf -- modern glibc refuses to load a shared object that
# requests an executable stack. Clear that ELF flag so it loads cleanly.
# NOTE: `execstack` itself is NOT in Trixie's repos (apt install execstack ->
# "Unable to locate package", confirmed on-device -- it was dropped from
# Debian). Use `patchelf --clear-execstack` instead, which IS packaged.
apt_install patchelf
VOSK_SO=$(python3 -c "import vosk, os; print(os.path.join(os.path.dirname(vosk.__file__), 'libvosk.so'))" 2>/dev/null)
if [ -n "$VOSK_SO" ] && [ -f "$VOSK_SO" ]; then
    patchelf --clear-execstack "$VOSK_SO"
    if python3 -c "from vosk import Model" 2>/dev/null; then
        echo "    Patched $VOSK_SO"
    else
        echo "    !! Patch did not take on $VOSK_SO -- voice mode may still fail."
        FAILURES+=("patchelf --clear-execstack $VOSK_SO (still fails to load after patch)")
    fi
else
    echo "    Could not locate libvosk.so -- if voice mode later fails with"
    echo "    'cannot enable executable stack', find it and run:"
    echo "    patchelf --clear-execstack /path/to/vosk/libvosk.so"
fi

echo
echo "==> Vosk model setup..."
VOSK_MODEL=~/vosk-model
if [ ! -d "$VOSK_MODEL" ]; then
    echo "    Downloading small English model (~40 MB)..."
    attempt=1
    max_attempts=3
    model_ok=0
    while [ "$attempt" -le "$max_attempts" ]; do
        rm -f /tmp/vosk-model.zip
        rm -rf ~/vosk-model-small-en-us-0.15
        if wget -q https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip -O /tmp/vosk-model.zip \
            && unzip -q /tmp/vosk-model.zip -d ~/ \
            && mv ~/vosk-model-small-en-us-0.15 "$VOSK_MODEL"; then
            model_ok=1
            break
        fi
        echo "    Download/extract failed (attempt $attempt/$max_attempts)"
        if [ "$attempt" -lt "$max_attempts" ]; then
            echo "    retrying in 5s..."
            sleep 5
        fi
        attempt=$((attempt + 1))
    done
    rm -f /tmp/vosk-model.zip
    if [ "$model_ok" -eq 1 ] && [ -d "$VOSK_MODEL" ]; then
        echo "    Vosk model installed at ~/vosk-model"
    else
        echo "    !! Giving up on the Vosk model download."
        FAILURES+=("Vosk model download (wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip)")
    fi
else
    echo "    Vosk model already present at ~/vosk-model — skipping."
fi

echo
echo "==> Creating music folder..."
mkdir -p ~/music

echo
echo "==> Enabling I2C (for the arm's PCA9685 servo driver)..."
sudo raspi-config nonint do_i2c 0
apt_install i2c-tools python3-smbus

echo
echo "==> Installing arm libraries (PCA9685 + servo control)..."
python3 -m pip install --break-system-packages adafruit-circuitpython-pca9685 adafruit-circuitpython-motor adafruit-blinka 2>/dev/null \
    || python3 -m pip install adafruit-circuitpython-pca9685 adafruit-circuitpython-motor adafruit-blinka

echo
if [ "${#FAILURES[@]}" -eq 0 ]; then
    echo "==> Setup complete. Reboot to load the camera + I2C:  sudo reboot"
else
    echo "==> Setup finished with ${#FAILURES[@]} failure(s) -- these did NOT install:"
    for f in "${FAILURES[@]}"; do
        echo "      apt install -y $f"
    done
    echo "    Usually a flaky WiFi/mirror drop. Re-run 'bash setup.sh' (it's safe to"
    echo "    repeat) or install the line(s) above by hand, then reboot."
fi
echo
echo "After reboot:"
echo "  - Verify the camera:  rpicam-hello --list-cameras   (should list imx219)"
echo "  - Test the motors:    python3 robot_code/tests/motor_test.py   (wheels off the ground)"
echo "  - Verify the arm:     i2cdetect -y 1   (should show address 40)"
echo "  - Test the arm:       python3 robot_code/tests/arm_test.py   (arm free to move)"
echo "  - Run the assistant:  python3 robot_code/tests/assistant.py    (voice mode)"
echo "  - Keyboard mode:      python3 robot_code/tests/assistant.py --type"
