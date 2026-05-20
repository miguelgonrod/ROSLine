"""High-level handlers for ROSLine chat intent branches."""

from ros_line.endpoints.chat.context import append_message, get_ros_agent
from ros_line.endpoints.chat.parsing import extract_robot_name_with_llm


def resolve_cmd_vel_topic(ros_agent, robot_name: str, default_topic: str = "/cmd_vel") -> tuple[str, str]:
    cmd_vel_topic = default_topic
    topic_status = "default"

    if not robot_name:
        return cmd_vel_topic, topic_status

    if not ros_agent:
        return cmd_vel_topic, "ros_unavailable"

    try:
        topics_output = ros_agent.list_topics()
        if not topics_output or topics_output.startswith("Error"):
            return cmd_vel_topic, "topics_unavailable"

        for topic in topics_output.split("\n"):
            topic = topic.strip()
            if robot_name.lower() in topic.lower() and "cmd_vel" in topic.lower():
                return topic, "found_specific"

        return cmd_vel_topic, "robot_not_found"
    except Exception as exc:
        print(f"Error obteniendo tópicos: {exc}")
        return cmd_vel_topic, "topics_error"


def _build_twist_message(linear_x: float, linear_y: float, angular_z: float) -> dict:
    return {
        "linear": {"x": linear_x, "y": linear_y, "z": 0.0},
        "angular": {"x": 0.0, "y": 0.0, "z": angular_z},
    }


def handle_move_robot(request, llm, user_input: str, movement_data: dict, append_message_fn=append_message) -> dict:
    ros_agent = get_ros_agent()
    robot_specified = movement_data["robot_specified"]
    robot_name = movement_data["robot_name"]
    linear_x = movement_data["linear_x"]
    linear_y = movement_data["linear_y"]
    angular_z = movement_data["angular_z"]
    description = movement_data["movement_description"]

    if not robot_name:
        robot_name = extract_robot_name_with_llm(llm, user_input)
        robot_specified = bool(robot_name)

    cmd_vel_topic, topic_status = resolve_cmd_vel_topic(ros_agent, robot_name)
    twist_message = _build_twist_message(linear_x, linear_y, angular_z)

    if ros_agent:
        try:
            ros_agent.move_robot(
                linear_x=linear_x,
                linear_y=linear_y,
                linear_z=0.0,
                angular_x=0.0,
                angular_y=0.0,
                angular_z=angular_z,
                topic=cmd_vel_topic.lstrip("/"),
            )

            robot_info = f" para {robot_name}" if robot_specified and robot_name else ""
            topic_info = f"Tópico usado: {cmd_vel_topic}" if cmd_vel_topic != "/cmd_vel" else "Tópico: /cmd_vel (default)"

            if topic_status == "robot_not_found":
                reply_text = (
                    f"⚠️ Robot '{robot_name}' no encontrado, usando tópico default\n"
                    f"✅ Movimiento ejecutado: {description}\n"
                    f"{topic_info}\n"
                    f"Velocidad lineal X: {linear_x} m/s\n"
                    f"Velocidad angular Z: {angular_z} rad/s"
                )
            else:
                reply_text = (
                    f"✅ Movimiento ejecutado{robot_info}: {description}\n"
                    f"{topic_info}\n"
                    f"Velocidad lineal X: {linear_x} m/s\n"
                    f"Velocidad angular Z: {angular_z} rad/s"
                )
            status = "success"
        except Exception as exc:
            reply_text = (
                f"❌ Error al ejecutar movimiento: {description}\n"
                f"Tópico: {cmd_vel_topic}\n"
                f"Error: {str(exc)}"
            )
            status = "error"
    else:
        reply_text = (
            "⚠️ Agente ROS no disponible\n"
            f"Movimiento solicitado: {description}\n"
            f"Tópico: {cmd_vel_topic}"
        )
        status = "ros_unavailable"

    ros_command = (
        f"ros2 topic pub --once {cmd_vel_topic} geometry_msgs/msg/Twist "
        f'"{{linear: {{x: {linear_x}, y: {linear_y}, z: 0.0}}, angular: {{x: 0.0, y: 0.0, z: {angular_z}}}}}"'
    )

    append_message_fn(request.user_id, "ai", reply_text)
    return {
        "userintention": "Move_robot",
        "status": status,
        "robot_specified": robot_specified,
        "robot_name": robot_name if robot_specified else None,
        "topic_used": cmd_vel_topic,
        "topic_status": topic_status,
        "ros_command": ros_command,
        "twist_message": twist_message,
        "reply": reply_text,
    }


def handle_stop_robot(request, llm, user_input: str, append_message_fn=append_message) -> dict:
    ros_agent = get_ros_agent()
    robot_name = extract_robot_name_with_llm(llm, user_input)
    robot_specified = bool(robot_name)

    cmd_vel_topic, topic_status = resolve_cmd_vel_topic(ros_agent, robot_name)
    twist_message = _build_twist_message(0.0, 0.0, 0.0)

    robot_info = f" {robot_name}" if robot_specified and robot_name else ""
    if ros_agent:
        try:
            ros_agent.move_robot(
                linear_x=0.0,
                linear_y=0.0,
                linear_z=0.0,
                angular_x=0.0,
                angular_y=0.0,
                angular_z=0.0,
                topic=cmd_vel_topic.lstrip("/"),
            )

            topic_info = f"Tópico usado: {cmd_vel_topic}" if cmd_vel_topic != "/cmd_vel" else "Tópico: /cmd_vel (default)"

            if topic_status == "robot_not_found":
                reply_text = (
                    f"⚠️ Robot '{robot_name}' no encontrado, usando tópico default\n"
                    f"🛑 Robot detenido correctamente\n"
                    f"{topic_info}\n"
                    "Todas las velocidades en cero."
                )
            else:
                reply_text = (
                    f"🛑 Robot{robot_info} detenido correctamente\n"
                    f"{topic_info}\n"
                    "Todas las velocidades en cero."
                )
            status = "success"
        except Exception as exc:
            reply_text = (
                f"❌ Error al detener el robot{robot_info}\n"
                f"Tópico: {cmd_vel_topic}\n"
                f"Error: {str(exc)}"
            )
            status = "error"
    else:
        reply_text = (
            "⚠️ Agente ROS no disponible\n"
            f"Robot solicitado: {robot_name if robot_name else 'robot por defecto'}\n"
            f"Tópico: {cmd_vel_topic}"
        )
        status = "ros_unavailable"

    ros_command = (
        f'ros2 topic pub --once {cmd_vel_topic} geometry_msgs/msg/Twist '
        f'"{{linear: {{x: 0.0, y: 0.0, z: 0.0}}, angular: {{x: 0.0, y: 0.0, z: 0.0}}}}"'
    )

    append_message_fn(request.user_id, "ai", reply_text)
    return {
        "userintention": "Stop_robot",
        "status": status,
        "robot_specified": robot_specified,
        "robot_name": robot_name if robot_specified else None,
        "topic_used": cmd_vel_topic,
        "topic_status": topic_status,
        "ros_command": ros_command,
        "twist_message": twist_message,
        "reply": reply_text,
    }
