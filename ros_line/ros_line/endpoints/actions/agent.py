"""
Provide the RosAgent class for mapping LLM requests to ROS terminal commands.

Classes:
    ROSAgent: Main class providing the Agent local capabilities.
"""

import os
import subprocess
from typing import Any

from geometry_msgs.msg import Twist
import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class RosAgent(Node):
    """
    A class to provide local functionalities to the LLM Agent.

    This class creates the agent functions, processes this ones, and
    manages local ROS nodes, topics, and so on.
    """

    def __init__(self) -> None:
        """
        Initialize the RosAgent object.

        Creates a node and a subscriber to keep listening ROS topics and nodes.
        """
        super().__init__('ros_line')
        self.get_logger().info('Nodo ros_line iniciado')

        self.subscription = self.create_subscription(
            String,
            'topic_in',
            self.listener_callback,
            10
        )
        self.subscription

        timer_period = 1.0
        self.timer = self.create_timer(timer_period, self.timer_callback)

    def list_topics(self) -> str:
        """
        Get the active ROS2 topics.

        :return: String with all the open topics, or an error.
        :rtype: str
        """
        cmd_str = f"""source /opt/ros/{os.environ.get("ROS_DISTRO", "jazzy")}/setup.bash;
        ros2 topic list"""

        topic_list = subprocess.run(cmd_str, shell=True, capture_output=True, text=True)
        return (
            topic_list.stdout.strip()
            if topic_list.returncode == 0
            else f'Error: {topic_list.stderr}'
        )

    def list_nodes(self) -> str:
        """
        Get the active ROS2 nodes.

        :return: String with all the active nodes, or an error.
        :rtype: str
        """
        cmd_str = f"""source /opt/ros/{os.environ.get("ROS_DISTRO", "jazzy")}/setup.bash;
        ros2 node list"""

        node_list = subprocess.run(cmd_str, shell=True,
                                   capture_output=True, text=True)
        return (
            node_list.stdout.strip()
            if node_list.returncode == 0
            else f'Error: {node_list.stderr}'
        )

    def list_services(self) -> str:
        """
        Get the active ROS2 services.

        :return: String with all the active services, or an error.
        :rtype: str
        """
        cmd_str = f"""source /opt/ros/{os.environ.get("ROS_DISTRO", "jazzy")}/setup.bash;
        ros2 service list"""

        service_list = subprocess.run(cmd_str, shell=True, capture_output=True, text=True)
        return (
            service_list.stdout.strip()
            if service_list.returncode == 0
            else f'Error: {service_list.stderr}'
        )

    def get_info(self, ros_type: str, name: str) -> str:
        """
        Get the information of a ROS2 {topic, node, service}.

        :param ros_type: type of object we need the information {topic, node, service}.
        :type ros_type: str
        :param name: name of the {topic, node, service} which we need to get informaton.
        :type name: str

        :return: String with the information requested, or an error.
        :rtype: str
        """
        cmd_str = f"""source /opt/ros/{os.environ.get("ROS_DISTRO", "jazzy")}/setup.bash;
        ros2 {ros_type} info {name}"""

        object_info = subprocess.run(cmd_str, shell=True, capture_output=True, text=True)
        return (
            object_info.stdout.strip()
            if object_info.returncode == 0
            else f'Error: {object_info.stderr}'
        )

    def move_robot(self, linear_x: float = 0.0, linear_y: float = 0.0, linear_z: float = 0.0,
                   angular_x: float = 0.0, angular_y: float = 0.0, angular_z: float = 0.0,
                   topic: str = 'cmd_vel') -> str:
        """
        Move the robot with an specific linear and angular values.

        :param linear_x: Value for the x axis in the linear movement.
        :type linear_x: float
        :param linear_y: Value for the y axis in the linear movement.
        :type linear_y: float
        :param linear_z: Value for the y axis in the linear movement.
        :type linear_z: float
        :param angular_x: Value for the x axis in the angular movement.
        :type angular_x: float
        :param angular_y: Value for the y axis in the angular movement.
        :type angular_y: float
        :param angular_z: Value for the z axis in the angular movement.
        :type angular_z: float

        :return: String with a confirmation of the movement, or an error.
        :rtype: str
        """
        cmd_vel_publisher = self.create_publisher(Twist, topic, 10)

        try:
            twist = Twist()
            twist.linear.x = float(linear_x)
            twist.linear.y = float(linear_y)
            twist.linear.z = float(linear_z)
            twist.angular.x = float(angular_x)
            twist.angular.y = float(angular_y)
            twist.angular.z = float(angular_z)

            cmd_vel_publisher.publish(twist)

            self.get_logger().info(f"""Publicando en {topic}:
                                   linear_x={linear_x}, linear_y={linear_y}, linear_z={linear_z},
                                   angular_x={angular_x}, angular_y={angular_y},
                                   angular_z={angular_z}""")

            return f"""Comando de movimiento enviado:
        linear=({linear_x}, {linear_y}, {linear_z}),
        angular=({angular_x}, {angular_y}, {angular_z})"""

        except ValueError:
            return 'Error: los valores lineares y angulares de movimiento deben ser numéricos'

        finally:
            self.destroy_publisher(cmd_vel_publisher)
            self.get_logger().info(f'Publicador de {topic} destruido')

    def listener_callback(self, msg: String) -> None:
        """
        Return the message captured by the topic (TODO).

        :param msg: Message captured by the topic
        :type msg: std_msgs/msg/String

        :return: Nothing.
        :rtype: None
        """
        self.get_logger().info(f'Mensaje recibido: {msg.data}')

    def timer_callback(self) -> None:
        """
        Create a timer callback for publishing or listening topics (TODO).

        :return: Nothing.
        :rtype: None
        """
        # TODO
        pass


def main(args: Any = None) -> None:
    """
    Create the main loop for the local agent, in case we don't need the LLM logic.

    :param args: additional arguments if needed for the rclpy initialization
    :type args: Any
    """
    rclpy.init(args=args)
    node = RosAgent()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
