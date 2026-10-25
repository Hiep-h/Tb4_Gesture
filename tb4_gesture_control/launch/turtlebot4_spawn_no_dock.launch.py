from ament_index_python.packages import get_package_share_directory

from irobot_create_common_bringup.namespace import GetNamespacedName
from irobot_create_common_bringup.offset import OffsetParser

from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, ExecuteProcess, GroupAction,
                            IncludeLaunchDescription, TimerAction)
from launch.conditions import IfCondition, LaunchConfigurationEquals
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution

from launch_ros.actions import Node, PushRosNamespace

TURTLEBOT4_HMI_LEDS = [
    'power', 'motors', 'comms', 'wifi', 'battery', 'user1', 'user2',
]

MOTION_CONTROL_SAFETY_OVERRIDE = 'backup_only'
MOTION_CONTROL_SAFETY_OVERRIDE_DELAY_S = 5.0


ARGUMENTS = [
    DeclareLaunchArgument('rviz', default_value='false',
                          choices=['true', 'false'],
                          description='Start rviz.'),
    DeclareLaunchArgument('use_sim_time', default_value='true',
                          choices=['true', 'false'],
                          description='use_sim_time'),
    DeclareLaunchArgument('model', default_value='standard',
                          choices=['standard', 'lite'],
                          description='Turtlebot4 Model'),
    DeclareLaunchArgument('namespace', default_value='',
                          description='Robot namespace'),
    DeclareLaunchArgument('localization', default_value='false',
                          choices=['true', 'false'],
                          description='Whether to launch localization'),
    DeclareLaunchArgument('slam', default_value='false',
                          choices=['true', 'false'],
                          description='Whether to launch SLAM'),
    DeclareLaunchArgument('nav2', default_value='false',
                          choices=['true', 'false'],
                          description='Whether to launch Nav2'),
    DeclareLaunchArgument('camera_bridge_enabled', default_value='false',
                          choices=['true', 'false'],
                          description='Bridge camera RGBD /oakd/rgb/preview/... sang ROS. '
                                       'Mac dinh false: gesture_recognition_node dung webcam '
                                       'rieng nen khong can; tat bridge nay giup gzserver '
                                       'khong phai render camera RGBD mo phong moi buoc.'),
]

for pose_element in ['x', 'y', 'z', 'yaw']:
    ARGUMENTS.append(DeclareLaunchArgument(pose_element, default_value='0.0',
                     description=f'{pose_element} component of the robot pose.'))


