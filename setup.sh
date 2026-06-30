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
echo "==> Setup complete. Reboot to load the camera:  sudo reboot"
echo
echo "After reboot:"
echo "  - Verify the camera:  rpicam-hello --list-cameras   (should list imx219)"
echo "  - Test the motors:    python3 robot_code/motor_test.py   (wheels off the ground)"
