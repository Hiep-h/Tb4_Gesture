import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    camera_index_arg = DeclareLaunchArgument(
        'camera_index', default_value='0',
        description='OpenCV camera index for the webcam',
    )
    show_preview_arg = DeclareLaunchArgument(
        'show_preview', default_value='true',
        description='Show the OpenCV webcam preview window',
    )
    scan_guard_enabled_arg = DeclareLaunchArgument(
        'scan_guard_enabled', default_value='true',
        description='Bo chong va cham theo /scan. Tu dong TAT khi phat hien /scan khong hop le.',
    )
    source_arg = DeclareLaunchArgument(
        'source', default_value='webcam',
        choices=['webcam', 'video', 'image_dir'],
        description='Nguon khung hinh: webcam (mac dinh) | video | image_dir (chi danh cho test).',
    )
    source_path_arg = DeclareLaunchArgument(
        'source_path', default_value='',
        description='Duong dan file video hoac thu muc anh khi source != webcam.',
    )
    fps_cap_arg = DeclareLaunchArgument(
        'fps_cap', default_value='20.0',
        description='Gioi han toc do xu ly khung hinh (Hz).',
    )
    best_frames_dir_arg = DeclareLaunchArgument(
        'best_frames_dir', default_value=os.path.expanduser('~/gesture_report_data/best_frames'),
        description='Thu muc luu anh co do tin cay cao nhat cho moi cu chi.',
    )
    gesture_config_arg = DeclareLaunchArgument(
        'gesture_config',
        default_value=PathJoinSubstitution(
            [FindPackageShare('tb4_gesture_control'), 'config', 'gesture.yaml']),
        description='File yaml chua tham so roi/privacy_mode (ghi boi tools/auto_roi.py).',
    )
    behavior_config_arg = DeclareLaunchArgument(
        'behavior_config',
        default_value=PathJoinSubstitution(
            [FindPackageShare('tb4_gesture_control'), 'config', 'behavior.yaml']),
        description='File yaml chua tham so BehaviorFSM (hold/cooldown/toc do/timeout).',
    )

    gesture_params = {
        'camera_index': LaunchConfiguration('camera_index'),
        'show_preview': LaunchConfiguration('show_preview'),
        'source': LaunchConfiguration('source'),
        'source_path': LaunchConfiguration('source_path'),
        'fps_cap': LaunchConfiguration('fps_cap'),
        'best_frames_dir': LaunchConfiguration('best_frames_dir'),
    }

    gesture_node = Node(
        package='tb4_gesture_control',
        executable='gesture_recognition_node',
        name='gesture_recognition_node',
        output='screen',
        parameters=[LaunchConfiguration('gesture_config'), gesture_params],
    )

    behavior_node = Node(
        package='tb4_gesture_control',
        executable='robot_behavior_node',
        name='robot_behavior_node',
        output='screen',
        parameters=[LaunchConfiguration('behavior_config'), {
            'scan_guard_enabled': LaunchConfiguration('scan_guard_enabled'),
        }],
    )

    return LaunchDescription([
        camera_index_arg,
        show_preview_arg,
        scan_guard_enabled_arg,
        source_arg,
        source_path_arg,
        fps_cap_arg,
        best_frames_dir_arg,
        gesture_config_arg,
        behavior_config_arg,
        gesture_node,
        behavior_node,
    ])
