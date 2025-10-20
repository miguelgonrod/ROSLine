from setuptools import find_packages, setup
import os
from glob import glob

package_name = 'ros_line'

setup(
    name=package_name,
    version='1.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        # Incluir archivos de launch
        (os.path.join('share', package_name, 'launch'), glob('launch/*.py')),
        # Incluir archivos de configuración
        (os.path.join('share', package_name, 'config'), glob('resource/*')),
    ],
    install_requires=[
    ],
    zip_safe=True,
    maintainer='miguel',
    maintainer_email='miguelgonrod2004@gmail.com',
    description='ROSLine: Agente conversacional inteligente para ROS 2 via WhatsApp',
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
