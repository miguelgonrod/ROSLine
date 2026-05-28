"""High-level handlers for ROSLine chat intent branches."""

from __future__ import annotations

import re
from typing import Any, TYPE_CHECKING

from ros_line.endpoints.actions.agent import RosAgent
from ros_line.endpoints.chat.context import append_message, get_ros_agent
from ros_line.endpoints.chat.parsing import extract_robot_name, extract_robot_name_with_llm
from ros_line.endpoints.dto.message_dto import ChatRequestDTO

if TYPE_CHECKING:
    from langchain_google_genai import ChatGoogleGenerativeAI


def _extract_cmd_vel_namespaces(topics_output: str) -> list[str]:
    """
    Extract the namespaces from movement topics.

    :param topics_output: All the active topics.
    :type topics_output: str

    :return: list of available namespaces
    :rtype: list[str]
    """
    namespaces: list[str] = []
    for raw_topic in topics_output.splitlines():
        topic = raw_topic.strip()
        if not topic or 'cmd_vel' not in topic:
            continue
        if topic.startswith('/'):
            parts = [part for part in topic.split('/') if part]
            if len(parts) >= 2 and 'cmd_vel' in parts[-1]:
                namespaces.append(parts[-2])
    return list(dict.fromkeys(namespaces))


def _infer_namespace_with_llm(
    llm: 'ChatGoogleGenerativeAI | Any',
    user_input: str,
    available_namespaces: list[str],
) -> str:
    """
    Find the required namespace using LLM.

    :param llm: LLM client or interface used to extract information when needed.
    :type llm: ChatGoogleGenerativeAI or Any
    :param user_input: Original user text that triggered the intent.
    :type user_input: str
    :param available_namespaces: List with all available namespaces.
    :type available_namespaces: list[str]

    :return: Required namespace
    :rtype: str
    """
    if not available_namespaces:
        return ''

    prompt_text = (
        'Selecciona el namespace ROS que mejor coincide con la intención del usuario. '
        'Debes responder SOLO con uno de estos valores exactos o con NONE.\n\n'
        f'Namespaces disponibles: {", ".join(available_namespaces)}\n'
        f'Mensaje del usuario: {user_input}\n\n'
        'Respuesta:'
    )

    try:
        result = llm.invoke(prompt_text)
        namespace = getattr(result, 'content', str(result)).strip()
        namespace = namespace.strip().strip(". ,;:!\"'[]{}()")
        if not namespace or namespace.upper() == 'NONE':
            return ''
        if namespace in available_namespaces:
            return namespace
        lowered = namespace.lower()
        for candidate in available_namespaces:
            if candidate.lower() == lowered:
                return candidate
    except Exception as exc:
        print(f'Error inferiendo namespace con LLM: {exc}')

    return ''


def _fallback_namespace_by_index(robot_name: str, available_namespaces: list[str]) -> str:
    """
    Find the required namespace using regex.

    :param robot_name: Robot name said by the user.
    :type robot_name: str
    :param available_namespaces: List with all available namespaces.
    :type available_namespaces: list[str]

    :return: Required namespace
    :rtype: str
    """
    if not robot_name:
        return ''

    index_match = re.search(r'(\d+)', robot_name)
    if not index_match:
        return ''

    robot_index = index_match.group(1)
    candidates = [
        f'tb{robot_index}',
        f'turtlebot{robot_index}',
        f'robot{robot_index}',
    ]

    for namespace in available_namespaces:
        lowered = namespace.lower()
        if lowered in candidates or lowered.endswith(robot_index):
            return namespace

    return ''


def resolve_cmd_vel_topic(ros_agent: RosAgent | None,
                          robot_name: str,
                          default_topic: str = '/cmd_vel') -> tuple[str, str]:
    """
    Find the required topic to publish twist message.

    :param ros_agent: LLM Agent that execute local queries.
    :type ros_agent: RosAgent or None
    :param robot_name: Name of the robot, in case we have multiple ones.
    :type robot_name: str
    :param default_topic: Topic to publish the Twist message
    :type default_topic: str

    :return: tuple with the cmd_vel_topic and its status
    :rtype: tuple[str, str]
    """
    cmd_vel_topic = default_topic
    topic_status = 'default'

    if not robot_name:
        return cmd_vel_topic, topic_status

    if not ros_agent:
        return cmd_vel_topic, 'ros_unavailable'

    try:
        topics_output = ros_agent.list_topics()
        if not topics_output or topics_output.startswith('Error'):
            return cmd_vel_topic, 'topics_unavailable'

        for topic in topics_output.split('\n'):
            topic = topic.strip()
            if robot_name.lower() in topic.lower() and 'cmd_vel' in topic.lower():
                return topic, 'found_specific'

        return cmd_vel_topic, 'robot_not_found'
    except Exception as exc:
        print(f'Error obteniendo tópicos: {exc}')
        return cmd_vel_topic, 'topics_error'


