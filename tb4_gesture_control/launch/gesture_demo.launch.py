import os
import subprocess

from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, IncludeLaunchDescription, LogInfo,
                            OpaqueFunction, Shutdown)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare

ALREADY_RUNNING_PATTERNS = (
    'tb4_gesture_control/gesture_recognition_node',
    'tb4_gesture_control/robot_behavior_node',
)


def already_running_pattern():
    for pattern in ALREADY_RUNNING_PATTERNS:
        result = subprocess.run(['pgrep', '-f', pattern], stdout=subprocess.PIPE)
        if result.stdout.strip():
            return pattern
    return None


DEV_FAST_WARNING = (
    '\n'
    '################################################################\n'
    '#  CANH BAO: dev_fast:=true dang BAT ("che do phat trien nhanh")\n'
    '#  /scan se KHONG hop le tren may nay (render hardware + ogre)  \n'
    '#  -> bo chong va cham theo /scan se TU TAT.                    \n'
    '#  KHONG dung cau hinh nay de quay video nop bai.               \n'
    '################################################################\n'
)


def launch_setup(context, *args, **kwargs):
    dev_fast = LaunchConfiguration('dev_fast').perform(context).lower() == 'true'
    actions = []
    if dev_fast:
        actions.append(LogInfo(msg=DEV_FAST_WARNING))
    return actions


def generate_launch_description():
    running = already_running_pattern()
    if running:
        return LaunchDescription([
            LogInfo(msg=f'LOI: da co tien trinh khop "{running}" dang chay. '
                        f'Dung lai de tranh hai node trung lap cung ghi log/publish '
                        f'/detected_gesture hoac /cmd_vel. Chay scripts/stop_all.sh truoc.'),
            Shutdown(reason=f'duplicate process matching {running}'),
        ])

    args = [
        DeclareLaunchArgument('world', default_value='small_house'),
        DeclareLaunchArgument('model', default_value='standard'),
        DeclareLaunchArgument('x', default_value='1.0'),
        DeclareLaunchArgument('y', default_value='1.0'),
        DeclareLaunchArgument('yaw', default_value='0.0'),
        DeclareLaunchArgument('rviz', default_value='false'),
        DeclareLaunchArgument('software_render', default_value='true'),
        DeclareLaunchArgument('gui', default_value='true'),
        DeclareLaunchArgument('render_engine', default_value=''),
        DeclareLaunchArgument('gui_config', default_value=PathJoinSubstitution(
                                  [FindPackageShare('tb4_gesture_control'), 'config', 'gui_small.config'])),
        DeclareLaunchArgument('camera_bridge_enabled', default_value='false'),
        DeclareLaunchArgument('dev_fast', default_value='false',
                              description='Che do "phat trien nhanh" (cau hinh F). '
                                           'KHONG dung de quay video demo.'),
        DeclareLaunchArgument('scan_guard_enabled', default_value='true'),
        DeclareLaunchArgument('camera_index', default_value='0'),
        DeclareLaunchArgument('show_preview', default_value='true'),
        DeclareLaunchArgument('source', default_value='webcam',
                              choices=['webcam', 'video', 'image_dir']),
        DeclareLaunchArgument('source_path', default_value=''),
        DeclareLaunchArgument('fps_cap', default_value='20.0'),
        DeclareLaunchArgument('best_frames_dir',
                              default_value=os.path.expanduser('~/gesture_report_data/best_frames')),
        DeclareLaunchArgument('gesture_config',
                              default_value=PathJoinSubstitution(
                                  [FindPackageShare('tb4_gesture_control'), 'config', 'gesture.yaml'])),
        DeclareLaunchArgument('behavior_config',
                              default_value=PathJoinSubstitution(
                                  [FindPackageShare('tb4_gesture_control'), 'config', 'behavior.yaml'])),
    ]

    sim = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution(
            [FindPackageShare('tb4_gesture_control'), 'launch', 'sim.launch.py'])),
        launch_arguments={
            'world': LaunchConfiguration('world'),
            'model': LaunchConfiguration('model'),
            'x': LaunchConfiguration('x'),
            'y': LaunchConfiguration('y'),
            'yaw': LaunchConfiguration('yaw'),
            'rviz': LaunchConfiguration('rviz'),
            'software_render': LaunchConfiguration('software_render'),
            'gui': LaunchConfiguration('gui'),
            'render_engine': LaunchConfiguration('render_engine'),
            'dev_fast': LaunchConfiguration('dev_fast'),
            'gui_config': LaunchConfiguration('gui_config'),
            'camera_bridge_enabled': LaunchConfiguration('camera_bridge_enabled'),
        }.items(),
    )

    gesture_control = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution(
            [FindPackageShare('tb4_gesture_control'), 'launch', 'gesture_control.launch.py'])),
        launch_arguments={
            'camera_index': LaunchConfiguration('camera_index'),
            'show_preview': LaunchConfiguration('show_preview'),
            'scan_guard_enabled': LaunchConfiguration('scan_guard_enabled'),
            'source': LaunchConfiguration('source'),
            'source_path': LaunchConfiguration('source_path'),
            'fps_cap': LaunchConfiguration('fps_cap'),
            'best_frames_dir': LaunchConfiguration('best_frames_dir'),
            'gesture_config': LaunchConfiguration('gesture_config'),
            'behavior_config': LaunchConfiguration('behavior_config'),
        }.items(),
    )

    return LaunchDescription(
        args + [OpaqueFunction(function=launch_setup), sim, gesture_control]
    )
