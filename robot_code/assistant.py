"""
Robot assistant brain — decides what to do, and the robot acts + talks back.

Pipeline:  your command -> brain (decides) -> {speak reply, drive, move arm} -> repeat

TWO brains, automatic fallback:
  1. Claude API (smart)  — natural language, when a key is set and the API works.
  2. Offline rules (free) — a standard-library keyword parser; no key, no internet,
     no pip installs. Used automatically if Claude isn't available or a call fails.

So the robot ALWAYS responds to basic commands (forward / back / left / right /
stop / arm) — even with no API key or no WiFi — and gets smarter when Claude is up.
As a safety bonus, "stop" always acts instantly, before the brain is even consulted.

Right now you TYPE commands. Adding your VOICE (mic -> speech-to-text) is the next
step — see docs/voice-assistant.md.

Status:
    - drive   -> wired to the L9110S motors (gpiozero)
    - speak   -> espeak-ng out the USB speakerphone (plughw:1,0)
    - arm     -> placeholder until the PCA9685 + MG996R servos are connected
    - transcribe() -> stub; wire up Vosk next for voice input

Setup (on the Pi):
    # OFFLINE mode needs nothing extra — just run it (gpiozero is already installed).
    # For the CLAUDE brain, add the SDK in a venv that can still see gpiozero:
    python3 -m venv --system-site-packages ~/venv
    source ~/venv/bin/activate
    pip install anthropic
    export ANTHROPIC_API_KEY=sk-ant-...          # your key; keep it secret

Run (wheels OFF the ground the first time — it can drive!):
    python3 robot_code/assistant.py
"""

import os
import re
import subprocess
from time import sleep

from gpiozero import Motor

# The Claude SDK is optional — the robot still works offline without it.
try:
    import anthropic
except ImportError:
    anthropic = None

# --- Model -----------------------------------------------------------------
# Haiku 4.5 — fastest + cheapest, best for a snappy voice loop. Switch to
# "claude-opus-4-8" for maximum smarts (slower / pricier) or "claude-sonnet-4-6".
MODEL = "claude-haiku-4-5"

AUDIO_DEVICE = "plughw:1,0"  # the USB speakerphone (card 1)

# Build a Claude client only if the SDK is present AND a key is set. Any problem
# here just means we run in offline mode.
client = None
if anthropic is not None and os.environ.get("ANTHROPIC_API_KEY"):
    try:
        client = anthropic.Anthropic()
    except Exception:
        client = None

# --- Hardware --------------------------------------------------------------
# Motors (L9110S) — same wiring as motor_test.py
motor_a = Motor(forward=16, backward=20)
motor_b = Motor(forward=27, backward=22)


def robot_drive(direction: str, seconds: float = 1.0) -> str:
    """Drive the car for a short time, then stop."""
    moves = {
        "forward":  (motor_a.forward,  motor_b.forward),
        "backward": (motor_a.backward, motor_b.backward),
        "left":     (motor_a.backward, motor_b.forward),
        "right":    (motor_a.forward,  motor_b.backward),
    }
    if direction == "stop":
        motor_a.stop()
        motor_b.stop()
        return "stopped"
    if direction not in moves:
        return f"unknown direction: {direction}"
    left, right = moves[direction]
    left()
    right()
    sleep(min(seconds, 5))  # cap so a bad value can't run forever
    motor_a.stop()
    motor_b.stop()
    return f"drove {direction} for {seconds}s"


def robot_move_arm(joint: str, angle: float) -> str:
    """Move one arm joint. TODO: implement via the PCA9685 once the arm is wired."""
    # Will set servo channel `joint` to `angle` degrees through the PCA9685 driver.
    return f"(arm not connected yet) would move {joint} to {angle} deg"


# --- Tools exposed to Claude ----------------------------------------------
TOOLS = [
    {
        "name": "drive",
        "description": "Drive the robot car. Use only when the user asks the robot to move.",
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["forward", "backward", "left", "right", "stop"],
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
                "joint": {
                    "type": "string",
                    "description": "Joint/servo name, e.g. base, shoulder, elbow, gripper.",
                },
                "angle": {"type": "number", "description": "Target angle, 0-180 degrees."},
            },
            "required": ["joint", "angle"],
        },
    },
]


def run_tool(name: str, tool_input: dict) -> str:
    if name == "drive":
        return robot_drive(tool_input["direction"], tool_input.get("seconds", 1.0))
    if name == "move_arm":
        return robot_move_arm(tool_input["joint"], tool_input["angle"])
    return f"unknown tool: {name}"


