"""
Kinematic simulator for MELVINN — drives the model from /cmd_vel.

Listens on /cmd_vel and integrates the robot's pose forward in time,
broadcasting odom -> base_footprint and spinning the wheel joints. In RViz
that makes MELVINN actually drive across the grid.

WHAT THIS IS NOT: physics. There's no mass, no friction, no traction, no
motor torque — so the real robot's whole struggle (a heavy arm on
current-starved TT motors that need rock-starting to break loose) does not
exist here. Ask this model for 0.2 m/s and it delivers 0.2 m/s, every time.
That gap is the point of a kinematic sim: it exercises the *interface*
(/cmd_vel in, tf + joint states out), which is exactly what Nav2 and the
real robot bridge will speak, without pretending to model the hardware.

For real physics you'd want Gazebo, which needs inertia + collision on every
link and a diff-drive plugin in the URDF.

Run:
    ros2 launch melvinn_sim sim.launch.py
    # then, in another terminal:
    ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.2}}"
"""

import math

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist, TransformStamped
from sensor_msgs.msg import JointState
from tf2_ros import TransformBroadcaster

# Must match the URDF (melvinn_description).
ARM_JOINTS = ["base", "shoulder", "elbow", "wrist", "wrist_rotate", "gripper"]
WHEEL_JOINTS = [
    "wheel_front_left_joint", "wheel_front_right_joint",
    "wheel_rear_left_joint", "wheel_rear_right_joint",
]
WHEEL_RADIUS = 0.0325       # metres — same value as the xacro property
RATE_HZ = 20.0


class FakeDrive(Node):
    def __init__(self):
        super().__init__("fake_drive")

        # Pose in the odom frame
        self.x = 0.0
        self.y = 0.0
        self.theta = 0.0
        self.wheel_angle = 0.0

        # Last commanded velocity
        self.v = 0.0        # m/s forward
        self.w = 0.0        # rad/s yaw

        self.create_subscription(Twist, "cmd_vel", self._on_cmd_vel, 10)
        self.joint_pub = self.create_publisher(JointState, "joint_states", 10)
        self.tf = TransformBroadcaster(self)

        self.dt = 1.0 / RATE_HZ
        self.create_timer(self.dt, self._tick)
        self.get_logger().info(
            "fake_drive up — listening on /cmd_vel, publishing odom->base_footprint"
        )

    def _on_cmd_vel(self, msg: Twist):
        self.v = msg.linear.x
        self.w = msg.angular.z
        self.get_logger().info(
            f"cmd_vel: v={self.v:+.3f} m/s  w={self.w:+.3f} rad/s",
            throttle_duration_sec=1.0,
        )

    def _tick(self):
        # Integrate the unicycle model one step.
        self.x += self.v * math.cos(self.theta) * self.dt
        self.y += self.v * math.sin(self.theta) * self.dt
        self.theta += self.w * self.dt
        self.wheel_angle += (self.v / WHEEL_RADIUS) * self.dt

        now = self.get_clock().now().to_msg()

        t = TransformStamped()
        t.header.stamp = now
        t.header.frame_id = "odom"
        t.child_frame_id = "base_footprint"
        t.transform.translation.x = self.x
        t.transform.translation.y = self.y
        t.transform.rotation.z = math.sin(self.theta / 2.0)
        t.transform.rotation.w = math.cos(self.theta / 2.0)
        self.tf.sendTransform(t)

        # robot_state_publisher needs every non-fixed joint, or the tf tree
        # goes incomplete and RViz drops the arm.
        js = JointState()
        js.header.stamp = now
        js.name = ARM_JOINTS + WHEEL_JOINTS
        js.position = [0.0] * len(ARM_JOINTS) + [self.wheel_angle] * len(WHEEL_JOINTS)
        self.joint_pub.publish(js)


def main():
    rclpy.init()
    node = FakeDrive()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
