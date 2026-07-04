"""
Robot assistant brain — voice in, voice out, and full motion control.

Pipeline:  mic -> transcribe (Vosk) -> brain (Claude / offline) -> {speak, drive, music} -> repeat

TWO brains, automatic fallback:
  1. Claude API (smart)  — natural language, when a key is set and the API works.
  2. Offline rules (free) — keyword parser; no key, no internet, no extra installs.

Voice commands supported:
  move forward / go back / turn left / spin      -> drives the motors
  play a song / play despacito                   -> plays from ~/music
  download despacito                             -> downloads via yt-dlp
  stop the music                                 -> stops playback
  say hello                                      -> speaks the text
  stop                                           -> stops motors instantly

Modes:
  python3 robot_code/assistant.py           -> VOICE mode  (mic -> Vosk -> brain)
  python3 robot_code/assistant.py --type    -> TEXT  mode  (keyboard -> brain)

Setup (on the Pi):
  # Install system deps
  sudo apt install -y espeak-ng alsa-utils mpg123 python3-sounddevice

  # Install yt-dlp for song downloads
  pip install yt-dlp

  # Vosk for offline speech recognition
  pip install vosk
  # Download a small English model (~40 MB):
  wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
  unzip vosk-model-small-en-us-0.15.zip -d ~/
  mv ~/vosk-model-small-en-us-0.15 ~/vosk-model

  # Optional: Claude brain
  python3 -m venv --system-site-packages ~/venv
  source ~/venv/bin/activate
  pip install anthropic vosk yt-dlp sounddevice
  export ANTHROPIC_API_KEY=sk-ant-...
"""

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from time import sleep
from glob import glob

from gpiozero import Motor

try:
    import anthropic
except ImportError:
    anthropic = None

try:
    import sounddevice as sd
    from vosk import Model, KaldiRecognizer
    _VOSK_AVAILABLE = True
except ImportError:
    _VOSK_AVAILABLE = False

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MODEL          = "claude-haiku-4-5"
AUDIO_DEVICE   = "plughw:1,0"          # USB speakerphone (card 1)
MIC_DEVICE     = None                  # None = system default mic
SAMPLE_RATE    = 16000
VOSK_MODEL_DIR = os.path.expanduser("~/vosk-model")
MUSIC_DIR      = os.path.expanduser("~/music")
PIPER_MODEL    = os.environ.get("PIPER_MODEL", os.path.expanduser("~/piper/voice.onnx"))

client = None
if anthropic is not None and os.environ.get("ANTHROPIC_API_KEY"):
    try:
        client = anthropic.Anthropic()
    except Exception:
        client = None

# ---------------------------------------------------------------------------
# Hardware — motors
# ---------------------------------------------------------------------------
motor_a = motor_b = None
_music_proc = None          # currently playing mpg123 process


def _ensure_motors():
    global motor_a, motor_b
    if motor_a is None:
        motor_a = Motor(forward=16, backward=20, pwm=False)
        motor_b = Motor(forward=27, backward=22, pwm=False)
    return motor_a, motor_b


def robot_drive(direction: str, seconds: float = 1.0) -> str:
    if direction == "stop":
        if motor_a is not None:
            motor_a.stop()
            motor_b.stop()
        return "Stopped."
    if direction not in ("forward", "backward", "left", "right", "spin"):
        return f"Unknown direction: {direction}"
    a, b = _ensure_motors()
    moves = {
        "forward":  (a.forward,  b.forward),
        "backward": (a.backward, b.backward),
        "left":     (a.backward, b.forward),
        "right":    (a.forward,  b.backward),
        "spin":     (a.forward,  b.backward),   # full spin (right motors fwd, left bwd)
    }
    left_fn, right_fn = moves[direction]
    left_fn()
    right_fn()
    secs = min(seconds, 5)
    sleep(secs)
    a.stop()
    b.stop()
    return f"Drove {direction} for {secs} seconds."


def robot_move_arm(joint: str, angle: float) -> str:
    """Placeholder — PCA9685 + servos not connected yet."""
    return f"Arm not connected yet — would move {joint} to {angle} degrees."


# ---------------------------------------------------------------------------
# Music
# ---------------------------------------------------------------------------
def _stop_music() -> str:
    global _music_proc
    if _music_proc and _music_proc.poll() is None:
        _music_proc.terminate()
        _music_proc = None
        return "Music stopped."
    return "Nothing is playing."