SYSTEM = (
    "You are the brain of a small robot car with a camera and (soon) a robot arm. "
    "You can drive and move the arm using the provided tools. Keep spoken replies "
    "short and natural — one or two sentences, since they are read aloud. Only drive "
    "or move the arm when the user actually asks you to."
)


# --- Brain 1: Claude API ---------------------------------------------------
def claude_brain(user_text: str, history: list) -> str:
    """Send the user's text to Claude, run any tool calls it makes, return the reply."""
    history.append({"role": "user", "content": user_text})
    while True:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM,
            tools=TOOLS,
            messages=history,
        )
        history.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason != "tool_use":
            # No (more) actions — return the spoken reply.
            return "".join(b.text for b in resp.content if b.type == "text")

        # Claude asked to act: run each tool, feed the results back, loop.
        results = []
        for block in resp.content:
            if block.type == "tool_use":
                output = run_tool(block.name, block.input)
                results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": output}
                )
        history.append({"role": "user", "content": results})


# --- Brain 2: offline rules (standard library only) ------------------------
_JOINTS = ("base", "shoulder", "elbow", "wrist", "gripper")


def local_brain(user_text: str) -> str:
    """Free, offline rule-based brain — keyword parsing, no API or internet needed."""
    t = user_text.lower()

    # arm: "move arm shoulder to 45", "gripper 120"
    if "arm" in t or any(j in t for j in _JOINTS):
        joint = next((j for j in _JOINTS if j in t), "base")
        m = re.search(r"(-?\d+(?:\.\d+)?)", t)
        angle = float(m.group(1)) if m else 90.0
        return robot_move_arm(joint, angle)

    # drive direction
    if "forward" in t or "ahead" in t or "straight" in t:
        direction = "forward"
    elif "back" in t or "reverse" in t:
        direction = "backward"
    elif "left" in t:
        direction = "left"
    elif "right" in t:
        direction = "right"
    else:
        direction = None

    if direction:
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:s|sec|secs|second|seconds)\b", t)
        seconds = float(m.group(1)) if m else 1.0
        return robot_drive(direction, seconds)

    # chit-chat / help
    if any(w in t for w in ("hello", "hi", "hey")):
        return "Hi. I'm running in offline mode."
    if "help" in t or "what can you" in t or "command" in t:
        return "Offline mode. Say: forward, back, left, right, stop, or move the arm."

    return "Offline mode understands forward, back, left, right, stop, and arm moves."


def think(user_text: str, history: list) -> str:
    """Use Claude if available; fall back to the offline brain on any failure."""
    # Safety: "stop" always acts instantly, even if Claude is slow or down.
    if "stop" in user_text.lower():
        return robot_drive("stop")
    if client is not None:
        try:
            return claude_brain(user_text, history)
        except Exception as exc:
            print(f"[Claude unavailable: {exc}] -> offline mode")
            return local_brain(user_text)
    return local_brain(user_text)


# --- Speech in / out -------------------------------------------------------
def transcribe() -> str:
    """(Next step) capture mic audio and return recognized text via Vosk.

    Voice input isn't wired yet — for now you type commands in main(). To add it:
    arecord from plughw:1,0 -> Vosk offline recognizer. See docs/voice-assistant.md.
    """
    raise NotImplementedError("voice input is the next step — see docs/voice-assistant.md")


def speak(text: str) -> None:
    """Say `text` aloud through the USB speaker (espeak-ng -> aplay)."""
    print(f"[robot] {text}")
    if not text.strip():
        return
    try:
        tts = subprocess.Popen(["espeak-ng", text, "--stdout"], stdout=subprocess.PIPE)
        subprocess.run(["aplay", "-q", "-D", AUDIO_DEVICE], stdin=tts.stdout)
        tts.stdout.close()
        tts.wait()
    except FileNotFoundError:
        pass  # install with: sudo apt install -y espeak-ng alsa-utils


def main() -> None:
    history: list = []
    if client is not None:
        print(f"Brain: Claude ({MODEL}), with automatic offline fallback.")
    else:
        why = "no anthropic SDK" if anthropic is None else "no ANTHROPIC_API_KEY"
        print(f"Brain: OFFLINE rules ({why}) — basic commands only.")
    print("Try:  drive forward for 2 seconds     (type 'quit' to exit)\n")
    speak("Hi, I am ready.")
    try:
        while True:
            user_text = input("you> ").strip()
            if not user_text:
                continue
            if user_text.lower() in ("quit", "exit", "q"):
                break
            speak(think(user_text, history))
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        motor_a.stop()
        motor_b.stop()
        print("\nbye")


if __name__ == "__main__":
    main()
