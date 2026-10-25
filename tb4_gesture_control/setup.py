import os
from glob import glob

from setuptools import find_packages, setup

package_name = 'tb4_gesture_control'


def tree_data_files(source_dir):
    entries = []
    for dirpath, _, filenames in os.walk(source_dir):
        if not filenames:
            continue
        dest = os.path.join('share', package_name, dirpath)
        entries.append((dest, [os.path.join(dirpath, f) for f in filenames]))
    return entries


setup(
    name=package_name,
    version='1.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'),
            glob(os.path.join('launch', '*.launch.py'))),
        (os.path.join('share', package_name, 'config'),
            glob(os.path.join('config', '*.yaml')) + glob(os.path.join('config', '*.config'))),
        (os.path.join('share', package_name, 'models'),
            glob(os.path.join('models', '*.task'))),
        *tree_data_files('worlds'),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='hiep-h',
    maintainer_email='hiepga05102005@gmail.com',
    description=(
        'Non-verbal human-robot interaction for TurtleBot 4: webcam '
        'hand-gesture recognition that selects and confirms robot '
        'behaviors published to /cmd_vel.'
    ),
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'gesture_recognition_node = '
            'tb4_gesture_control.gesture_recognition_node:main',
            'robot_behavior_node = '
            'tb4_gesture_control.robot_behavior_node:main',
        ],
    },
)
