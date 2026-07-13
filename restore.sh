#!/usr/bin/env bash
#
# One-command rebuild after a fresh SD-card flash.
#
# From a brand-new flash (repo not cloned yet), bootstrap it in one line:
#   curl -fsSL https://raw.githubusercontent.com/alancasre133/robotic-startup-automated-arm-worker/main/restore.sh | bash
#
# Or, if you've already cloned the repo:
#   bash restore.sh
#
# It installs git if needed, clones (or updates) the repo, runs setup.sh — which
# installs OpenCV, the camera stack, arm libraries, Vosk + its model, audio, and
# I2C — then verifies each major piece so you know exactly what came back.
#
# Safe to re-run.

REPO_URL="https://github.com/alancasre133/robotic-startup-automated-arm-worker"
REPO_DIR="$HOME/robotic-startup-automated-arm-worker"

echo "=================================================="
echo " Robot restore — rebuilding after a fresh flash"
echo "=================================================="

# 1. Make sure git is available.
if ! command -v git >/dev/null 2>&1; then
    echo "==> Installing git..."
    sudo apt update && sudo apt install -y git
fi

# 2. Clone the repo, or update it if it's already here.
if [ -d "$REPO_DIR/.git" ]; then
    echo "==> Repo already present — pulling latest..."
    git -C "$REPO_DIR" pull --ff-only || echo "    (pull skipped — you have local changes; that's fine)"
else
    echo "==> Cloning the repo..."
    git clone "$REPO_URL" "$REPO_DIR" || { echo "!! Clone failed — check the network."; exit 1; }
fi

cd "$REPO_DIR" || { echo "!! Could not enter $REPO_DIR"; exit 1; }

# 3. Run the full dependency setup (handles its own retries + Vosk model download).
echo
echo "==> Running setup.sh (this is the long part)..."
bash setup.sh

# 4. Verify what actually came back.
echo
echo "=================================================="
echo " Verification"
echo "=================================================="
FAILED=0
ok()  { printf '   [ OK ] %s\n' "$1"; }
bad() { printf '   [FAIL] %s\n' "$1"; FAILED=$((FAILED + 1)); }

python3 -c "import cv2" 2>/dev/null \
    && ok "OpenCV (cv2) imports — vision ready" \
    || bad "OpenCV (cv2) does NOT import — vision won't work"

[ -d "$HOME/vosk-model" ] \
    && ok "Vosk model present — offline voice ready" \
    || bad "Vosk model missing — offline speech recognition won't work"

python3 -c "import gpiozero" 2>/dev/null \
    && ok "gpiozero present — motors + ultrasonic ready" \
    || bad "gpiozero missing — motor/sensor control won't work"

python3 -c "from picamera2 import Picamera2" 2>/dev/null \
    && ok "picamera2 present — camera ready" \
    || bad "picamera2 missing — camera won't work"

command -v i2cdetect >/dev/null 2>&1 \
    && ok "i2c-tools present — arm (PCA9685) ready" \
    || bad "i2c-tools missing — arm control won't work"

echo
if [ "$FAILED" -eq 0 ]; then
    echo "==> Everything restored. Reboot to load the camera + I2C overlays:"
    echo "      sudo reboot"
    echo
    echo "    Then test vision:"
    echo "      cd $REPO_DIR/robot_code/tests"
    echo "      sudo systemctl stop camera-stream    # free the camera"
    echo "      python3 vision_find_test.py red"
else
    echo "==> Restore finished with $FAILED issue(s) above. Re-run 'bash restore.sh'"
    echo "    once (network hiccups are the usual cause). If OpenCV still fails after"
    echo "    a clean flash, the filesystem may already be corrupting again — check"
    echo "    that you're doing clean shutdowns (sudo shutdown -h now)."
fi
