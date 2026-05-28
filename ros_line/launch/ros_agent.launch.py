#!/usr/bin/env python3

from launch import LaunchDescription
from launch.actions import ExecuteProcess


def generate_launch_description():

    # Process to execute FastAPI server.
    fastapi_server = ExecuteProcess(
        cmd=['python3', '-m', 'ros_line.main'],
        cwd='/home/miguel/ros2_ws/src/ros_line',
        output='screen',
        name='rosline_fastapi_server'
    )

    return LaunchDescription([
        fastapi_server,
    ])
