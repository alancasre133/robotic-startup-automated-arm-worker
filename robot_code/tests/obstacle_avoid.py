"""
Obstacle avoidance using the HC-SR04 ultrasonic sensor.

Continuously measures distance in front of the robot. When an obstacle
is closer than STOP_DISTANCE the robot stops and turns to avoid it.

Wiring (Pi physical pin numbers):
    HC-SR04 VCC   -> Pi pin 2   (5V)
    HC-SR04 GND   -> Pi pin 34  (GND)
    HC-SR04 Trig  -> Pi pin 33  (GPIO13, BCM)
    HC-SR04 Echo  -> Pi pin 35  (GPIO19, BCM)  ** via voltage divider **

Voltage divider on Echo (Echo pin outputs 5V, Pi GPIO is 3.3V max):
    Echo -> 1kΩ -> Pi pin 35 (GPIO19)
    Pi pin 35 (GPIO19) -> 2kΩ -> Pi pin 39 (GND)

Install (on the Pi, already done by setup.sh):
    sudo apt install -y python3-gpiozero python3-lgpio

Run:
    python3 robot_code/tests/obstacle_avoid.py

Press Ctrl-C to stop.
"""

from gpiozero import DistanceSensor, Motor
from time import sleep

# --- Config ------------------------------------------------------------------
TRIG_PIN       = 13       # BCM (Pi pin 33)
ECHO_PIN       = 19       # BCM (Pi pin 35, behind voltage divider)
STOP_DISTANCE  = 0.25     # metres — stop if obstacle is closer than this
TURN_TIME      = 0.8      # seconds to turn when blocked
POLL_INTERVAL  = 0.05     # seconds between distance readings

# --- Hardware ----------------------------------------------------------------
sensor  = DistanceSensor(echo=ECHO_PIN, trigger=TRIG_PIN, max_distance=2.0)
motor_a = Motor(forward=16, backward=20, pwm=False)
motor_b = Motor(forward=27, backward=22, pwm=False)


def stop():
    motor_a.stop()
    motor_b.stop()


def drive_forward():
    motor_a.forward()
    motor_b.forward()


def turn_right():
    motor_a.forward()
    motor_b.backward()


# --- Main loop ---------------------------------------------------------------
def main():
    print(f"Obstacle avoidance running. Stop distance: {STOP_DISTANCE * 100:.0f} cm")
    print("Press Ctrl-C to stop.\n")
    moving = False  # start driving only on the stopped->moving transition, not every poll
    try:
        while True:
            dist = sensor.distance          # metres
            print(f"\rDistance: {dist * 100:5.1f} cm   ", end="", flush=True)

            if dist < STOP_DISTANCE:
                print(f"\n[!] Obstacle at {dist * 100:.1f} cm — stopping and turning")
                stop()
                moving = False
                sleep(0.2)
                turn_right()
                sleep(TURN_TIME)
                stop()
            elif not moving:
                drive_forward()  # commit to steady drive
                moving = True
            # else: already driving forward steadily -- nothing to do this poll

            sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        pass
    finally:
        stop()
        print("\nStopped.")


if __name__ == "__main__":
    main()
