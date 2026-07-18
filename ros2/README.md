# MELVINN in ROS 2

ROS 2 **Jazzy** packages describing MELVINN.

## Why ROS runs on the PC, not the Pi

ROS 2 publishes no 32-bit-ARM (armhf) binaries, and building it from source
needs several GB of RAM — the Pi 3A+ has **512 MB**. So ROS 2 runs on the
development machine (WSL2 / Ubuntu 24.04) and the Pi keeps its plain-Python
stack. Nothing here needs to be installed on the robot.

## Packages

| Package | What it is |
|---------|-----------|
| `melvinn_description` | URDF model — links, joints, sensors. The foundation RViz, tf2, and MoveIt all read. |
| `melvinn_sim` | Kinematic simulation — drives the model from `/cmd_vel`, no physics. |

## ⚠️ WSL2 needs CycloneDDS

**Use CycloneDDS, not the default Fast DDS.** ROS 2's default middleware
discovers peers over multicast, which WSL2's networking handles unreliably —
publishers and subscribers intermittently never find each other. The symptom
is maddening because it's *intermittent*: a node subscribes fine, `ros2 topic
info` shows the subscription, and messages simply never arrive. Debugging this
cost a while here; a drive command worked once and then the identical turn
command silently did nothing.

```bash
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp   # already in ~/.bashrc
```

Install it with `sudo apt install -y ros-jazzy-rmw-cyclonedds-cpp`. With
Cyclone the same commands work every time.

## Setup (once)

```bash
# in WSL, with ROS 2 Jazzy installed
sudo apt install -y python3-colcon-common-extensions \
                    ros-jazzy-joint-state-publisher-gui ros-jazzy-xacro

mkdir -p ~/ros2_ws/src
# symlink so this git repo stays the single source of truth
ln -sfn /mnt/d/mobile_apps/robotic-startup-automated-arm-worker/ros2/melvinn_description \
        ~/ros2_ws/src/melvinn_description

cd ~/ros2_ws && colcon build --symlink-install
```

## View the model

```bash
source ~/ros2_ws/install/setup.bash
ros2 launch melvinn_description display.launch.py
```

RViz opens with a slider window. Set **Fixed Frame** to `base_footprint`, add a
**RobotModel** display, and set its Description Topic to `/robot_description`.
Dragging a slider moves that joint — the same six joints the real arm has.

## Joint names match the firmware

The six arm joints are named exactly as in `ARM_JOINTS`
(`robot_code/tests/assistant.py`): `base, shoulder, elbow, wrist,
wrist_rotate, gripper`. That's deliberate — a `/joint_states` message from the
robot maps onto this model with no translation layer.

Zero radians means each joint's `ARM_CENTER_ANGLES` value (shoulder 180°,
elbow 45°, the rest 90°), which is why some joint limits are asymmetric. Those
centres were found on the real robot: the arm fouls the chassis elsewhere.

## ⚠️ Dimensions are estimates

Nothing in this repo records measured lengths, so segment sizes come from
typical part dimensions. They're all `xacro:property` values at the top of
`urdf/melvinn.urdf.xacro` — measure the real robot and correct them there.
Until then the model's *proportions* are approximate, though its *structure*
(which joint moves what, about which axis) is correct.

## Drive him in simulation

```bash
ros2 launch melvinn_sim sim.launch.py
```

Set RViz's **Fixed Frame** to `odom` (not `base_footprint`, or the camera
rides along and he looks stationary while the world slides past). Then from
another terminal:

```bash
ros2 topic pub -r 10 /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.2}}"
# or drive with the keyboard:
ros2 run teleop_twist_keyboard teleop_twist_keyboard
```

Verified numerically: 0.2 m/s for ~3 s moved him 0.64 m along x, and 0.5 rad/s
for ~2 s turned him 54°.

**This is kinematics, not physics.** There's no mass, friction, or motor
torque, so the real robot's whole difficulty — a heavy arm on current-starved
TT motors that need rock-starting to break loose — doesn't exist here. Ask the
sim for 0.2 m/s and you get exactly 0.2 m/s. What it *does* exercise is the
interface (`/cmd_vel` in, tf + joint states out), which is precisely what Nav2
and a real-robot bridge speak. Real physics would mean Gazebo, which needs
inertia and collision on every link plus a diff-drive plugin.

## Not done yet

- **Bridging to the real robot** — nothing here talks to the Pi. That needs a
  node speaking `rosbridge` over WebSocket, since the Pi can't run ROS.
- **MoveIt** — the URDF is the prerequisite; the MoveIt config is a separate
  package.
- **SLAM / Nav2** — needs a real ranging sensor. The HC-SR04 is a single-point
  ~30° cone, which is not enough to build a map; that wants a lidar.
