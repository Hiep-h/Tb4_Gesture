import os
from pathlib import Path

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction, SetEnvironmentVariable
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node


ARGUMENTS = [
    DeclareLaunchArgument('world', default_value='warehouse',
                          description='Ignition World'),
    DeclareLaunchArgument('model', default_value='lite',
                          choices=['standard', 'lite'],
                          description='Turtlebot4 Model'),
    DeclareLaunchArgument('gui', default_value='true',
                          description='Show the Gazebo GUI. false runs server-only (headless).'),
    DeclareLaunchArgument('render_engine', default_value='',
                          description='Ignition render engine override: ogre or ogre2. '
                                       'Empty = Gazebo default (ogre2).'),
    DeclareLaunchArgument('gui_config', default_value='',
                          description='Duong dan file gui.config tuy chinh (vi du '
                                       'config/gui_small.config trong repo nay, cua so GUI '
                                       'nho hon de giam tai render). Rong = dung gui.config '
                                       'mac dinh cua turtlebot4_ignition_bringup.'),
]


def launch_setup(context, *args, **kwargs):
    pkg_turtlebot4_ignition_bringup = get_package_share_directory('turtlebot4_ignition_bringup')
    pkg_turtlebot4_ignition_gui_plugins = get_package_share_directory('turtlebot4_ignition_gui_plugins')
    pkg_turtlebot4_description = get_package_share_directory('turtlebot4_description')
    pkg_irobot_create_description = get_package_share_directory('irobot_create_description')
    pkg_irobot_create_ignition_bringup = get_package_share_directory('irobot_create_ignition_bringup')
    pkg_irobot_create_ignition_plugins = get_package_share_directory('irobot_create_ignition_plugins')
    pkg_ros_ign_gazebo = get_package_share_directory('ros_ign_gazebo')

    world = LaunchConfiguration('world').perform(context)
    model = LaunchConfiguration('model').perform(context)
    render_engine = LaunchConfiguration('render_engine').perform(context)
    gui = LaunchConfiguration('gui').perform(context).lower() == 'true'

    ign_resource_path = SetEnvironmentVariable(
        name='IGN_GAZEBO_RESOURCE_PATH',
        value=os.pathsep.join([
            os.path.join(pkg_turtlebot4_ignition_bringup, 'worlds'),
            os.path.join(pkg_irobot_create_ignition_bringup, 'worlds'),
            str(Path(pkg_turtlebot4_description).parent.resolve()),
            str(Path(pkg_irobot_create_description).parent.resolve())]))

    ign_gui_plugin_path = SetEnvironmentVariable(
        name='IGN_GUI_PLUGIN_PATH',
        value=os.pathsep.join([
            os.path.join(pkg_turtlebot4_ignition_gui_plugins, 'lib'),
            os.path.join(pkg_irobot_create_ignition_plugins, 'lib')]))

    ign_args = f'{world}.sdf -r -v 4'
    if gui:
        gui_config_override = LaunchConfiguration('gui_config').perform(context)
        gui_config = gui_config_override if gui_config_override else os.path.join(
            pkg_turtlebot4_ignition_bringup, 'gui', model, 'gui.config')
        ign_args += f' --gui-config {gui_config}'
    else:
        ign_args += ' -s'
    if render_engine:
        ign_args += f' --render-engine {render_engine}'

    ign_gazebo_launch = PathJoinSubstitution([pkg_ros_ign_gazebo, 'launch', 'ign_gazebo.launch.py'])
    ignition_gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([ign_gazebo_launch]),
        launch_arguments=[('ign_args', ign_args)])

    clock_bridge = Node(package='ros_gz_bridge', executable='parameter_bridge',
                        name='clock_bridge',
                        output='screen',
                        arguments=[
                            '/clock' + '@rosgraph_msgs/msg/Clock' + '[ignition.msgs.Clock'
                        ])

    return [ign_resource_path, ign_gui_plugin_path, ignition_gazebo, clock_bridge]


def generate_launch_description():
    return LaunchDescription(ARGUMENTS + [OpaqueFunction(function=launch_setup)])
