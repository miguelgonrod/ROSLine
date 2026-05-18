from fastapi import APIRouter, HTTPException
from fastapi_utils.cbv import cbv

import base64
import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
import google.generativeai as genai

"""Chat endpoints sin utilizar helpers de memoria de LangChain.

Se usa un almacenamiento en memoria simple (dict + listas) por usuario
para construir el contexto de conversación y se generan prompts como cadenas.
"""

from ros_line.endpoints.dto.message_dto import (ChatRequestDTO)
from ros_line.endpoints.actions.agent import RosAgent

import rclpy
import threading
import re

# --- Configuración de entorno ---
# Buscar archivo .env en la carpeta resource
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'resource', '.env')
load_dotenv(dotenv_path)

# --- Router y clase del servicio de chat ---
chat_webservice_api_router = APIRouter()

# Memoria en proceso por usuario: { user_id: [ {"role": "human"|"ai", "content": str }, ... ] }
_memory_store = {}
_history_window_size = int(os.getenv("ROSLINE_HISTORY_WINDOW_SIZE", "8"))
_max_memory_messages = int(os.getenv("ROSLINE_MAX_MEMORY_MESSAGES", "24"))

# Agente ROS global
_ros_agent = None
_ros_thread = None


def _get_ros_agent():
    """Inicializa y retorna el agente ROS"""
    global _ros_agent, _ros_thread
    if _ros_agent is None:
        try:
            rclpy.init()
            _ros_agent = RosAgent()
            
            # Ejecutar el agente en un hilo separado
            _ros_thread = threading.Thread(target=rclpy.spin, args=(_ros_agent,), daemon=True)
            _ros_thread.start()
            
        except Exception as e:
            print(f"Error al inicializar el agente ROS: {e}")
            _ros_agent = None
    
    return _ros_agent


def _get_history(user_id: str):
    if user_id not in _memory_store:
        _memory_store[user_id] = []
    return _memory_store[user_id]


def _append_message(user_id: str, role: str, content: str) -> None:
    history = _get_history(user_id)
    history.append({"role": role, "content": content})
    if len(history) > _max_memory_messages:
        del history[:-_max_memory_messages]


def _history_as_text(user_id: str, limit: int | None = None) -> str:
    lines = []
    history = _get_history(user_id)
    if limit is not None:
        history = history[-limit:]

    for msg in history:
        if msg.get("role") == "human":
            lines.append(f"Usuario: {msg.get('content', '')}")
        elif msg.get("role") == "ai":
            lines.append(f"Asistente: {msg.get('content', '')}")
    return "\n".join(lines)


def _detect_direct_intention(user_input: str):
    text = user_input.strip().lower()

    if re.search(r"\b(det[ée]n|para|stop|frena|alto)\b", text):
        return "Stop_robot"

    if re.search(r"\b(t[óo]picos?|topics?|lista\s+de\s+t[óo]picos?)\b", text):
        return "List_topics"

    if re.search(r"\b(nodos?|nodes?|lista\s+de\s+nodos?)\b", text):
        return "List_nodes"

    if re.search(r"\b(servicios?|services?|lista\s+de\s+servicios?)\b", text):
        return "List_services"

    if re.search(r"\b(info|informaci[óo]n|estado|diagn[oó]stico|bater[ií]a|odometr[ií]a|posici[óo]n)\b", text):
        return "Query_state"

    move_keywords = (
        r"\b(mueve|mover|avanza|avanzar|retrocede|retroceder|gira|girar|turn|move|forward|backward|left|right)\b"
    )
    if re.search(move_keywords, text):
        return "Move_robot"

    return None


