"""Parsing helpers for ROSLine chat intent extraction."""

import re

from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from langchain_google_genai import ChatGoogleGenerativeAI


def detect_direct_intention(user_input: str) -> str | None:
    """
    Detect an specific request from the user, avoiding the excesive use of AI.

    :param user_input: Original user text that triggered the intent.
    :type user_input: str

    :return: User intention or None if is a different request.
    :rtype: str or None
    """
    text = user_input.strip().lower()

    info_request = re.search(
        r'(informaci[óo]n|info|sobre|detalles?|estado|diagn[oó]stico)\b',
        text,
    )
    specific_resource = re.search(
        r'(t[óo]picos?|topics?|nodos?|nodes?|servicios?|services?|/[\w/-]+)\b',
        text,
    )

    if info_request and specific_resource:
        return 'Get_info'

    # Avoid matching 'para' (explanatory questions in spanish)
    if re.search(r'\b(det[ée]n|para(?!\s+(que|qué))|stop|frena|alto)\b', text):
        return 'Stop_robot'

    if re.search(r'\b(t[óo]picos?|topics?|lista\s+de\s+t[óo]picos?)\b', text):
        return 'List_topics'

    if re.search(r'\b(nodos?|nodes?|lista\s+de\s+nodos?)\b', text):
        return 'List_nodes'

    if re.search(r'\b(servicios?|services?|lista\s+de\s+servicios?)\b', text):
        return 'List_services'

    if re.search(r"""\b(info|informaci[óo]n|estado|
                 diagn[oó]stico|bater[ií]a|odometr[ií]a|
                 posici[óo]n)\b""", text):
        return 'Query_state'

    move_keywords = r"""\b(mueve|mover|avanza|avanzar|
        retrocede|retroceder|gira|girar|turn|move|
        forward|backward|left|right)\b"""
    if re.search(move_keywords, text):
        return 'Move_robot'

    return None


def extract_robot_name(user_input: str) -> str:
    """
    Search using regex if there is a known robot namespace.

    :param user_input: Original user text that triggered the intent.
    :type user_input: str

    :return: Robot namespace if exists in known str, or empty if not.
    :rtype: str or None
    """
    text = user_input.lower()
    patterns = [
        r'\b(robot\s*\d+[\w-]*)\b',
        r'\b(turtlebot\s*\d+[\w-]*)\b',
        r'\b(tb\s*\d+[\w-]*)\b',
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).replace(' ', '')

    return ''


def extract_robot_name_with_llm(llm: 'ChatGoogleGenerativeAI | Any', user_input: str) -> str:
    """
    Search using llm if there is a robot namespace.

    :param llm: LLM client or interface used to extract information when needed.
    :type llm: ChatGoogleGenerativeAI or Any
    :param user_input: Original user text that triggered the intent.
    :type user_input: str

    :return: Robot namespace if exists in known str, or empty if not.
    :rtype: str or None
    """
    prompt_text = (
        'Extrae solo el nombre del robot mencionado en el mensaje. '
        """Responde únicamente con el nombre exacto del robot o
        con NONE si no hay un robot específico.\n\n"""
        f'Mensaje: {user_input}'
    )

    try:
        result = llm.invoke(prompt_text)
        robot_name = getattr(result, 'content', str(result)).strip()
        if not robot_name or robot_name.upper() == 'NONE':
            return ''

        robot_name = robot_name.strip().strip(". ,;:!\"'[]{}()")
        return robot_name.replace(' ', '')
    except Exception as exc:
        print(f'Error extrayendo nombre de robot con LLM: {exc}')
        return ''


def extract_number(user_input: str) -> float | None:
    """
    Extract the numeric value of a message.

    :param user_input: Original user text that triggered the intent.
    :type user_input: str

    :return: Float value extracted from the message or None.
    :rtype: float or None
    """
    match = re.search(r'-?\d+(?:[\.,]\d+)?', user_input)
    if not match:
        return None

    return float(match.group(0).replace(',', '.'))


def extract_movement_request(user_input: str) -> dict:
    """
    Search using regex the direction to move the robot.

    Assigns a magnitude to construct the movement dict.

    :param user_input: Original user text that triggered the intent.
    :type user_input: str

    :return: Dictionary with the namespace, and the movement direction.
    :rtype: dict
    """
    text = user_input.lower()
    robot_name = extract_robot_name(text)
    robot_specified = bool(robot_name)
    magnitude = extract_number(text)
    linear_x = 0.0
    linear_y = 0.0
    angular_z = 0.0

    if re.search(r'\b(izquierda|left|gira\s+izquierda|turn\s+left)\b', text):
        angular_z = abs(magnitude) if magnitude is not None else 0.5
    elif re.search(r'\b(derecha|right|gira\s+derecha|turn\s+right)\b', text):
        angular_z = -(abs(magnitude) if magnitude is not None else 0.5)
    elif re.search(r'\b(atr[áa]s|retrocede|backward|backwards)\b', text):
        linear_x = -(abs(magnitude) if magnitude is not None else 0.2)
    elif re.search(r'\b(adelante|avanza|forward)\b', text):
        linear_x = abs(magnitude) if magnitude is not None else 0.2

    if abs(linear_x) > 2.0:
        linear_x = 2.0 if linear_x > 0 else -2.0

    if abs(angular_z) > 3.14:
        angular_z = 3.14 if angular_z > 0 else -3.14

    return {
        'robot_specified': robot_specified,
        'robot_name': robot_name,
        'linear_x': linear_x,
        'linear_y': linear_y,
        'angular_z': angular_z,
        'movement_description': user_input.strip(),
    }


def extract_info_request(user_input: str) -> dict:
    """
    Search using regex the type of data we need.

    Extracts information for specific target types including topic,
    service, message, or node.

    :param user_input: Original user text that triggered the intent.
    :type user_input: str

    :return: Dictionary with the type of information and the name of the
        {topic, service, message, node}
    :rtype: dict
    """
    text = user_input.lower()
    target_name = ''

    match = re.search(r'(/[^\s,.;]+)', text)
    if match:
        target_name = match.group(1)
    else:
        words_after_keywords = re.search(
            r"""(?:info(?:rmación)?|estado|diagn[oó]stico|sobre)\s+
                (?:del\s+|de\s+|la\s+|el\s+)?(.+)$""",
            text,
        )
        if words_after_keywords:
            target_name = words_after_keywords.group(1).strip().split()[0]

    if any(keyword in text for keyword in ['tópico', 'topico', 'topic', 'topics']):
        info_type = 'topic_info'
    elif any(keyword in text for keyword in ['nodo', 'node', 'nodos']):
        info_type = 'node_info'
    elif any(keyword in text for keyword in ['servicio', 'service', 'servicios']):
        info_type = 'service_info'
    elif any(keyword in text for keyword in ['mensaje', 'msg', 'tipo de mensaje']):
        info_type = 'message_type'
    else:
        info_type = 'general_info'

    return {'info_type': info_type, 'target_name': target_name}
