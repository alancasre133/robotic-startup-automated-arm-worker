"""
Simulate MELVINN driving.

    ros2 launch melvinn_sim sim.launch.py

Then drive him from another terminal:
    ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.2}}"
or with the keyboard:
    ros2 run teleop_twist_keyboard teleop_twist_keyboard

In RViz set Fixed Frame to `odom` (not base_footprint) — otherwise the camera
rides along with the robot and he looks stationary while the world moves.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.substitutions import Command
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    desc_pkg = get_package_share_directory("melvinn_description")
    xacro_file = os.path.join(desc_pkg, "urdf", "melvinn.urdf.xacro")
    rviz_config = os.path.join(desc_pkg, "rviz", "melvinn.rviz")

    return LaunchDescription([
        Node(
            package="robot_state_publisher",
            executable="robot_state_publisher",
            output="screen",
            # value_type=str is required: without it launch tries to parse the
            # URDF's XML as YAML and dies.
            parameters=[{
                "robot_description": ParameterValue(
                    Command(["xacro ", xacro_file]), value_type=str
                )
            }],
        ),

        # Integrates /cmd_vel into a pose, publishes odom->base_footprint
        # and the wheel joint angles.
        Node(
            package="melvinn_sim",
            executable="fake_drive",
            output="screen",
        ),

        # -d preloads a config with the RobotModel + TF displays already set
        # up and Fixed Frame on odom, so it opens showing the robot.
        Node(
            package="rviz2",
            executable="rviz2",
            output="screen",
            arguments=["-d", rviz_config],
        ),
    ])
