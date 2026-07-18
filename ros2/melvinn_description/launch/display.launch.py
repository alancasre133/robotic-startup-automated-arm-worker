"""
View MELVINN in RViz with sliders for every joint.

    ros2 launch melvinn_description display.launch.py

Starts three nodes:
  robot_state_publisher   reads the URDF, publishes the tf tree
  joint_state_publisher_gui  a slider window -> publishes /joint_states
  rviz2                   draws it

The sliders stand in for the real robot. Later, when the actual MELVINN
publishes /joint_states over the bridge, run this with gui:=false and RViz
shows the real arm's pose instead of the sliders'.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition, UnlessCondition
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    pkg = get_package_share_directory("melvinn_description")
    xacro_file = os.path.join(pkg, "urdf", "melvinn.urdf.xacro")

    gui = LaunchConfiguration("gui")

    # Command(...) runs xacro at launch time and feeds the expanded URDF in.
    # value_type=str is required: without it launch tries to parse the URDF's
    # XML as YAML and the whole launch dies.
    robot_description = {
        "robot_description": ParameterValue(
            Command(["xacro ", xacro_file]), value_type=str
        )
    }

    return LaunchDescription([
        DeclareLaunchArgument(
            "gui", default_value="true",
            description="Show joint sliders. Set false when the real robot "
                        "is publishing /joint_states.",
        ),

        Node(
            package="robot_state_publisher",
            executable="robot_state_publisher",
            output="screen",
            parameters=[robot_description],
        ),

        Node(
            package="joint_state_publisher_gui",
            executable="joint_state_publisher_gui",
            condition=IfCondition(gui),
        ),

        # Without the GUI, something must still publish /joint_states or the
        # tf tree goes stale. This publishes zeros until the real robot talks.
        Node(
            package="joint_state_publisher",
            executable="joint_state_publisher",
            condition=UnlessCondition(gui),
        ),

        Node(
            package="rviz2",
            executable="rviz2",
            output="screen",
            arguments=["-d", os.path.join(pkg, "rviz", "melvinn.rviz")],
        ),
    ])
