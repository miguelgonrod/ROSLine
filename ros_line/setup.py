from glob import glob
import os

from setuptools import find_packages, setup

package_name = 'ros_line'
config_files = [
    path for path in glob('resource/*')
    if os.path.basename(path) != package_name
]

setup(
    name=package_name,
    version='2.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        # Incluir archivos de launch
        (os.path.join('share', package_name, 'launch'), glob('launch/*.py')),
        # Incluir archivos de configuración
        (os.path.join('share', package_name, 'config'), config_files),
    ],
    install_requires=[
    ],
    zip_safe=True,
    maintainer='Miguel Angel Gonzalez Rodriguez',
    maintainer_email='miguel_gonzalezr@ieee.org',
    description=(
        'ROSLine is a natural language interface that bridges WhatsApp and ROS 2. '
        'It allows users to control and monitor ROS-based robots through chat commands '
        'powered by Gemini and a lightweight reasoning layer.'
    ),
    license='Apache License 2.0',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'rosline_agent = ros_line.main:main',
            'ros_fastapi_node = ros_line.ros_fastapi_node:main',
        ],
    },
)
