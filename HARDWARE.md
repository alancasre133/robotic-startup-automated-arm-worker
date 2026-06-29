# Hardware — Bill of Materials

Everything needed to reproduce the robot car, plus the planned camera and arm
add-ons. Prices are rough estimates (Mexico, 2026, MercadoLibre/Amazon) and will
vary — use them for budgeting, not exact quotes.

## Wiring overview

![Wiring overview](docs/wiring-overview.svg)

If the diagram doesn't render inline, open [docs/wiring-overview.svg](docs/wiring-overview.svg) directly.

---

## Core build (the driving car)

| # | Component | Qty | What it's for | Approx. (MXN) |
|---|-----------|-----|---------------|---------------|
| 1 | Raspberry Pi 3 (Model A+, 3B, or 3B+) | 1 | The brain — runs the control code | 700–1000 |
| 2 | microSD card, 16 GB+ (Class 10/A1) | 1 | Operating system (Raspberry Pi OS Lite, Trixie) | 120–200 |
| 3 | USB power bank, 5V / 2A+ | 1 | Powers the Pi (kept separate from motor power) | 200–450 |
| 4 | 2WD robot car chassis kit | 1 | Frame, 2× TT gear motors, 2 wheels, caster, AA holder | 150–350 |
| 5 | L9110S dual H-bridge motor driver | 1 | Lets the Pi drive both motors forward/back | 30–60 |
| 6 | AA batteries | 4 | Motor power (~6V), via the holder in the kit | 40–80 |
| 7 | Dupont jumper wires (M–F & F–F, 40+) | 1 set | Pi GPIO ↔ L9110S, battery joins | 80–120 |

> The chassis kit (#4) usually bundles the motors, wheels, caster, and AA holder.
> If you buy parts separately you'll also need 2× TT gear motors + wheels.

## Optional — camera (vision)

| # | Component | Qty | What it's for | Approx. (MXN) |
|---|-----------|-----|---------------|---------------|
| 8 | Camera Module v2 / **IMX219** module + ribbon | 1 | Live video / vision on the Pi | 260–555 |

> ⚠️ Avoid generic **OV5647 "v1.3" clones** — ours was detected over I²C but never
> streamed (CSI-2 timeout) and could not be fixed in software. The **IMX219**
> sensor works out of the box on Trixie. Match the ribbon cable to the Pi 3
> (15-pin, standard CSI).

## Planned — robotic arm

| # | Component | Qty | What it's for | Approx. (MXN) |
|---|-----------|-----|---------------|---------------|
| 9 | 6-DOF robotic arm kit (MG996R servos) | 1 | The arm itself | ~775 |
| 10 | Raspberry Pi Pico W | 1 | Generates the servo PWM signals | 120–180 |
| 11 | 5–6V power supply for servos | 1 | Servos draw too much to run off the Pi/Pico | varies |

---

## Tools

- Small flat screwdriver (for the L9110S screw terminals)
- Electrical tape (to join bare battery wires to jumpers)
- A computer with [Raspberry Pi Imager](https://www.raspberrypi.com/software/) (flash the SD card)
- *(Optional)* soldering iron — only needed for add-ons like a WS2812B LED strip

## Wiring quick reference

Pi GPIO → L9110S (BCM numbers):

| L9110S pin | Pi pin | GPIO |
|------------|--------|------|
| A-1A | 36 | GPIO16 |
| A-1B | 38 | GPIO20 |
| B-1A | 13 | GPIO27 |
| B-2A | 15 | GPIO22 |
| GND  | 6  | (ground) |

Power: battery **+** → L9110S **VCC**, battery **−** → Pi **pin 9** (GND).
The Pi is powered separately by the USB power bank.

See [`robot_code/motor_test.py`](robot_code/motor_test.py) for the matching code,
and run [`setup.sh`](setup.sh) once to install dependencies.
