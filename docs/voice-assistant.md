# Voice Assistant — Design

The end goal: talk to the robot, and it listens, thinks, answers out loud, and
acts (drives, moves the arm). This is the software plan for that.

## Pipeline

![Voice pipeline](voice-pipeline.svg)

```
mic → speech-to-text → Claude (brain) → speak reply + act → listen again
```

1. **Listen** — capture audio from the USB speakerphone mic.
2. **Speech-to-text (STT)** — turn the audio into text.
3. **Think** — send the text to the **Claude API**. Claude decides whether to
   just talk or to *act*, and calls robot tools (`drive`, `move_arm`) when it
   should move.
4. **Act + speak** — run any tool calls (motors / arm) and read the reply aloud
   through the USB speakerphone.
5. **Loop** — go back to listening.

The Pi is the hands and ears; **Claude (in the cloud) is the thinking.** The Pi
3A+ can't run a large model locally, so the intelligence lives in the API and
the Pi just captures audio, calls it, and carries out the actions.

## The brain — Claude API with tool use

The code skeleton is [robot_code/assistant.py](../robot_code/assistant.py). It
uses the Anthropic Python SDK and the **tool-use loop**: Claude receives the
request and can call tools that map to robot functions.

Tools exposed to Claude:

| Tool | Maps to | Status |
|------|---------|--------|
| `drive(direction, seconds)` | the L9110S motors | ✅ works once motors are wired |
| `move_arm(joint, angle)` | a PCA9685 servo channel | ⏳ stub until the arm is wired |

The loop: send transcript → if Claude returns `tool_use`, run the tool and feed
the result back → repeat until Claude returns a normal reply → speak it.

### Model choice

The skeleton defaults to **`claude-opus-4-8`** (most capable). For a voice loop,
latency and cost matter, so you may prefer a faster/cheaper model — just change
the `MODEL` constant:

| Model | Use when |
|-------|----------|
| `claude-opus-4-8` | best quality (default) |
| `claude-sonnet-4-6` | balanced speed / cost |
| `claude-haiku-4-5` | fastest + cheapest — good for snappy voice |

### Setup

On the Pi, use a virtualenv (Trixie's system Python is externally managed):

```bash
python3 -m venv ~/venv && source ~/venv/bin/activate
pip install anthropic gpiozero lgpio
export ANTHROPIC_API_KEY=sk-ant-...      # keep this secret; don't commit it
```

## Speech-to-text (STT) options

| Option | Runs | Notes |
|--------|------|-------|
| **Vosk** | offline, on the Pi | Lightweight, works on the Pi 3, no internet needed. Good first choice. |
| Cloud STT API | needs WiFi | Higher accuracy, more setup, per-use cost. |

## Text-to-speech (TTS) options

| Option | Runs | Notes |
|--------|------|-------|
| **Piper** | offline, on the Pi | Natural-sounding neural voice, reasonable on the Pi 3. |
| **espeak-ng** | offline, on the Pi | Robotic but tiny and instant — simplest to start with. |
| Cloud TTS API | needs WiFi | Best quality, per-use cost. |

## Audio hardware — USB speakerphone (working ✅)

We use a **USB conference speakerphone** (BY `Y02`) for both mic and speaker — one
USB plug, no soldering, no GPIO use. It runs through a **USB hub** (the Pi 3A+ has
only one USB port, shared with the Pico). Confirmed working on Raspberry Pi OS
Trixie. (This replaces the earlier INMP441/MAX98357 I²S kit, which needed
soldering and collided with Motor A on GPIO20.)

**Detect it** (after plugging the hub + speakerphone in):
```bash
lsusb                # lists the hub + the "Y02" speakerphone
arecord -l           # capture (mic):     card 1: Y02 ...
aplay -l             # playback (speaker): card 1: Y02 ...
```
Both mic and speaker enumerate as **card 1**, so the ALSA device is `plughw:1,0`
(the `plughw` plugin auto-converts sample rate / format).

**Record + play back test:**
```bash
arecord -D plughw:1,0 -f S16_LE -c 1 -r 16000 -d 5 ~/test.wav   # speak for 5 s
aplay   -D plughw:1,0 ~/test.wav
```

> ⚠️ **Silent at first?** A fresh USB audio device is usually muted / at zero
> volume. Run `alsamixer -c 1`, press `F5` to show all controls, then raise **and
> unmute** (`M`) both the playback and capture levels and press `Esc`. Also check
> the speakerphone's own physical mute / volume buttons.

**Make it talk (TTS):**
```bash
sudo apt install -y espeak-ng
espeak-ng "Hello, I am your robot." --stdout | aplay -D plughw:1,0
```
Piping through `aplay -D plughw:1,0` routes speech to the USB speaker (not the
Pi's headphone jack). Upgrade to **Piper** later for a natural voice.

> **Don't put secrets in the repo.** Keep `ANTHROPIC_API_KEY` in the environment
> (or a `.env` that's git-ignored), never in committed code.

## Build order

1. ✅ Drive (motors) — done
2. ✅ Audio I/O — USB speakerphone mic + speaker record/play back cleanly
3. ⏳ Arm (PCA9685 + servos)
4. STT + TTS working end to end (text in the terminal first, then voice)
5. Wire it together: `assistant.py` listens, thinks with Claude, and acts
6. Add the camera as another tool (let Claude "look" by sending a frame)