def download_song(query: str) -> str:
    """Download a song as mp3 using yt-dlp."""
    if not shutil.which("yt-dlp"):
        return "yt-dlp is not installed. Run: pip install yt-dlp"
    os.makedirs(MUSIC_DIR, exist_ok=True)
    try:
        subprocess.run(
            [
                "yt-dlp", "-x", "--audio-format", "mp3", "--audio-quality", "5",
                "--output", os.path.join(MUSIC_DIR, "%(title)s.%(ext)s"),
                f"ytsearch1:{query}",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return f"Downloaded: {query}"
    except subprocess.CalledProcessError as e:
        return f"Download failed: {e}"


def play_song(query: str = "") -> str:
    """Play a local mp3. If query given, find the closest match in ~/music."""
    global _music_proc
    _stop_music()
    songs = sorted(glob(os.path.join(MUSIC_DIR, "*.mp3")))
    if not songs:
        return "No songs in ~/music yet. Ask me to download one first."
    if query:
        match = next((s for s in songs if query.lower() in os.path.basename(s).lower()), songs[0])
    else:
        match = songs[0]
    _music_proc = subprocess.Popen(
        ["mpg123", "-q", "-a", AUDIO_DEVICE, match],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return f"Playing {os.path.basename(match)}."


# ---------------------------------------------------------------------------
# Claude tools
# ---------------------------------------------------------------------------
TOOLS = [
    {
        "name": "drive",
        "description": "Drive the robot. Use when the user asks it to move.",
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["forward", "backward", "left", "right", "spin", "stop"],
                },
                "seconds": {"type": "number", "description": "How long to drive (max 5)."},
            },
            "required": ["direction"],
        },
    },
    {
        "name": "move_arm",
        "description": "Move one joint of the robot arm to an angle in degrees.",
        "input_schema": {
            "type": "object",
            "properties": {
                "joint": {"type": "string", "description": "base, shoulder, elbow, wrist, or gripper"},
                "angle": {"type": "number", "description": "Target angle 0-180 degrees."},
            },
            "required": ["joint", "angle"],
        },
    },
    {
        "name": "play_song",
        "description": "Play a song from the robot's music library.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Song name to search for in the library."},
            },
            "required": [],
        },
    },
    {
        "name": "download_song",
        "description": "Download a song by name or artist using yt-dlp.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Song name or artist to search for."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "stop_music",
        "description": "Stop whatever song is currently playing.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def run_tool(name: str, tool_input: dict) -> str:
    if name == "drive":
        return robot_drive(tool_input["direction"], tool_input.get("seconds", 1.0))
    if name == "move_arm":
        return robot_move_arm(tool_input["joint"], tool_input["angle"])
    if name == "play_song":
        return play_song(tool_input.get("query", ""))
    if name == "download_song":
        return download_song(tool_input["query"])
    if name == "stop_music":
        return _stop_music()
    return f"Unknown tool: {name}"


SYSTEM = (
    "You are the brain of a small robot car. You can drive, move the arm, "
    "play or download songs, and chat. Keep spoken replies short (1-2 sentences) "
    "since they are read aloud. Only drive or move when the user asks. "
    "If asked to download AND play, download first, then play."
)


# ---------------------------------------------------------------------------
# Brain 1: Claude
# ---------------------------------------------------------------------------
def claude_brain(user_text: str, history: list) -> str:
    history.append({"role": "user", "content": user_text})
    while True:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=512,
            system=SYSTEM,
            tools=TOOLS,
            messages=history,
        )
        history.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason != "tool_use":
            return "".join(b.text for b in resp.content if b.type == "text")
        results = []
        for block in resp.content:
            if block.type == "tool_use":
                output = run_tool(block.name, block.input)
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": output})
        history.append({"role": "user", "content": results})


# ---------------------------------------------------------------------------
# Brain 2: offline keyword rules
# ---------------------------------------------------------------------------
_JOINTS = ("base", "shoulder", "elbow", "wrist", "gripper")


def local_brain(user_text: str) -> str:
    t = user_text.lower()

    # music
    if "stop" in t and "music" in t:
        return _stop_music()
    if "download" in t:
        query = re.sub(r"download\s*", "", t, count=1).strip()
        return download_song(query) if query else "What song should I download?"
    if "play" in t:
        query = re.sub(r"play\s*(a\s*song\s*)?", "", t, count=1).strip()
        return play_song(query)

    # say
    if t.startswith("say "):
        return user_text.strip()[4:].strip()

    # arm
    if "arm" in t or any(j in t for j in _JOINTS):
        joint = next((j for j in _JOINTS if j in t), "base")
        m = re.search(r"(-?\d+(?:\.\d+)?)", t)
        return robot_move_arm(joint, float(m.group(1)) if m else 90.0)

    # spin / turn
    if "spin" in t:
        m = re.search(r"(\d+(?:\.\d+)?)", t)
        return robot_drive("spin", float(m.group(1)) if m else 2.0)

    # drive
    for kw, direction in [
        (("forward", "ahead", "straight"), "forward"),
        (("back", "reverse"),              "backward"),
        (("left",),                        "left"),
        (("right",),                       "right"),
    ]:
        if any(k in t for k in kw):
            m = re.search(r"(\d+(?:\.\d+)?)\s*(?:s|sec|second|seconds)?\b", t)
            return robot_drive(direction, float(m.group(1)) if m else 1.0)

    if any(w in t for w in ("hello", "hi", "hey")):
        return "Hi! I am running in offline mode."
    if "help" in t or "what can" in t:
        return "Say: forward, back, left, right, spin, play, download, or stop."

    return "I didn't catch that. Try: forward, spin, play a song, or download a song."


