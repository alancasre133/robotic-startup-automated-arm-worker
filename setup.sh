#!/usr/bin/env bash
#
# Setup script for the robot car project on Raspberry Pi OS (Trixie, headless).
# Installs the system packages the robot code needs. Safe to re-run.
#
# Usage (on the Pi, from the project folder):
#     bash setup.sh
#

echo "==> Updating package lists..."
sudo apt update

echo
echo "==> Installing motor control libraries (gpiozero + lgpio)..."
# Used by robot_code/motor_test.py to drive the L9110S from the Pi GPIO.
sudo apt install -y python3-gpiozero python3-lgpio

echo
echo "==> Installing camera stack (libcamera + picamera2)..."
# For the IMX219 camera module. Installing now is harmless even with no camera
# attached; it just makes things ready when the module is plugged in.
sudo apt install -y python3-picamera2 rpicam-apps

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
sudo apt install -y espeak-ng alsa-utils mpg123

echo
echo "==> Installing Python audio input (sounddevice)..."
sudo apt install -y python3-sounddevice

echo
echo "==> Installing yt-dlp (song downloader)..."
pip install --break-system-packages yt-dlp 2>/dev/null || pip install yt-dlp

echo
echo "==> Installing Vosk (offline speech recognition)..."
pip install --break-system-packages vosk 2>/dev/null || pip install vosk

echo
echo "==> Vosk model setup..."
VOSK_MODEL=~/vosk-model
if [ ! -d "$VOSK_MODEL" ]; then
    echo "    Downloading small English model (~40 MB)..."
    wget -q https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip -O /tmp/vosk-model.zip
    unzip -q /tmp/vosk-model.zip -d ~/
    mv ~/vosk-model-small-en-us-0.15 "$VOSK_MODEL"
    rm /tmp/vosk-model.zip
    echo "    Vosk model installed at ~/vosk-model"
else
    echo "    Vosk model already present at ~/vosk-model — skipping."
fi

echo
echo "==> Creating music folder..."
mkdir -p ~/music

echo
echo "==> Enabling I2C (for the arm's PCA9685 servo driver)..."
sudo raspi-config nonint do_i2c 0
sudo apt install -y i2c-tools python3-smbus

echo
echo "==> Installing arm libraries (PCA9685 + servo control)..."
pip install --break-system-packages adafruit-circuitpython-pca9685 adafruit-circuitpython-motor adafruit-blinka 2>/dev/null \
    || pip install adafruit-circuitpython-pca9685 adafruit-circuitpython-motor adafruit-blinka

echo
echo "==> Setup complete. Reboot to load the camera + I2C:  sudo reboot"
echo
echo "After reboot:"
echo "  - Verify the camera:  rpicam-hello --list-cameras   (should list imx219)"
echo "  - Test the motors:    python3 robot_code/motor_test.py   (wheels off the ground)"
echo "  - Verify the arm:     i2cdetect -y 1   (should show address 40)"
echo "  - Test the arm:       python3 robot_code/arm_test.py   (arm free to move)"
echo "  - Run the assistant:  python3 robot_code/assistant.py    (voice mode)"
echo "  - Keyboard mode:      python3 robot_code/assistant.py --type"
