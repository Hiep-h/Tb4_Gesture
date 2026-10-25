from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction, SetEnvironmentVariable
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare

DEV_FAST_MODEL = 'lite'
DEV_FAST_SOFTWARE_RENDER = 'false'
DEV_FAST_RENDER_ENGINE = 'ogre'


def launch_setup(context, *args, **kwargs):
    dev_fast = LaunchConfiguration('dev_fast').perform(context).lower() == 'true'

    if dev_fast:
        model = DEV_FAST_MODEL
        software_render = DEV_FAST_SOFTWARE_RENDER
        render_engine = DEV_FAST_RENDER_ENGINE
    else:
        model = LaunchConfiguration('model').perform(context)
        software_render = LaunchConfiguration('software_render').perform(context)
        render_engine = LaunchConfiguration('render_engine').perform(context)

    pose = {
        'x': LaunchConfiguration('x'),
        'y': LaunchConfiguration('y'),
        'yaw': LaunchConfiguration('yaw'),
    }

    ignition = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution(
            [FindPackageShare('tb4_gesture_control'), 'launch', 'ignition_custom.launch.py'])),
        launch_arguments={
            'world': LaunchConfiguration('world'),
            'model': model,
            'gui': LaunchConfiguration('gui'),
            'render_engine': render_engine,
            'gui_config': LaunchConfiguration('gui_config'),
        }.items(),
    )
    robot_spawn = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution(
            [FindPackageShare('tb4_gesture_control'), 'launch', 'turtlebot4_spawn_no_dock.launch.py'])),
        launch_arguments={
            'rviz': LaunchConfiguration('rviz'),
            'model': model,
            'camera_bridge_enabled': LaunchConfiguration('camera_bridge_enabled'),
            **pose,
        }.items(),
    )
    soft = SetEnvironmentVariable(
        name='LIBGL_ALWAYS_SOFTWARE', value='1',
        condition=IfCondition(software_render),
    )
    own_worlds_path = SetEnvironmentVariable(
        name='GZ_SIM_RESOURCE_PATH',
        value=[PathJoinSubstitution([FindPackageShare('tb4_gesture_control'), 'worlds'])],
    )

    return [soft, own_worlds_path, ignition, robot_spawn]


def generate_launch_description():
    args = [
        DeclareLaunchArgument('world', default_value='small_house'),
        DeclareLaunchArgument('model', default_value='standard'),
        DeclareLaunchArgument('x', default_value='1.0'),
        DeclareLaunchArgument('y', default_value='1.0'),
        DeclareLaunchArgument('yaw', default_value='0.0'),
        DeclareLaunchArgument('rviz', default_value='false'),
        DeclareLaunchArgument('software_render', default_value='true'),
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        DeclareLaunchArgument('gui', default_value='true',
                              description='Show the Gazebo GUI. false = server-only '
                                           '(headless); pair with rviz:=true for development.'),
        DeclareLaunchArgument('render_engine', default_value='',
                              description='Ignition render engine override: ogre or ogre2. '
                                           'Empty = Gazebo default (ogre2).'),
        DeclareLaunchArgument('gui_config', default_value=PathJoinSubstitution(
                                  [FindPackageShare('tb4_gesture_control'), 'config', 'gui_small.config']),
                              description='Duong dan file gui.config. Mac dinh dung '
                                           'config/gui_small.config (cua so nho, bo cac '
                                           'plugin khong can) de giam tai render GUI; truyen '
                                           'gui_config:="" de quay ve gui.config day du cua '
                                           'turtlebot4_ignition_bringup (vi du khi quay video demo).'),
        DeclareLaunchArgument('camera_bridge_enabled', default_value='false',
                              description='Bridge /oakd/rgb/... (anh + depth + points) sang '
                                           'ROS. Mac dinh false vi gesture_recognition_node '
                                           'dung webcam rieng, khong can camera mo phong nay; '
                                           'tat bridge giup gzserver khong render cam RGBD.'),
        DeclareLaunchArgument('dev_fast', default_value='false',
                              description='Che do "phat trien nhanh" (cau hinh F): ep '
                                           'model=lite, software_render=false, '
                                           'render_engine=ogre, ghi de moi gia tri khac duoc '
                                           'truyen vao. RTF cao nhung /scan KHONG hop le -> bo '
                                           'chong va cham tu tat. KHONG dung de quay video demo.'),
    ]
    return LaunchDescription(args + [OpaqueFunction(function=launch_setup)])