# ---------------------------------------------------------------------------
# Think — pick brain
# ---------------------------------------------------------------------------
def think(user_text: str, history: list) -> str:
    if "stop" in user_text.lower() and "music" not in user_text.lower():
        return robot_drive("stop")
    if client is not None:
        try:
            return claude_brain(user_text, history)
        except Exception as exc:
            print(f"[Claude error: {exc}] -> offline mode")
    return local_brain(user_text)


# ---------------------------------------------------------------------------
# Text-to-speech
# ---------------------------------------------------------------------------
def _say_piper(text: str) -> bool:
    if shutil.which("piper") is None or not os.path.exists(PIPER_MODEL):
        return False
    wav = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav = f.name
        subprocess.run(["piper", "--model", PIPER_MODEL, "--output_file", wav],
                       input=text.encode(), stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True)
        subprocess.run(["aplay", "-q", "-D", AUDIO_DEVICE, wav])
        return True
    except (OSError, subprocess.SubprocessError):
        return False
    finally:
        if wav:
            try: os.remove(wav)
            except OSError: pass


def _say_espeak(text: str) -> None:
    try:
        tts = subprocess.Popen(["espeak-ng", text, "--stdout"], stdout=subprocess.PIPE)
        subprocess.run(["aplay", "-q", "-D", AUDIO_DEVICE], stdin=tts.stdout)
        tts.stdout.close()
        tts.wait()
    except FileNotFoundError:
        pass


def speak(text: str) -> None:
    print(f"[robot] {text}")
    if not text.strip():
        return
    if not _say_piper(text):
        _say_espeak(text)


# ---------------------------------------------------------------------------
# Speech-to-text (Vosk, offline)
# ---------------------------------------------------------------------------
def transcribe() -> str:
    """Listen on the mic until a complete phrase is detected, return the text."""
    if not _VOSK_AVAILABLE:
        raise RuntimeError(
            "Vosk not installed. Run: pip install vosk sounddevice\n"
            "Then download a model: https://alphacephei.com/vosk/models\n"
            "Extract to ~/vosk-model"
        )
    if not os.path.exists(VOSK_MODEL_DIR):
        raise RuntimeError(
            f"Vosk model not found at {VOSK_MODEL_DIR}.\n"
            "Download vosk-model-small-en-us-0.15.zip from https://alphacephei.com/vosk/models\n"
            "and unzip it to ~/vosk-model"
        )
    model = Model(VOSK_MODEL_DIR)
    rec = KaldiRecognizer(model, SAMPLE_RATE)
    q: queue.Queue = queue.Queue()

    def _cb(indata, frames, time_info, status):
        q.put(bytes(indata))

    print("[listening...]")
    with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=8000,
                           device=MIC_DEVICE, dtype="int16",
                           channels=1, callback=_cb):
        while True:
            data = q.get()
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                text = result.get("text", "").strip()
                if text:
                    print(f"[heard] {text}")
                    return text


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main() -> None:
    voice_mode = "--type" not in sys.argv

    history: list = []

    brain_label = f"Claude ({MODEL})" if client is not None else "offline rules"
    input_label = "voice (Vosk)" if voice_mode else "keyboard"
    print(f"Brain: {brain_label}  |  Input: {input_label}")
    print("Commands: move forward / spin / play a song / download despacito / stop")
    if voice_mode:
        print("Speak after '[listening...]' appears. Ctrl-C to quit.\n")
    else:
        print("Type a command. Ctrl-C or 'quit' to exit.\n")

    speak("Hi, I am ready. What should I do?")

    try:
        while True:
            if voice_mode:
                try:
                    user_text = transcribe()
                except RuntimeError as e:
                    print(f"[STT error] {e}")
                    print("Falling back to keyboard input. Use --type flag to skip this message.")
                    voice_mode = False
                    user_text = input("you> ").strip()
            else:
                user_text = input("you> ").strip()

            if not user_text:
                continue
            if user_text.lower() in ("quit", "exit", "q"):
                break

            reply = think(user_text, history)
            speak(reply)

    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        _stop_music()
        if motor_a is not None:
            motor_a.stop()
        if motor_b is not None:
            motor_b.stop()
        print("\nbye")


if __name__ == "__main__":
    main()
