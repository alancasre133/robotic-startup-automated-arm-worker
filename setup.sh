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
echo "==> Installing camera stack (libcamera + picamera2 + OpenCV)..."
# For the IMX219 camera module. Installing now is harmless even with no camera
# attached; it just makes things ready when the module is plugged in.
# python3-opencv (+ opencv-data for the Haar cascades) powers the vision scripts:
# perception.py colour-blob object finding, vision_track.py / papoi.py face
# detection. numpy comes in as a dependency of python3-opencv.
apt_install python3-picamera2 rpicam-apps python3-opencv opencv-data

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
echo "==> Installing audio tools (espeak-ng, aplay, mpg123, sox)..."
# arecord (from alsa-utils) is what assistant.py uses for mic input -- not
# Python's sounddevice/PortAudio, which couldn't negotiate the USB
# speakerphone's sample rate on the raw ALSA default device.
# sox powers MELVINN's voice EFFECTS (robot/monster/ghost/etc.) -- it
# post-processes the TTS audio; without it, effects silently no-op.
apt_install espeak-ng alsa-utils mpg123 sox

echo
echo "==> Setting USB speakerphone volume..."
# The Techwolf/BY Y02 speakerphone's PCM Playback Volume defaults to 0 (muted)
# on a fresh setup -- this looked exactly like a broken/silent mic during
# debugging, but arecord was capturing fine the whole time; only the SPEAKER
# was silent. Un-mute + boost both playback and mic capture, then save with
# alsactl store so it survives a reboot (ALSA mixer state resets otherwise).
SPK_CARD=$(arecord -l 2>/dev/null | grep -i "usb audio" | head -1 | sed -n 's/^card \([0-9]*\).*/\1/p')
if [ -n "$SPK_CARD" ]; then
    amixer -c "$SPK_CARD" sset 'PCM' 90% unmute >/dev/null 2>&1
    amixer -c "$SPK_CARD" sset 'Mic' 95% unmute >/dev/null 2>&1
    sudo alsactl store
    echo "    Set playback/mic volume on card $SPK_CARD and saved with alsactl store."
else
    echo "    No USB Audio capture card found yet (mic not plugged in?) -- if voice"
    echo "    mode is silent later, run: amixer -c <card> sset 'PCM' 90% unmute"
fi

echo
echo "==> Installing Piper (natural neural voice for MELVINN)..."
# espeak-ng (above) is the always-there fallback, but it sounds robotic.
# Piper is a small neural TTS that sounds human; assistant.py's speak()
# prefers it automatically whenever ~/piper/voice.onnx exists. This section
# installs the piper binary and downloads a set of voices to ~/piper/. Extra
# voices land as ~/piper/<name>.onnx and show up in "list_voices" with no code
# change. Safe to re-run: anything already downloaded is skipped.
PIPER_DIR=~/piper
mkdir -p "$PIPER_DIR"

if ! command -v piper >/dev/null 2>&1; then
    # Pick the prebuilt binary matching this Pi's architecture.
    case "$(uname -m)" in
        aarch64)         PIPER_ASSET=piper_linux_aarch64.tar.gz ;;
        armv7l|armv6l)   PIPER_ASSET=piper_linux_armv7l.tar.gz ;;
        x86_64)          PIPER_ASSET=piper_linux_x86_64.tar.gz ;;
        *)               PIPER_ASSET="" ;;
    esac
    if [ -z "$PIPER_ASSET" ]; then
        echo "    Unknown architecture $(uname -m) -- skipping piper; espeak-ng stays as the voice."
        FAILURES+=("piper (no prebuilt binary for $(uname -m))")
    else
        PIPER_URL="https://github.com/rhasspy/piper/releases/download/2023.11.14-2/$PIPER_ASSET"
        if wget -q --show-progress -O /tmp/piper.tar.gz "$PIPER_URL" \
            && tar xzf /tmp/piper.tar.gz -C "$PIPER_DIR"; then
            sudo ln -sf "$PIPER_DIR/piper/piper" /usr/local/bin/piper
            echo "    Piper installed ($PIPER_ASSET)."
        else
            echo "    !! Piper download/extract failed -- espeak-ng stays as the voice."
            FAILURES+=("piper binary download ($PIPER_URL)")
        fi
        rm -f /tmp/piper.tar.gz
    fi