def _build_twist_message(
        linear_x: float,
        linear_y: float,
        angular_z: float,
        linear_z: float = 0.0,
        angular_x: float = 0.0,
        angular_y: float = 0.0) -> dict:
    """
    Build a twist message to publish.

    :param linear_x: Linear value of x
    :type linear_x: float
    :param linear_y: Linear value of y
    :type linear_y: float
    :param angular_z: Angular value of z
    :type angular_z: float
    :param linear_z: Linear value of z
    :type linear_z: float
    :param angular_x: Angular value of x
    :type angular_x: float
    :param angular_y: Angular value of y
    :type angular_y: float


    :return: dictionary with the linear and angular values
    :rtype: dict
    """
    return {
        'linear': {'x': linear_x, 'y': linear_y, 'z': linear_z},
        'angular': {'x': angular_x, 'y': angular_y, 'z': angular_z},
    }


def handle_move_robot(
        request: ChatRequestDTO, llm: 'ChatGoogleGenerativeAI | Any',
        user_input: str, movement_data: dict,
        append_message_fn=append_message) -> dict:
    """
    Manage the logic behind constructing and publishing movement to a robot.

    :param request: Request object containing metadata (must expose `user_id`).
    :type request: ChatRequestDTO
    :param llm: LLM client or interface used to extract information when needed.
    :type llm: ChatGoogleGenerativeAI or Any
    :param user_input: Original user text that triggered the intent.
    :type user_input: str
    :param movement_data: Dictionary with movement parameters and metadata.
    :type movement_data: dict
    :param append_message_fn: Function that adds messaages to chat history.
    :type append_message_fn: callable

    :return: Dictionary with the action result, and metadata required to loggin.
    :rtype: dict
    """
    ros_agent = get_ros_agent()
    robot_specified = movement_data['robot_specified']
    robot_name = movement_data['robot_name']
    linear_x = movement_data.get('linear_x', 0.0)
    linear_y = movement_data.get('linear_y', 0.0)
    linear_z = movement_data.get('linear_z', 0.0)
    angular_x = movement_data.get('angular_x', 0.0)
    angular_y = movement_data.get('angular_y', 0.0)
    angular_z = movement_data.get('angular_z', 0.0)
    description = movement_data['movement_description']

    if not robot_name:
        robot_name = extract_robot_name_with_llm(llm, user_input)
        robot_specified = bool(robot_name)

    cmd_vel_topic, topic_status = resolve_cmd_vel_topic(ros_agent, robot_name)

    if ros_agent and topic_status == 'robot_not_found':
        topics_output = ros_agent.list_topics()
        if topics_output and not topics_output.startswith('Error'):
            namespaces = _extract_cmd_vel_namespaces(topics_output)
            inferred_namespace = _fallback_namespace_by_index(robot_name, namespaces)
            if not inferred_namespace:
                inferred_namespace = _infer_namespace_with_llm(llm, user_input, namespaces)

            if inferred_namespace:
                cmd_vel_topic = f'/{inferred_namespace}/cmd_vel'
                topic_status = 'found_by_inference'
                robot_name = inferred_namespace
                robot_specified = True

    twist_message = _build_twist_message(linear_x, linear_y,
                                         angular_z, linear_z=linear_z,
                                         angular_x=angular_x, angular_y=angular_y)

    if ros_agent:
        try:
            ros_agent.move_robot(
                linear_x=linear_x,
                linear_y=linear_y,
                linear_z=linear_z,
                angular_x=angular_x,
                angular_y=angular_y,
                angular_z=angular_z,
                topic=cmd_vel_topic.lstrip('/'),
            )

            robot_info = f' para {robot_name}' if robot_specified and robot_name else ''
            topic_info = (
                f'Tópico usado: {cmd_vel_topic}'
                if cmd_vel_topic != '/cmd_vel'
                else 'Tópico: /cmd_vel (default)'
            )

            if topic_status == 'robot_not_found':
                reply_text = (
                    f"⚠️ Robot '{robot_name}' no encontrado, usando tópico default\n"
                    f'✅ Movimiento ejecutado: {description}\n'
                    f'{topic_info}\n'
                    f'Velocidad lineal X: {linear_x} m/s\n'
                    f'Velocidad angular Z: {angular_z} rad/s'
                )
            else:
                reply_text = (
                    f'✅ Movimiento ejecutado{robot_info}: {description}\n'
                    f'{topic_info}\n'
                    f'Velocidad lineal X: {linear_x} m/s\n'
                    f'Velocidad angular Z: {angular_z} rad/s'
                )
            status = 'success'
        except Exception as exc:
            reply_text = (
                f'❌ Error al ejecutar movimiento: {description}\n'
                f'Tópico: {cmd_vel_topic}\n'
                f'Error: {str(exc)}'
            )
            status = 'error'
    else:
        reply_text = (
            '⚠️ Agente ROS no disponible\n'
            f'Movimiento solicitado: {description}\n'
            f'Tópico: {cmd_vel_topic}'
        )
        status = 'ros_unavailable'

    ros_command = (
        f'ros2 topic pub --once {cmd_vel_topic} geometry_msgs/msg/Twist '
        f"""\"{{linear: {{x: {linear_x}, y: {linear_y}, z: {linear_z}}},
        angular: {{x: {angular_x}, y: {angular_y}, z: {angular_z}}}}}\""""
    )

    append_message_fn(request.user_id, 'ai', reply_text)
    return {
        'userintention': 'Move_robot',
        'status': status,
        'robot_specified': robot_specified,
        'robot_name': robot_name if robot_specified else None,
        'topic_used': cmd_vel_topic,
        'topic_status': topic_status,
        'ros_command': ros_command,
        'twist_message': twist_message,
        'reply': reply_text,
    }


