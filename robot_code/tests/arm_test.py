"""
Robot arm bring-up test — PCA9685 + servos, one joint at a time.

Verifies the PCA9685 wiring and each servo before trusting the arm to
assistant.py. Uses the SAME robot_move_arm() / ARM_JOINTS the assistant uses,
so a pass here means the assistant's arm commands will work too.

SAFETY:
  - Keep the arm free to move — nothing should block a joint's travel.
  - Power the servo battery (6V NiMH -> PCA9685 V+) BEFORE running this. The
    Pi's 3.3V VCC alone runs the PCA9685 chip but not the servos.
  - If a joint strains or grinds, Ctrl-C immediately.

One-time install (on the Pi):
    sudo raspi-config nonint do_i2c 0 && sudo reboot   # enable I2C
    pip install adafruit-circuitpython-pca9685 adafruit-circuitpython-motor adafruit-blinka
    i2cdetect -y 1                                      # confirm address 40 shows up

Run:
    python3 robot_code/tests/arm_test.py
"""

from assistant import ARM_JOINTS, robot_move_arm, _ensure_arm  # reuse the real arm code


def main():
    print("Arm bring-up test — one joint at a time. Ctrl-C any time to stop.\n")
    if _ensure_arm() is None:
        print("Could not reach the PCA9685 over I2C. Check:")
        print("  - I2C enabled?  i2cdetect -y 1  should show address 40")
        print("  - Pi -> PCA9685: 3.3V->VCC, GND->GND, SDA(pin 3)->SDA, SCL(pin 5)->SCL")
        print("  - adafruit-circuitpython-pca9685 / adafruit-blinka installed?")
        return

    print("PCA9685 found. Centering all joints to 90 degrees...")
    for joint in ARM_JOINTS:
        robot_move_arm(joint, 90)
    input("\nAll joints centered — press Enter to test them one at a time.")

    for joint in ARM_JOINTS:
        input(f"\n-- {joint} -- press Enter to sweep 60 -> 120 -> 90")
        robot_move_arm(joint, 60)
        input(f"   {joint} at 60 degrees. Enter to continue -> 120")
        robot_move_arm(joint, 120)
        input(f"   {joint} at 120 degrees. Enter to continue -> back to 90 (center)")
        robot_move_arm(joint, 90)
        print(f"   {joint} back at 90. Did it move smoothly and in the right direction?")

    print("\nAll joints tested. If one moved the wrong way, or not at all, check that")
    print("servo's channel number (0-5, in ARM_JOINTS order) and connector orientation.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nstopped")
