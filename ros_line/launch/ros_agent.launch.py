#!/usr/bin/env python3

from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    fastapi_server = Node(
        package='ros_line',
        executable='rosline_agent',
        output='screen',
        name='rosline_fastapi_server',
    )

    return LaunchDescription([
        fastapi_server,
    ])
