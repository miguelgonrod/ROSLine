"""Shared chat state and ROS agent lifecycle helpers."""

import os
import threading

import rclpy

from ros_line.endpoints.actions.agent import RosAgent


_memory_store: dict[str, list[dict[str, str]]] = {}
_history_window_size = int(os.getenv('ROSLINE_HISTORY_WINDOW_SIZE', '8'))
_max_memory_messages = int(os.getenv('ROSLINE_MAX_MEMORY_MESSAGES', '24'))
_ros_agent = None
_ros_thread = None


def get_history(user_id: str) -> list[dict[str, str]]:
    """
    Get the chat history.

    :param user_id: Unique code of the user for the LLM.
    :type user_id: str

    :return: List with a dictionary that contains user_id and messages history.
    :rtype: list[dict[str, str]]
    """
    if user_id not in _memory_store:
        _memory_store[user_id] = []
    return _memory_store[user_id]


def append_message(user_id: str, role: str, content: str) -> None:
    """
    Append an specific message to the history.

    :param user_id: Unique code of the user for the LLM.
    :type user_id: str
    :param role: Role of the message sender in the chat.
    :type role: str
    :param content: Content of the message.
    :type content: str
    """
    history = get_history(user_id)
    history.append({'role': role, 'content': content})
    if len(history) > _max_memory_messages:
        del history[:-_max_memory_messages]


def history_as_text(user_id: str, limit: int | None = None) -> str:
    """
    Print the history as an unique text.

    :param user_id: Unique code of the user for the LLM.
    :type user_id: str
    :param limit: Size limit to the history.
    :type limit: int or None

    :return: Parsed string with the complete history.
    :rtype: str
    """
    lines: list[str] = []
    history = get_history(user_id)
    if limit is not None:
        history = history[-limit:]

    for msg in history:
        if msg.get('role') == 'human':
            lines.append(f"Usuario: {msg.get('content', '')}")
        elif msg.get('role') == 'ai':
            lines.append(f"Asistente: {msg.get('content', '')}")
    return '\n'.join(lines)


def get_ros_agent():
    """Inicializa y retorna el agente ROS."""
    global _ros_agent, _ros_thread
    if _ros_agent is None:
        try:
            rclpy.init()
            _ros_agent = RosAgent()
            _ros_thread = threading.Thread(target=rclpy.spin, args=(_ros_agent,), daemon=True)
            _ros_thread.start()
        except Exception as exc:
            print(f'Error al inicializar el agente ROS: {exc}')
            _ros_agent = None

    return _ros_agent


def history_window_size() -> int:
    """
    Give the complete size of the chat history.

    :return: Size of the history window.
    :rtype: int
    """
    return _history_window_size
