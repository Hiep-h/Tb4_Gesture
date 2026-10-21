"""Launches the gesture recognition and robot behavior nodes together.

TurtleBot 4's own Gazebo simulation is launched separately (see the
README) so this file stays decoupled from whichever TurtleBot 4
simulator launch file the grader/instructor has installed.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    camera_index_arg = DeclareLaunchArgument(
        'camera_index', default_value='0',
        description='OpenCV camera index for the webcam',
    )
    show_preview_arg = DeclareLaunchArgument(
        'show_preview', default_value='true',
        description='Show the OpenCV webcam preview window',
    )

    gesture_params = {
        'camera_index': LaunchConfiguration('camera_index'),
        'show_preview': LaunchConfiguration('show_preview'),
    }

    gesture_node = Node(
        package='tb4_gesture_control',
        executable='gesture_recognition_node',
        name='gesture_recognition_node',
        output='screen',
        parameters=[gesture_params],
    )

    behavior_node = Node(
        package='tb4_gesture_control',
        executable='robot_behavior_node',
        name='robot_behavior_node',
        output='screen',
    )

    return LaunchDescription([
        camera_index_arg,
        show_preview_arg,
        gesture_node,
        behavior_node,
    ])
