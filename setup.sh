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
echo "==> Setup complete."
echo
echo "Next steps:"
echo "  - Test the motors (wheels off the ground):  python3 robot_code/motor_test.py"
echo "  - List the camera once attached:            rpicam-hello --list-cameras"
