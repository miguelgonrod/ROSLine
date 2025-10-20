#!/usr/bin/env python3

from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.substitutions import LaunchConfiguration
import os
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():

    # Variables de configuración
    host = LaunchConfiguration('host')
    port = LaunchConfiguration('port')
    debug = LaunchConfiguration('debug')

    # Proceso para ejecutar el servidor FastAPI
    fastapi_server = ExecuteProcess(
        cmd=['python3', '-m', 'ros_line.main'],
        cwd='/home/miguel/ros2_ws/src/ros_line',
        output='screen',
        name='rosline_fastapi_server'
    )

    return LaunchDescription([
        fastapi_server,
    ])