def generate_launch_description():
    pkg_turtlebot4_ignition_bringup = get_package_share_directory(
        'turtlebot4_ignition_bringup')
    pkg_turtlebot4_description = get_package_share_directory(
        'turtlebot4_description')
    pkg_turtlebot4_viz = get_package_share_directory(
        'turtlebot4_viz')
    pkg_turtlebot4_navigation = get_package_share_directory(
        'turtlebot4_navigation')
    pkg_irobot_create_common_bringup = get_package_share_directory(
        'irobot_create_common_bringup')
    pkg_irobot_create_ignition_bringup = get_package_share_directory(
        'irobot_create_ignition_bringup')

    create3_ros_ign_bridge_launch = PathJoinSubstitution(
        [pkg_irobot_create_ignition_bringup, 'launch', 'create3_ros_ignition_bridge.launch.py'])
    rviz_launch = PathJoinSubstitution(
        [pkg_turtlebot4_viz, 'launch', 'view_robot.launch.py'])
    turtlebot4_node_launch = PathJoinSubstitution(
        [pkg_turtlebot4_ignition_bringup, 'launch', 'turtlebot4_nodes.launch.py'])
    create3_nodes_launch = PathJoinSubstitution(
        [pkg_irobot_create_common_bringup, 'launch', 'create3_nodes.launch.py'])
    create3_ignition_nodes_launch = PathJoinSubstitution(
        [pkg_irobot_create_ignition_bringup, 'launch', 'create3_ignition_nodes.launch.py'])
    robot_description_launch = PathJoinSubstitution(
        [pkg_turtlebot4_description, 'launch', 'robot_description.launch.py'])
    localization_launch = PathJoinSubstitution(
        [pkg_turtlebot4_navigation, 'launch', 'localization.launch.py'])
    slam_launch = PathJoinSubstitution(
        [pkg_turtlebot4_navigation, 'launch', 'slam.launch.py'])
    nav2_launch = PathJoinSubstitution(
        [pkg_turtlebot4_navigation, 'launch', 'nav2.launch.py'])

    param_file_cmd = DeclareLaunchArgument(
        'param_file',
        default_value=PathJoinSubstitution(
            [pkg_turtlebot4_ignition_bringup, 'config', 'turtlebot4_node.yaml']),
        description='Turtlebot4 Robot param file')

    namespace = LaunchConfiguration('namespace')
    use_sim_time = LaunchConfiguration('use_sim_time')
    x, y, z = LaunchConfiguration('x'), LaunchConfiguration('y'), LaunchConfiguration('z')
    yaw = LaunchConfiguration('yaw')
    turtlebot4_node_yaml_file = LaunchConfiguration('param_file')

    robot_name = GetNamespacedName(namespace, 'turtlebot4')
    dock_name = GetNamespacedName(namespace, 'standard_dock')

    z_robot = OffsetParser(z, -0.0025)

    world = LaunchConfiguration('world')
    camera_bridge_enabled = LaunchConfiguration('camera_bridge_enabled')

    create3_bridge = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([create3_ros_ign_bridge_launch]),
        launch_arguments=[
            ('robot_name', robot_name),
            ('dock_name', dock_name),
            ('namespace', namespace),
            ('world', world)
        ]
    )

    lidar_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='lidar_bridge',
        output='screen',
        parameters=[{'use_sim_time': use_sim_time}],
        arguments=[
            ['/world/', world, '/model/', robot_name,
             '/link/rplidar_link/sensor/rplidar/scan' +
             '@sensor_msgs/msg/LaserScan[ignition.msgs.LaserScan']
        ],
        remappings=[
            (['/world/', world, '/model/', robot_name,
              '/link/rplidar_link/sensor/rplidar/scan'],
             'scan')
        ])

    hmi_display_msg_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='hmi_display_msg_bridge',
        output='screen',
        parameters=[{'use_sim_time': use_sim_time}],
        arguments=[
            [namespace, '/hmi/display/raw@std_msgs/msg/String]ignition.msgs.StringMsg'],
            [namespace, '/hmi/display/selected@std_msgs/msg/Int32]ignition.msgs.Int32'],
        ],
        remappings=[
            ([namespace, '/hmi/display/raw'], 'hmi/display/_raw'),
            ([namespace, '/hmi/display/selected'], 'hmi/display/_selected'),
        ],
        condition=LaunchConfigurationEquals('model', 'standard'))

    hmi_buttons_msg_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='hmi_buttons_msg_bridge',
        output='screen',
        parameters=[{'use_sim_time': use_sim_time}],
        arguments=[
            [namespace, '/hmi/buttons@std_msgs/msg/Int32[ignition.msgs.Int32'],
        ],
        remappings=[
            ([namespace, '/hmi/buttons'], 'hmi/buttons/_set'),
        ],
        condition=LaunchConfigurationEquals('model', 'standard'))

    hmi_led_msg_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='hmi_led_msg_bridge',
        output='screen',
        parameters=[{'use_sim_time': use_sim_time}],
        arguments=[
            [namespace, '/hmi/led/' + led + '@std_msgs/msg/Int32]ignition.msgs.Int32']
            for led in TURTLEBOT4_HMI_LEDS
        ],
        remappings=[
            ([namespace, '/hmi/led/' + led], 'hmi/led/_' + led)
            for led in TURTLEBOT4_HMI_LEDS
        ],
        condition=LaunchConfigurationEquals('model', 'standard'))

    oakd_camera_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='camera_bridge',
        output='screen',
        parameters=[{'use_sim_time': use_sim_time}],
        arguments=[
            ['/world/', world, '/model/', robot_name,
             '/link/oakd_rgb_camera_frame/sensor/rgbd_camera/image' +
             '@sensor_msgs/msg/Image[ignition.msgs.Image'],
            ['/world/', world, '/model/', robot_name,
             '/link/oakd_rgb_camera_frame/sensor/rgbd_camera/depth_image' +
             '@sensor_msgs/msg/Image[ignition.msgs.Image'],
            ['/world/', world, '/model/', robot_name,
             '/link/oakd_rgb_camera_frame/sensor/rgbd_camera/points' +
             '@sensor_msgs/msg/PointCloud2[ignition.msgs.PointCloudPacked'],
            ['/world/', world, '/model/', robot_name,
             '/link/oakd_rgb_camera_frame/sensor/rgbd_camera/camera_info' +
             '@sensor_msgs/msg/CameraInfo[ignition.msgs.CameraInfo'],
        ],
        remappings=[
            (['/world/', world, '/model/', robot_name,
              '/link/oakd_rgb_camera_frame/sensor/rgbd_camera/image'],
             'oakd/rgb/preview/image_raw'),
            (['/world/', world, '/model/', robot_name,
              '/link/oakd_rgb_camera_frame/sensor/rgbd_camera/depth_image'],
             'oakd/rgb/preview/depth'),
            (['/world/', world, '/model/', robot_name,
              '/link/oakd_rgb_camera_frame/sensor/rgbd_camera/points'],
             'oakd/rgb/preview/depth/points'),
            (['/world/', world, '/model/', robot_name,
              '/link/oakd_rgb_camera_frame/sensor/rgbd_camera/camera_info'],
             'oakd/rgb/preview/camera_info'),
        ],
        condition=IfCondition(camera_bridge_enabled))

    spawn_robot_group_action = GroupAction([
        PushRosNamespace(namespace),

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([robot_description_launch]),
            launch_arguments=[('model', LaunchConfiguration('model')),
                              ('use_sim_time', LaunchConfiguration('use_sim_time'))]
        ),

        Node(
            package='ros_ign_gazebo',
            executable='create',
            arguments=['-name', robot_name,
                       '-x', x,
                       '-y', y,
                       '-z', z_robot,
                       '-Y', yaw,
                       '-topic', 'robot_description'],
            output='screen'
        ),

        create3_bridge,
        lidar_bridge,
        hmi_display_msg_bridge,
        hmi_buttons_msg_bridge,
        hmi_led_msg_bridge,
        oakd_camera_bridge,

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([turtlebot4_node_launch]),
            launch_arguments=[('model', LaunchConfiguration('model')),
                              ('param_file', turtlebot4_node_yaml_file)]
        ),

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([create3_nodes_launch]),
            launch_arguments=[
                ('namespace', namespace)
            ]
        ),

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([create3_ignition_nodes_launch]),
            launch_arguments=[
                ('robot_name', robot_name),
                ('dock_name', dock_name),
            ]
        ),

        Node(
            name='rplidar_stf',
            package='tf2_ros',
            executable='static_transform_publisher',
            output='screen',
            arguments=[
                '0', '0', '0', '0', '0', '0.0',
                'rplidar_link', [robot_name, '/rplidar_link/rplidar']],
            remappings=[
                ('/tf', 'tf'),
                ('/tf_static', 'tf_static'),
            ]
        ),

        Node(
            name='camera_stf',
            package='tf2_ros',
            executable='static_transform_publisher',
            output='screen',
            arguments=[
                '0', '0', '0',
                '1.5707', '-1.5707', '0',
                'oakd_rgb_camera_optical_frame',
                [robot_name, '/oakd_rgb_camera_frame/rgbd_camera']
            ],
            remappings=[
                ('/tf', 'tf'),
                ('/tf_static', 'tf_static'),
            ]
        ),

    ])

    localization = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([localization_launch]),
        launch_arguments=[
            ('namespace', namespace),
            ('use_sim_time', use_sim_time)
        ],
        condition=IfCondition(LaunchConfiguration('localization'))
    )

    slam = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([slam_launch]),
        launch_arguments=[
            ('namespace', namespace),
            ('use_sim_time', use_sim_time)
        ],
        condition=IfCondition(LaunchConfiguration('slam'))
    )

    nav2 = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([nav2_launch]),
        launch_arguments=[
            ('namespace', namespace),
            ('use_sim_time', use_sim_time)
        ],
        condition=IfCondition(LaunchConfiguration('nav2'))
    )

    rviz = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([rviz_launch]),
        launch_arguments=[
            ('namespace', namespace),
            ('use_sim_time', use_sim_time)],
        condition=IfCondition(LaunchConfiguration('rviz')),
    )

    motion_control_name = ['/', GetNamespacedName(namespace, 'motion_control')]
    set_motion_control_safety_override = TimerAction(
        period=MOTION_CONTROL_SAFETY_OVERRIDE_DELAY_S,
        actions=[ExecuteProcess(
            cmd=['ros2', 'param', 'set', motion_control_name,
                 'safety_override', MOTION_CONTROL_SAFETY_OVERRIDE],
            output='screen',
        )],
    )

    ld = LaunchDescription(ARGUMENTS)
    ld.add_action(param_file_cmd)
    ld.add_action(spawn_robot_group_action)
    ld.add_action(set_motion_control_safety_override)
    ld.add_action(localization)
    ld.add_action(slam)
    ld.add_action(nav2)
    ld.add_action(rviz)
    return ld