else
    echo "    piper already installed -- skipping binary."
fi

# Download voices. First column is the local name (~/piper/<name>.onnx), second
# is the path under the piper-voices repo. "voice" is MELVINN's default voice.
if command -v piper >/dev/null 2>&1; then
    echo "==> Downloading MELVINN's voices..."
    PIPER_VOICE_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"
    PIPER_VOICES=(
        # --- default ---
        "voice|en/en_US/amy/low/en_US-amy-low"          # default: warm, fast
        # --- American English ---
        "joe|en/en_US/joe/medium/en_US-joe-medium"      # deep American male
        "danny|en/en_US/danny/low/en_US-danny-low"      # casual young male
        "kathleen|en/en_US/kathleen/low/en_US-kathleen-low"
        "ryan|en/en_US/ryan/low/en_US-ryan-low"
        "lessac|en/en_US/lessac/low/en_US-lessac-low"   # narrator-style female
        "hfc_female|en/en_US/hfc_female/medium/en_US-hfc_female-medium"
        "hfc_male|en/en_US/hfc_male/medium/en_US-hfc_male-medium"
        "kristin|en/en_US/kristin/medium/en_US-kristin-medium"
        "libritts|en/en_US/libritts_r/medium/en_US-libritts_r-medium"  # expressive
        "norman|en/en_US/norman/medium/en_US-norman-medium"
        "ljspeech|en/en_US/ljspeech/medium/en_US-ljspeech-medium"      # classic TTS
        "bryce|en/en_US/bryce/medium/en_US-bryce-medium"
        "john|en/en_US/john/medium/en_US-john-medium"
        # --- British / Scottish English ---
        "alan|en/en_GB/alan/medium/en_GB-alan-medium"   # British male
        "northern|en/en_GB/northern_english_male/medium/en_GB-northern_english_male-medium"
        "jenny|en/en_GB/jenny_dioco/medium/en_GB-jenny_dioco-medium"   # British female
        "alba|en/en_GB/alba/medium/en_GB-alba-medium"   # Scottish female
        "cori|en/en_GB/cori/high/en_GB-cori-high"        # British female, high quality
        "semaine|en/en_GB/semaine/medium/en_GB-semaine-medium"
        "aru|en/en_GB/aru/medium/en_GB-aru-medium"
        # --- other languages (fun accents when reading English; real when spoken in-language) ---
        "spanish|es/es_MX/ald/medium/es_MX-ald-medium"       # Mexican Spanish male
        "castilian|es/es_ES/davefx/medium/es_ES-davefx-medium"  # Spain Spanish
        "french|fr/fr_FR/siwis/medium/fr_FR-siwis-medium"
        "german|de/de_DE/thorsten/medium/de_DE-thorsten-medium"
        "italian|it/it_IT/riccardo/x_low/it_IT-riccardo-x_low"
        "portuguese|pt/pt_BR/faber/medium/pt_BR-faber-medium"
        "dutch|nl/nl_NL/mls/medium/nl_NL-mls-medium"
        "swedish|sv/sv_SE/nst/medium/sv_SE-nst-medium"
    )
    for entry in "${PIPER_VOICES[@]}"; do
        vname=${entry%%|*}
        vpath=${entry#*|}
        target="$PIPER_DIR/$vname.onnx"
        if [ -f "$target" ]; then
            echo "    $vname already present -- skipping."
            continue
        fi
        if wget -q --show-progress -O "$target" "$PIPER_VOICE_BASE/$vpath.onnx" \
            && wget -q -O "$target.json" "$PIPER_VOICE_BASE/$vpath.onnx.json"; then
            echo "    Downloaded $vname."
        else
            echo "    !! Failed to download voice '$vname'."
            rm -f "$target" "$target.json"
            FAILURES+=("piper voice: $vname")
        fi
    done
fi

echo
echo "==> Installing yt-dlp (song downloader)..."
python3 -m pip install --break-system-packages yt-dlp 2>/dev/null || python3 -m pip install yt-dlp

echo
echo "==> Installing ffmpeg (yt-dlp needs it to convert downloads to mp3)..."
# Without this, yt-dlp downloads the audio fine but fails at the very end
# with "Postprocessing: ffprobe and ffmpeg not found" -- confirmed on-device.
apt_install ffmpeg

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
