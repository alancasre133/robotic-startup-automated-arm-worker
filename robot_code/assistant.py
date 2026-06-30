"""
Voice assistant brain for the robot.

Pipeline:  mic -> speech-to-text -> Claude (decides) -> {speak reply, drive / move arm} -> repeat

Claude is the "brain": it receives the transcribed request, decides whether to
talk, drive, or move the arm, and calls robot tools to act. This file wires the
Claude API tool-use loop to the robot's hardware functions.

See docs/voice-assistant.md for the full design and component options.

Status:
    - drive tools  -> wired to gpiozero (works once the motors are wired)
    - arm tools    -> placeholder until the PCA9685 + MG996R servos are connected
    - transcribe() / speak() -> stubs; pick a speech engine per docs/voice-assistant.md

Setup (on the Pi; use a virtualenv — Trixie's system Python is externally managed):
    python3 -m venv ~/venv && source ~/venv/bin/activate
    pip install anthropic gpiozero lgpio
    export ANTHROPIC_API_KEY=sk-ant-...

Run:
    python3 assistant.py
"""

from time import sleep

import anthropic
from gpiozero import Motor

# --- Model -----------------------------------------------------------------
# Most capable. For the lowest latency / cost on a voice loop you can switch to
# "claude-haiku-4-5" (fastest, cheapest) or "claude-sonnet-4-6" (balanced).
MODEL = "claude-opus-4-8"

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment

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


def handle(user_text: str, history: list) -> str:
    """Send the user's text to Claude, run any tool calls it makes, return the reply to speak."""
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


# --- Speech in / out (stubs) ----------------------------------------------
def transcribe() -> str:
    """Capture audio from the mic and return the recognized text.

    TODO: implement with the INMP441 I2S mic. Options (see docs/voice-assistant.md):
      - Vosk (offline, lightweight, runs on the Pi 3)
      - a cloud speech-to-text API (higher quality, needs WiFi)
    """
    raise NotImplementedError("wire up speech-to-text — see docs/voice-assistant.md")


def speak(text: str) -> None:
    """Speak `text` aloud through the MAX98357 amp + speaker.

    TODO: implement with piper (offline neural TTS) or espeak-ng (simplest).
    """
    print(f"[assistant] {text}")  # placeholder: print until TTS is wired


def main() -> None:
    history: list = []
    print("Voice assistant ready. Ctrl+C to quit.")
    try:
        while True:
            user_text = transcribe()        # listen
            reply = handle(user_text, history)  # think + act
            speak(reply)                    # respond
    finally:
        motor_a.stop()
        motor_b.stop()


if __name__ == "__main__":
    main()