def handle_stop_robot(
        request: ChatRequestDTO, llm: 'ChatGoogleGenerativeAI | Any',
        user_input: str, append_message_fn=append_message) -> dict:
    """
    Manage the logic behind constructing and publishing a stop message to a robot.

    :param request: Request object containing metadata (must expose `user_id`).
    :type request: ChatRequestDTO
    :param llm: LLM client or interface used to extract information when needed.
    :type llm: ChatGoogleGenerativeAI or Any
    :param user_input: Original user text that triggered the intent.
    :type user_input: str
    :param append_message_fn: Function that adds messaages to chat history.
    :type append_message_fn: callable

    :return: Dictionary with the action result, and metadata required to loggin.
    :rtype: dict
    """
    ros_agent = get_ros_agent()
    robot_name = extract_robot_name(user_input)
    if not robot_name:
        robot_name = extract_robot_name_with_llm(llm, user_input)
    robot_specified = bool(robot_name)

    cmd_vel_topic, topic_status = resolve_cmd_vel_topic(ros_agent, robot_name)

    if ros_agent and topic_status == 'robot_not_found':
        topics_output = ros_agent.list_topics()
        if topics_output and not topics_output.startswith('Error'):
            namespaces = _extract_cmd_vel_namespaces(topics_output)
            inferred_namespace = _fallback_namespace_by_index(robot_name, namespaces)
            if not inferred_namespace:
                inferred_namespace = _infer_namespace_with_llm(llm, user_input, namespaces)

            if inferred_namespace:
                cmd_vel_topic = f'/{inferred_namespace}/cmd_vel'
                topic_status = 'found_by_inference'
                robot_name = inferred_namespace
                robot_specified = True

    # stop: ensure we set all axes to zero
    twist_message = _build_twist_message(0.0, 0.0, 0.0, linear_z=0.0, angular_x=0.0, angular_y=0.0)

    robot_info = f' {robot_name}' if robot_specified and robot_name else ''
    if ros_agent:
        try:
            ros_agent.move_robot(
                linear_x=0.0,
                linear_y=0.0,
                linear_z=0.0,
                angular_x=0.0,
                angular_y=0.0,
                angular_z=0.0,
                topic=cmd_vel_topic.lstrip('/'),
            )

            topic_info = (
                f'Tópico usado: {cmd_vel_topic}'
                if cmd_vel_topic != '/cmd_vel'
                else 'Tópico: /cmd_vel (default)'
            )

            if topic_status == 'robot_not_found':
                reply_text = (
                    f"⚠️ Robot '{robot_name}' no encontrado, usando tópico default\n"
                    f'🛑 Robot detenido correctamente\n'
                    f'{topic_info}\n'
                    'Todas las velocidades en cero.'
                )
            else:
                reply_text = (
                    f'🛑 Robot{robot_info} detenido correctamente\n'
                    f'{topic_info}\n'
                    'Todas las velocidades en cero.'
                )
            status = 'success'
        except Exception as exc:
            reply_text = (
                f'❌ Error al detener el robot{robot_info}\n'
                f'Tópico: {cmd_vel_topic}\n'
                f'Error: {str(exc)}'
            )
            status = 'error'
    else:
        reply_text = (
            '⚠️ Agente ROS no disponible\n'
            f"Robot solicitado: {robot_name if robot_name else 'robot por defecto'}\n"
            f'Tópico: {cmd_vel_topic}'
        )
        status = 'ros_unavailable'

    ros_command = (
        f'ros2 topic pub --once {cmd_vel_topic} geometry_msgs/msg/Twist '
        f'"{{linear: {{x: 0.0, y: 0.0, z: 0.0}}, angular: {{x: 0.0, y: 0.0, z: 0.0}}}}"'
    )

    append_message_fn(request.user_id, 'ai', reply_text)
    return {
        'userintention': 'Stop_robot',
        'status': status,
        'robot_specified': robot_specified,
        'robot_name': robot_name if robot_specified else None,
        'topic_used': cmd_vel_topic,
        'topic_status': topic_status,
        'ros_command': ros_command,
        'twist_message': twist_message,
        'reply': reply_text,
    }
