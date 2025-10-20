import rclpy
from rclpy.node import Node

import subprocess
import os

from std_msgs.msg import String
from geometry_msgs.msg import Twist

class RosAgent(Node):
    def __init__(self):
        super().__init__('ros_line')
        self.get_logger().info('Nodo ros_line iniciado')

        # Publicadores y suscriptores
        self.subscription = self.create_subscription(
            String,
            'topic_in',
            self.listener_callback,
            10
        )
        self.subscription  # evita advertencias de variable no usada

        # Timer para ejecutar periódicamente una función
        timer_period = 1.0  # segundos
        self.timer = self.create_timer(timer_period, self.timer_callback)

    def list_topics(self):
        cmd_str = f'source /opt/ros/{os.environ.get("ROS_DISTRO", "humble")}/setup.bash; ros2 topic list'

        topic_list = subprocess.run(cmd_str, shell=True, capture_output=True, text=True)
        return topic_list.stdout.strip() if topic_list.returncode == 0 else f"Error: {topic_list.stderr}"
        
    def list_nodes(self):
        cmd_str = f'source /opt/ros/{os.environ.get("ROS_DISTRO", "humble")}/setup.bash; ros2 node list'

        node_list = subprocess.run(cmd_str, shell=True, capture_output=True, text=True)
        return node_list.stdout.strip() if node_list.returncode == 0 else f"Error: {node_list.stderr}"
        
    def list_services(self):
        cmd_str = f'source /opt/ros/{os.environ.get("ROS_DISTRO", "humble")}/setup.bash; ros2 service list'

        service_list = subprocess.run(cmd_str, shell=True, capture_output=True, text=True)
        return service_list.stdout.strip() if service_list.returncode == 0 else f"Error: {service_list.stderr}"
        
    def get_info(self, type, topic):
        cmd_str = f'source /opt/ros/{os.environ.get("ROS_DISTRO", "humble")}/setup.bash; ros2 {type} info {topic}'

        object_info = subprocess.run(cmd_str, shell=True, capture_output=True, text=True)
        return object_info.stdout.strip() if object_info.returncode == 0 else f"Error: {object_info.stderr}"

    # Metodo que publica al topico de movimiento usando la convencion de ros2 python
    def move_robot(self, linear_x, linear_y, linear_z, angular_x, angular_y, angular_z, topic='cmd_vel'):
        # Crear el publicador solo cuando se necesite
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
            
            self.get_logger().info(f'Publicando en {topic}: linear_x={linear_x}, linear_y={linear_y}, linear_z={linear_z}, angular_x={angular_x}, angular_y={angular_y}, angular_z={angular_z}')
            
            return f"Comando de movimiento enviado: linear=({linear_x}, {linear_y}, {linear_z}), angular=({angular_x}, {angular_y}, {angular_z})"
        
        finally:
            # Destruir el publicador después de usarlo
            self.destroy_publisher(cmd_vel_publisher)
            self.get_logger().info(f'Publicador de {topic} destruido')
        
    # Metodo que llama un servicio x usando la convencion de ros2 python
    def call_service(self, service_name, service_type, request):
        client = self.create_client(service_type, service_name)
        while not client.wait_for_service(timeout_sec=1.0):
            self.get_logger().info(f'Servicio {service_name} no disponible, esperando...')

        future = client.call_async(request)
        rclpy.spin_until_future_complete(self, future)
        return future.result()

    def listener_callback(self, msg):
        self.get_logger().info(f'Mensaje recibido: {msg.data}')
        # TODO: Lógica de callback

    def timer_callback(self):
        # Timer callback - puedes usar esto para tareas periódicas si es necesario
        pass

def main(args=None):
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