def _extract_robot_name(user_input: str) -> str:
    text = user_input.lower()
    patterns = [
        r"\b(robot\s*\d+[\w-]*)\b",
        r"\b(turtlebot\s*\d+[\w-]*)\b",
        r"\b(tb\s*\d+[\w-]*)\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).replace(" ", "")

    return ""


def _extract_robot_name_with_llm(llm, user_input: str) -> str:
    prompt_text = (
        "Extrae solo el nombre del robot mencionado en el mensaje. "
        "Responde únicamente con el nombre exacto del robot o con NONE si no hay un robot específico.\n\n"
        f"Mensaje: {user_input}"
    )

    try:
        result = llm.invoke(prompt_text)
        robot_name = getattr(result, "content", str(result)).strip()
        if not robot_name or robot_name.upper() == "NONE":
            return ""

        robot_name = robot_name.strip().strip(". ,;:!\"'[]{}()")
        return robot_name.replace(" ", "")
    except Exception as e:
        print(f"Error extrayendo nombre de robot con LLM: {e}")
        return ""


def _extract_number(user_input: str) -> float | None:
    match = re.search(r"-?\d+(?:[\.,]\d+)?", user_input)
    if not match:
        return None

    return float(match.group(0).replace(",", "."))


def _extract_movement_request(user_input: str):
    text = user_input.lower()
    robot_name = _extract_robot_name(text)
    robot_specified = bool(robot_name)
    magnitude = _extract_number(text)
    linear_x = 0.0
    linear_y = 0.0
    angular_z = 0.0

    if re.search(r"\b(izquierda|left|gira\s+izquierda|turn\s+left)\b", text):
        angular_z = abs(magnitude) if magnitude is not None else 0.5
    elif re.search(r"\b(derecha|right|gira\s+derecha|turn\s+right)\b", text):
        angular_z = -(abs(magnitude) if magnitude is not None else 0.5)
    elif re.search(r"\b(atr[áa]s|retrocede|backward|backwards)\b", text):
        linear_x = -(abs(magnitude) if magnitude is not None else 0.2)
    elif re.search(r"\b(adelante|avanza|forward)\b", text):
        linear_x = abs(magnitude) if magnitude is not None else 0.2

    if abs(linear_x) > 2.0:
        linear_x = 2.0 if linear_x > 0 else -2.0

    if abs(angular_z) > 3.14:
        angular_z = 3.14 if angular_z > 0 else -3.14

    return {
        "robot_specified": robot_specified,
        "robot_name": robot_name,
        "linear_x": linear_x,
        "linear_y": linear_y,
        "angular_z": angular_z,
        "movement_description": user_input.strip(),
    }


def _extract_info_request(user_input: str):
    text = user_input.lower()
    target_name = ""

    match = re.search(r"(/[^\s,.;]+)", text)
    if match:
        target_name = match.group(1)
    else:
        words_after_keywords = re.search(
            r"(?:info(?:rmación)?|estado|diagn[oó]stico|sobre)\s+(?:del\s+|de\s+|la\s+|el\s+)?(.+)$",
            text,
        )
        if words_after_keywords:
            target_name = words_after_keywords.group(1).strip().split()[0]

    if any(keyword in text for keyword in ["tópico", "topico", "topic", "topics"]):
        info_type = "topic_info"
    elif any(keyword in text for keyword in ["nodo", "node", "nodos"]):
        info_type = "node_info"
    elif any(keyword in text for keyword in ["servicio", "service", "servicios"]):
        info_type = "service_info"
    elif any(keyword in text for keyword in ["mensaje", "msg", "tipo de mensaje"]):
        info_type = "message_type"
    else:
        info_type = "general_info"

    return {"info_type": info_type, "target_name": target_name}


def _extract_service_request(user_input: str):
    text = user_input.lower()
    service_name = ""

    match = re.search(r"(/[^\s,.;]+)", text)
    if match:
        service_name = match.group(1)
    else:
        words_after_keywords = re.search(
            r"(?:servicio|service)\s+(?:del\s+|de\s+|la\s+|el\s+)?(.+)$",
            text,
        )
        if words_after_keywords:
            service_name = words_after_keywords.group(1).strip().split()[0]

    return {
        "service_name": service_name,
        "service_type": "",
        "parameters": "",
    }


def _is_image_attachment(mime_type: str | None, file_base64: str | None) -> bool:
    return bool(mime_type and mime_type.startswith("image/") and file_base64)


def _is_quota_error(error: Exception) -> bool:
    error_text = str(error).lower()
    return "429" in error_text or "quota" in error_text or "rate limit" in error_text


def _analyze_rqt_graph_image(api_key: str, caption: str, mime_type: str, file_base64: str) -> str:
    configure = getattr(genai, "configure")
    generative_model = getattr(genai, "GenerativeModel")

    configure(api_key=api_key)
    model_candidates = [
        model_name.strip()
        for model_name in os.getenv(
            "ROSLINE_IMAGE_MODELS",
            "gemini-2.5-flash,gemini-3.0-Flash",
        ).split(",")
        if model_name.strip()
    ]

    prompt = (
        "Analiza esta imagen como si fuera una captura de rqt_graph de ROS 2. "
        "Identifica los nodos visibles, los tópicos, quién publica y quién suscribe, "
        "y resume la arquitectura general del grafo. "
        "Si detectas relaciones que sugieran un flujo de datos importante, explícalas. "
        "Si la imagen no parece ser un rqt_graph, dilo claramente y describe lo que sí ves. "
        "Responde en español, sin Markdown, con frases breves y concretas."
    )

    if caption:
        prompt += f"\n\nContexto adicional del usuario: {caption}"

    image_bytes = base64.b64decode(file_base64)
    last_error: Exception | None = None

    for model_name in model_candidates:
        try:
            model = generative_model(model_name)
            response = model.generate_content(
                [
                    prompt,
                    {"mime_type": mime_type, "data": image_bytes},
                ]
            )

            reply = (getattr(response, "text", "") or "").strip()
            if reply:
                return reply
        except Exception as error:
            last_error = error
            if not _is_quota_error(error):
                raise

    if last_error is not None and _is_quota_error(last_error):
        return (
            "No pude analizar la imagen porque se agotó la cuota del modelo de visión. "
            "Prueba de nuevo en unos minutos o cambia la variable ROSLINE_IMAGE_MODELS para usar otro modelo."
        )

    return "No pude interpretar la imagen adjunta. Si quieres, reenvíala con más resolución o una captura más centrada del rqt_graph."


@cbv(chat_webservice_api_router)
class ChatWebService:
    # --- v1.0: Chat con memoria en sesión ---
    @chat_webservice_api_router.post("/api/chat_v1.0")
    async def chat_with_memory(self, request: ChatRequestDTO):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            api_key = input("Por favor, ingrese su API KEY de Google (GOOGLE_API_KEY): ")
            os.environ["GOOGLE_API_KEY"] = api_key

        # Modelo y prompt del sistema
        llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")

        system_prompt = """ROL: ROSLine — asistente conversacional para controlar y consultar robots ROS 2.

    TAREA: interpreta mensajes del usuario y responde de forma clara y breve. Para órdenes operativas, extrae intención y parámetros; no inventes comandos ni devuelvas líneas de CLI.

    RESPUESTA: máximo 2–3 frases en texto plano. Si es primera interacción, saluda y pide el nombre. No uses Markdown. Si dudas, pide aclaración.
    """


        # Construcción de historial y prompt como texto
        history_text = _history_as_text(request.user_id, _history_window_size)
        user_input = request.message
        _append_message(request.user_id, "human", user_input)

        prompt_text = (
            f"{system_prompt}\n\n"
            f"Historial:\n{history_text}\n\n"
            f"Usuario: {user_input}\n"
            f"Asistente:"
        )

        # Respuesta final directa del modelo
        result = llm.invoke(prompt_text)
        reply = getattr(result, "content", str(result))
        _append_message(request.user_id, "ai", reply)

        return {
            "reply": reply,
        }

    # --- v1.1: Clasificación de intención + extracción y registro de distribuidor ---
    @chat_webservice_api_router.post("/api/chat_v1.1")
    async def chat_with_structure_output(self, request: ChatRequestDTO):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            api_key = input("Por favor, ingrese su API KEY de Google (GOOGLE_API_KEY): ")
            os.environ["GOOGLE_API_KEY"] = api_key

        # Modelo base
        llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")

        has_image_attachment = _is_image_attachment(request.mime_type, request.file_base64)
        user_input = request.message.strip() if request.message else ""

        if has_image_attachment:
            try:
                reply = _analyze_rqt_graph_image(
                    api_key=api_key,
                    caption=user_input,
                    mime_type=request.mime_type or "image/*",
                    file_base64=request.file_base64 or "",
                )
                history_input = user_input or "Imagen de rqt_graph adjunta"
                _append_message(request.user_id, "human", f"{history_input} [Archivo adjunto: {request.mime_type}]")
                _append_message(request.user_id, "ai", reply)
                return {
                    "userintention": "Other",
                    "analysis_type": "rqt_graph_image",
                    "reply": reply,
                }
            except Exception as e:
                fallback_reply = (
                    "No pude analizar la imagen adjunta. "
                    f"Error: {str(e)}"
                )
                _append_message(request.user_id, "human", f"{user_input} [Archivo adjunto: {request.mime_type}]")
                _append_message(request.user_id, "ai", fallback_reply)
                return {
                    "userintention": "Other",
                    "analysis_type": "rqt_graph_image",
                    "reply": fallback_reply,
                }

        # Registrar el mensaje actual en memoria y construir historial
        if request.mime_type and request.file_base64:
            user_input += f" [Archivo adjunto: {request.mime_type}]"

        _append_message(request.user_id, "human", user_input)
        history_text = _history_as_text(request.user_id, _history_window_size)

        direct_intention = _detect_direct_intention(user_input)
        if direct_intention:
            user_intention = direct_intention
        else:
            user_intention = None

        # Esquema de intención + clasificador estructurado
        intention_schema = {
            "title": "UserIntention",
            "description": "Clasifica la intención del mensaje del usuario relacionado con robótica y ROS 2.",
            "type": "object",
            "properties": {
                "userintention": {
                    "type": "string",
                    "enum": [
                        "List_topics",
                        "List_nodes",
                        "List_services",
                        "Get_info",
                        "Move_robot",
                        "Stop_robot",
                        "Call_service",
                        "Query_state",
                        "Other",
                    ],
                }
            },
            "required": ["userintention"],
            "additionalProperties": False,
        }

        model_with_structure = llm.with_structured_output(intention_schema)

        # Clasificación de intención (prompt plano)
        classify_text = (
            "Eres un clasificador especializado en robótica y ROS 2. Lee la conversación y clasifica la intención "
            "estrictamente en una de las etiquetas: "
            "'List_topics', 'List_nodes', 'List_services', 'Get_info', 'Move_robot', 'Stop_robot', "
            "'Call_service', 'Query_state' u 'Other'. "
            "Usa 'List_topics' cuando el usuario pide listar los tópicos activos. "
            "Usa 'List_nodes' cuando quiere ver los nodos activos. "
            "Usa 'List_services' cuando solicita ver los servicios disponibles. "
            "Usa 'Get_info' cuando pide información sobre un tópico, nodo o parámetro específico. "
            "Usa 'Move_robot' cuando da una orden de movimiento, por ejemplo avanzar, girar o desplazarse a una posición. "
            "Usa 'Stop_robot' cuando solicita detener el robot o cancelar un movimiento. "
            "Usa 'Call_service' cuando el usuario pide ejecutar un servicio o acción de ROS 2. "
            "Usa 'Query_state' cuando pregunta por el estado del robot, como posición, batería o diagnóstico. "
            "En cualquier otro caso usa 'Other'.\n\n"
            f"Historial:\n{history_text}\n\n"
            f"Último mensaje del usuario: {user_input}"
        )


        if user_intention is None:
            result = model_with_structure.invoke(classify_text)
            print(result)
            if isinstance(result, list):
                first_result = result[0]
                user_intention = first_result.get("args", {}).get("userintention") if isinstance(first_result, dict) else getattr(first_result, "userintention", None)
            else:
                user_intention = getattr(result, "userintention", None)

        if user_intention == "Other":
            # Rama 'Other': respuesta general con memoria y conocimiento de ROS 2
            system_prompt = """ROLE:
                ROSLine, un asistente inteligente especializado en robótica y ROS 2 que actúa como
                un compañero de apoyo para estudiantes, desarrolladores e investigadores. Es un experto
                en comunicación entre robots y sistemas ROS 2, y está diseñado para conversar, enseñar y
                guiar sobre temas de robótica moderna y computación distribuida.

                TASK:
                Mantener una conversación amigable con el usuario sobre robótica y ROS 2. Si es la primera interacción,
                saluda y pregunta el nombre del usuario, luego preséntate brevemente como ROSLine.
                En conversaciones posteriores, responde preguntas sobre ROS 2 o robótica de manera educativa y clara,
                compartiendo conocimiento técnico útil y actualizado.

                CONOCIMIENTO DE ROS 2 Y ROBÓTICA:
                - ROS 2 (Robot Operating System 2): framework de código abierto para desarrollo robótico
                - Nodos: unidades básicas de ejecución que comunican datos
                - Tópicos: canales de comunicación entre nodos (publicadores y suscriptores)
                - Servicios y Acciones: permiten solicitudes y ejecuciones de tareas entre nodos
                - Parámetros: variables configurables en tiempo de ejecución
                - Tipos de mensajes: geometry_msgs, sensor_msgs, nav_msgs, std_msgs, etc.
                - Comunicación: basada en DDS (Data Distribution Service)
                - Simulación: Gazebo, Webots, Ignition o RViz para visualización
                - Control: mensajes tipo Twist, odometría, sensores y controladores PID
                - Middleware: permite la interoperabilidad entre nodos distribuidos
                - Integración con IA: visión por computadora, PLN y RL integrados con ROS 2
                - Plataformas comunes: TurtleBot3, Jetson, ESP32 con micro-ROS, Raspberry Pi

                CAPACIDADES PRINCIPALES:
                1. Explicar conceptos de ROS 2 de forma clara y sencilla
                2. Guiar al usuario sobre cómo ejecutar comandos o estructuras de ROS 2
                3. Aclarar dudas sobre tópicos, nodos, mensajes o arquitecturas
                4. Dar ejemplos educativos de comandos, flujos o integraciones
                5. Orientar sobre buenas prácticas de desarrollo y depuración
                6. Conversar sobre tendencias y aplicaciones de la robótica moderna

                ESTILO DE COMUNICACIÓN:
                - Técnico pero amigable
                - Educativo, estructurado y con ejemplos prácticos
                - Siempre dispuesto a enseñar y orientar en temas de robótica
                - Respuestas claras, útiles y aplicables

                CONSTRAINTS:
                - No inventar comandos ni sintaxis de ROS 2
                - Basar las respuestas en conocimiento real y documentado de ROS 2
                - Mantener un tono profesional y claro
                - Hablar en primera persona como "ROSLine"

                OUTPUT_POLICY:
                - Para saludos iniciales: saluda, pregunta el nombre y preséntate brevemente
                - Para preguntas técnicas: responde de forma explicativa en 3–5 frases
                - Mantén las respuestas informativas pero concisas
                - Si no sabes algo específico, dilo y sugiere cómo o dónde podría obtener más información

                INSTRUCCIONES ADICIONALES:
                - Solo saluda y pide el nombre si es la primera interacción del usuario
                - Para conversaciones existentes, enfócate en responder sobre ROS 2 o robótica
                - Sé educativo y comparte conocimiento útil y actualizado
                - NO uses formato Markdown (**, *, _, etc.) ya que no funciona en WhatsApp
                - Usa texto plano sin formato especial
            """


            # Usar memoria propia y construir prompt plano
            history_text = _history_as_text(request.user_id, _history_window_size)
            user_input = request.message

            prompt_text = (
                f"{system_prompt}\n\n"
                f"Historial:\n{history_text}\n\n"
                f"Usuario: {user_input}\n"
                f"Asistente:"
            )

            ai_result = llm.invoke(prompt_text)
            reply = getattr(ai_result, "content", str(ai_result))
            _append_message(request.user_id, "ai", reply)
            print(ai_result)
            return {
                "userintention": "Other",
                "reply": reply,
            }
            
        elif user_intention == "List_topics":
            # Rama 'List_topics': Mostrar los tópicos ROS 2 actualmente activos
            user_input = request.message
            
            # Ejecutar comando ROS usando el agente
            ros_agent = _get_ros_agent()
            if ros_agent:
                try:
                    topics_output = ros_agent.list_topics()
                    reply_text = (
                        "Tópicos ROS 2 activos:\n"
                        f"{topics_output if topics_output else 'No se pudieron obtener los tópicos'}\n\n"
                        "¿Necesitas información específica de algún tópico?"
                    )
                    status = "success"
                except Exception as e:
                    reply_text = (
                        "Error al ejecutar el comando ROS:\n"
                        f"ros2 topic list\n\n"
                        f"Error: {str(e)}"
                    )
                    status = "error"
            else:
                reply_text = (
                    "El agente ROS no está disponible.\n"
                    "Comando que se ejecutaría: ros2 topic list\n\n"
                    "Verifica que ROS 2 esté configurado correctamente."
                )
                status = "ros_unavailable"
            
            _append_message(request.user_id, "ai", reply_text)
            return {
                "userintention": "List_topics",
                "status": status,
                "ros_command": "ros2 topic list",
                "reply": reply_text,
            }

        elif user_intention == "List_nodes":
            # Rama 'List_nodes': Mostrar los nodos ROS 2 actualmente activos
            user_input = request.message
            
            # Ejecutar comando ROS usando el agente
            ros_agent = _get_ros_agent()
            if ros_agent:
                try:
                    nodes_output = ros_agent.list_nodes()
                    reply_text = (
                        "Nodos ROS 2 activos:\n"
                        f"{nodes_output if nodes_output else 'No se pudieron obtener los nodos'}\n\n"
                        "¿Necesitas información específica de algún nodo?"
                    )
                    status = "success"
                except Exception as e:
                    reply_text = (
                        "Error al ejecutar el comando ROS:\n"
                        f"ros2 node list\n\n"
                        f"Error: {str(e)}"
                    )
                    status = "error"
            else:
                reply_text = (
                    "El agente ROS no está disponible.\n"
                    "Comando que se ejecutaría: ros2 node list\n\n"
                    "Verifica que ROS 2 esté configurado correctamente."
                )
                status = "ros_unavailable"
            
            _append_message(request.user_id, "ai", reply_text)
            return {
                "userintention": "List_nodes",
                "status": status,
                "ros_command": "ros2 node list",
                "reply": reply_text,
            }

        elif user_intention == "List_services":
            # Rama 'List_services': Mostrar los servicios ROS 2 disponibles
            user_input = request.message
            
            # Ejecutar comando ROS usando el agente
            ros_agent = _get_ros_agent()
            if ros_agent:
                try:
                    services_output = ros_agent.list_services()
                    reply_text = (
                        "Servicios ROS 2 disponibles:\n"
                        f"{services_output if services_output else 'No se pudieron obtener los servicios'}\n\n"
                        "¿Quieres llamar algún servicio específico?"
                    )
                    status = "success"
                except Exception as e:
                    reply_text = (
                        "Error al ejecutar el comando ROS:\n"
                        f"ros2 service list\n\n"
                        f"Error: {str(e)}"
                    )
                    status = "error"
            else:
                reply_text = (
                    "El agente ROS no está disponible.\n"
                    "Comando que se ejecutaría: ros2 service list\n\n"
                    "Verifica que ROS 2 esté configurado correctamente."
                )
                status = "ros_unavailable"
            
            _append_message(request.user_id, "ai", reply_text)
            return {
                "userintention": "List_services",
                "status": status,
                "ros_command": "ros2 service list",
                "reply": reply_text,
            }

        elif user_intention == "Get_info":
            # Rama 'Get_info': Obtener información específica sobre tópicos, nodos o servicios
            user_input = request.message
            info_data = _extract_info_request(user_input)
            info_type = info_data.get("info_type", "general_info")
            target_name = info_data.get("target_name", "")

            ros_agent = _get_ros_agent()
            if ros_agent and target_name and info_type in ["topic_info", "node_info", "service_info"]:
                try:
                    ros_type = info_type.replace("_info", "")
                    info_output = ros_agent.get_info(ros_type, target_name)

                    reply_text = (
                        f"Información sobre {target_name}:\n"
                        f"{info_output if info_output else 'No se pudo obtener la información'}\n\n"
                        "¿Necesitas más detalles?"
                    )
                    ros_command = f"ros2 {ros_type} info {target_name}"
                    status = "success"
                except Exception as e:
                    reply_text = (
                        f"Error al obtener información sobre {target_name}:\n"
                        f"Error: {str(e)}"
                    )
                    ros_command = f"ros2 {info_type.replace('_info', '')} info {target_name}"
                    status = "error"
            else:
                reply_text = (
                    "Necesito más información específica sobre qué quieres consultar.\n"
                    "Ejemplo: 'información del tópico /cmd_vel' o 'info del nodo /turtlesim'"
                )
                ros_command = "ros2 --help"
                status = "need_more_info"
            
            _append_message(request.user_id, "ai", reply_text)
            return {
                "userintention": "Get_info",
                "status": status,
                "ros_command": ros_command,
                "reply": reply_text,
            }

        elif user_intention == "Move_robot":
            # Rama 'Move_robot': Generar comandos de movimiento para el robot
            user_input = request.message
            movement_data = _extract_movement_request(user_input)
            robot_specified = movement_data["robot_specified"]
            robot_name = movement_data["robot_name"]
            linear_x = movement_data["linear_x"]
            linear_y = movement_data["linear_y"]
            angular_z = movement_data["angular_z"]
            description = movement_data["movement_description"]

            if not robot_name:
                robot_name = _extract_robot_name_with_llm(llm, user_input)
                robot_specified = bool(robot_name)

            cmd_vel_topic = "/cmd_vel"
            topic_status = "default"

            if robot_specified and robot_name:
                ros_agent = _get_ros_agent()
                if ros_agent:
                    try:
                        topics_output = ros_agent.list_topics()
                        if topics_output and not topics_output.startswith("Error"):
                            for topic in topics_output.split("\n"):
                                topic = topic.strip()
                                if robot_name.lower() in topic.lower() and "cmd_vel" in topic.lower():
                                    cmd_vel_topic = topic
                                    topic_status = "found_specific"
                                    break
                            else:
                                topic_status = "robot_not_found"
                        else:
                            topic_status = "topics_unavailable"
                    except Exception as e:
                        print(f"Error obteniendo tópicos: {e}")
                        topic_status = "topics_error"
                else:
                    topic_status = "ros_unavailable"
            
            # Ejecutar movimiento usando el agente ROS con el tópico determinado
            ros_agent = _get_ros_agent()
            if ros_agent:
                try:
                    ros_agent.move_robot(
                        linear_x=linear_x,
                        linear_y=linear_y, 
                        linear_z=0.0,
                        angular_x=0.0,
                        angular_y=0.0,
                        angular_z=angular_z,
                        topic=cmd_vel_topic.lstrip('/')  # Remover barra inicial si existe
                    )
                    
                    twist_message = {
                        "linear": {"x": linear_x, "y": linear_y, "z": 0.0},
                        "angular": {"x": 0.0, "y": 0.0, "z": angular_z}
                    }
                    
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
                    
                except Exception as e:
                    twist_message = {"linear": {"x": 0.0, "y": 0.0, "z": 0.0}, "angular": {"x": 0.0, "y": 0.0, "z": 0.0}}
                    reply_text = (
                        f"❌ Error al ejecutar movimiento: {description}\n"
                        f"Tópico: {cmd_vel_topic}\n"
                        f"Error: {str(e)}"
                    )
                    status = "error"
            else:
                twist_message = {"linear": {"x": 0.0, "y": 0.0, "z": 0.0}, "angular": {"x": 0.0, "y": 0.0, "z": 0.0}}
                reply_text = (
                    "⚠️ Agente ROS no disponible\n"
                    f"Movimiento solicitado: {description}\n"
                    f"Tópico: {cmd_vel_topic}"
                )
                status = "ros_unavailable"
            
            ros_command = f"ros2 topic pub --once {cmd_vel_topic} geometry_msgs/msg/Twist \"{{linear: {{x: {linear_x}, y: {linear_y}, z: 0.0}}, angular: {{x: 0.0, y: 0.0, z: {angular_z}}}}}\""
            
            _append_message(request.user_id, "ai", reply_text)
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

        elif user_intention == "Stop_robot":
            # Rama 'Stop_robot': Detener todos los movimientos del robot
            user_input = request.message
            robot_name = _extract_robot_name(user_input)
            if not robot_name:
                robot_name = _extract_robot_name_with_llm(llm, user_input)
            robot_specified = bool(robot_name)

            cmd_vel_topic = "/cmd_vel"
            topic_status = "default"

            if robot_specified:
                ros_agent = _get_ros_agent()
                if ros_agent:
                    try:
                        topics_output = ros_agent.list_topics()
                        if topics_output and not topics_output.startswith("Error"):
                            for topic in topics_output.split("\n"):
                                topic = topic.strip()
                                if robot_name.lower() in topic.lower() and "cmd_vel" in topic.lower():
                                    cmd_vel_topic = topic
                                    topic_status = "found_specific"
                                    break
                            else:
                                topic_status = "robot_not_found"
                        else:
                            topic_status = "topics_unavailable"
                    except Exception as e:
                        print(f"Error obteniendo tópicos: {e}")
                        topic_status = "topics_error"
                else:
                    topic_status = "ros_unavailable"
            
            # Ejecutar comando de parada usando el agente ROS con el tópico determinado
            robot_info = f" {robot_name}" if robot_specified and robot_name else ""
            ros_agent = _get_ros_agent()
            if ros_agent:
                try:
                    ros_agent.move_robot(
                        linear_x=0.0,
                        linear_y=0.0,
                        linear_z=0.0,
                        angular_x=0.0,
                        angular_y=0.0,
                        angular_z=0.0,
                        topic=cmd_vel_topic.lstrip('/')  # Remover barra inicial si existe
                    )
                    
                    robot_info = f" {robot_name}" if robot_specified and robot_name else ""
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
                    
                except Exception as e:
                    reply_text = (
                        f"❌ Error al detener el robot{robot_info}\n"
                        f"Tópico: {cmd_vel_topic}\n"
                        f"Error: {str(e)}"
                    )
                    status = "error"
            else:
                robot_info = f" {robot_name}" if robot_specified and robot_name else ""
                reply_text = (
                    "⚠️ Agente ROS no disponible\n"
                    f"Robot solicitado: {robot_name if robot_name else 'robot por defecto'}\n"
                    f"Tópico: {cmd_vel_topic}"
                )
                status = "ros_unavailable"
            
            twist_message = {
                "linear": {"x": 0.0, "y": 0.0, "z": 0.0},
                "angular": {"x": 0.0, "y": 0.0, "z": 0.0}
            }
            
            ros_command = f"ros2 topic pub --once {cmd_vel_topic} geometry_msgs/msg/Twist \"{{linear: {{x: 0.0, y: 0.0, z: 0.0}}, angular: {{x: 0.0, y: 0.0, z: 0.0}}}}\""
            
            _append_message(request.user_id, "ai", reply_text)
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

        elif user_intention == "Call_service":
            # Rama 'Call_service': Llamar a un servicio específico de ROS 2
            user_input = request.message
            service_data = _extract_service_request(user_input)
            service_name = service_data.get("service_name", "")
            service_type = service_data.get("service_type", "")
            parameters = service_data.get("parameters", "")

            ros_agent = _get_ros_agent()
            if ros_agent and service_name:
                try:
                    reply_text = (
                        f"🔧 Preparando llamada al servicio: {service_name}\n"
                        f"Tipo: {service_type if service_type else 'No especificado'}\n"
                        f"Parámetros: {parameters if parameters else 'Ninguno'}\n\n"
                        "Nota: La llamada al servicio requiere implementación específica del tipo de servicio."
                    )
                    ros_command = f"ros2 service call {service_name} {service_type} \"{parameters}\"" if parameters else f"ros2 service call {service_name} {service_type} {{}}"
                    status = "partial_implementation"

                except Exception as e:
                    reply_text = (
                        f"❌ Error al preparar llamada al servicio: {service_name}\n"
                        f"Error: {str(e)}"
                    )
                    ros_command = f"ros2 service call {service_name} {service_type}"
                    status = "error"
            elif service_name:
                reply_text = (
                    f"⚠️ Agente ROS no disponible\n"
                    f"Servicio solicitado: {service_name}\n"
                    "Verifica que ROS 2 esté configurado correctamente."
                )
                ros_command = f"ros2 service call {service_name} {service_type}"
                status = "ros_unavailable"
            else:
                reply_text = (
                    "❓ No pude identificar el servicio específico.\n"
                    "Mostrando servicios disponibles..."
                )
                if ros_agent:
                    try:
                        services_output = ros_agent.list_services()
                        reply_text += f"\n\nServicios disponibles:\n{services_output}"
                    except:
                        pass
                ros_command = "ros2 service list"
                status = "service_not_found"
            
            _append_message(request.user_id, "ai", reply_text)
            return {
                "userintention": "Call_service",
                "status": status,
                "ros_command": ros_command,
                "reply": reply_text,
            }

        elif user_intention == "Query_state":
            # Rama 'Query_state': Consultar el estado del robot o sistema
            user_input = request.message
            
            # Respuesta fija como solicitado
            reply_text = (
                "📊 Consulta de estado del robot\n"
                "Esta funcionalidad está por implementar.\n\n"
                "Próximamente podrás consultar:\n"
                "- Posición y odometría\n"
                "- Estado de batería\n"
                "- Datos de sensores\n"
                "- Diagnósticos del sistema\n"
                "- Transformadas (TF)"
            )
            
            _append_message(request.user_id, "ai", reply_text)
            return {
                "userintention": "Query_state",
                "status": "not_implemented",
                "ros_command": "# Por implementar",
                "reply": reply_text,
            }


        # Si no se reconoce la intención, manejo por defecto
        else:
            # Respuesta por defecto para intenciones no manejadas
            user_input = request.message
            history_text = _history_as_text(request.user_id)
            
            default_text = (
                "ROLE: ROSLine, asistente especializado en ROS 2.\n"
                "El usuario ha enviado una solicitud que no pude clasificar correctamente. "
                "Responde de manera amigable y sugiere las capacidades disponibles.\n\n"
                f"Historial:\n{history_text}\n\n"
                f"Usuario: {user_input}\n"
                f"Asistente:"
            )
            
            reply_obj = llm.invoke(default_text)
            reply_text = getattr(reply_obj, "content", str(reply_obj))
            _append_message(request.user_id, "ai", reply_text)
            
            return {
                "userintention": user_intention or "Unknown",
                "status": "unhandled",
                "reply": reply_text,
            }
