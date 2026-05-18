from fastapi import APIRouter, HTTPException
from fastapi_utils.cbv import cbv

import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

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


def _history_as_text(user_id: str) -> str:
    lines = []
    for msg in _get_history(user_id):
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

        system_prompt = """ROL:
            ROSLine, un asistente conversacional inteligente diseñado para interactuar
            con sistemas ROS 2 mediante lenguaje natural a través de WhatsApp. Actúa como
            una interfaz entre el usuario y ROS 2, capaz de interpretar mensajes,
            generar comandos ROS 2 y ofrecer retroalimentación clara sobre el estado del robot.

            TAREA:
            Mantener una conversación amigable y profesional con el usuario sobre ROS 2.
            Siempre comenzar con un saludo breve y pedir el nombre del usuario. 
            Después del saludo, presentarte brevemente como ROSLine en 1–2 frases, 
            explicando que ayudas a controlar y monitorear robots ROS 2 mediante chat.
            Luego, interpretar y responder de forma clara las solicitudes del usuario 
            usando el contexto disponible de ROS 2 o las acciones compatibles.

            CONTEXTO:
            ROSLine está pensado para desarrolladores, estudiantes y entusiastas de la robótica 
            que desean manejar robots ROS 2 utilizando lenguaje natural a través de WhatsApp.
            Su objetivo es hacer la interacción con robots más intuitiva, accesible e inteligente.

            Capacidades principales:
            1. Consultas del sistema ROS 2:
            - Listar tópicos, nodos y servicios activos.
            - Obtener información sobre tipos de mensajes o parámetros.
            - Consultar el estado del robot o diagnósticos del sistema.

            2. Ejecución de comandos:
            - Enviar comandos de velocidad o movimiento mediante tópicos como /cmd_vel.
            - Activar acciones y servicios de ROS 2.
            - Realizar tareas como avanzar, girar o detener al robot.

            3. Interpretación en lenguaje natural:
            - Entender lenguaje humano y traducirlo en comandos ROS 2 estructurados.
            - Reconocer contexto (tópicos, nodos, direcciones, distancias, etc.).
            - Dar confirmaciones o retroalimentación tras ejecutar comandos.

            4. Capa de integración:
            - Comunicarse con la API de Gemini para razonamiento y comprensión del lenguaje.
            - Conectar la salida con un backend capaz de ejecutar comandos ROS 2 reales.

            Usuarios objetivo:
            - Desarrolladores y roboticistas que trabajan con ROS 2.
            - Estudiantes que aprenden sobre robótica e inteligencia artificial.
            - Investigadores interesados en interacción humano-robot.

            Propuesta de valor:
            - Controla tu robot usando lenguaje natural desde WhatsApp.
            - Simplifica el uso de ROS 2 sin necesidad de una terminal.
            - Integra razonamiento basado en IA con control robótico real.
            - Convierte ROS 2 en una experiencia más conversacional y accesible.

            Estilo de comunicación:
            - Amigable, preciso y técnicamente claro.
            - Siempre útil, conciso y profesional.
            - Cercano y motivador, enfocado en robótica y ROS 2.

            RESTRICCIONES:
            - Nunca inventar comandos o acciones de ROS 2 que no existan.
            - Solo proporcionar información basada en funcionalidades reales de ROS 2.
            - Mantener las respuestas cortas y relevantes al contexto.
            - Hablar siempre en primera persona como "ROSLine".

            POLÍTICA DE RESPUESTA:
            - Responder en 2–4 frases como máximo.
            - Siempre comenzar con un saludo y pedir el nombre del usuario.
            - Después del saludo, presentarte brevemente como el asistente ROSLine.
            - Luego interpretar y responder la solicitud relacionada con ROS 2.
            - Si no estás seguro de un comando, indícalo claramente en lugar de inventar.

            INSTRUCCIONES ADICIONALES:
            - Siempre saluda primero y pide el nombre del usuario.
            - Mantén todos los mensajes claros, breves y enfocados en ROS 2.
            - Usa un tono profesional pero conversacional.
            - NO uses formato Markdown (**, *, _, etc.) ya que WhatsApp no lo soporta.
            - Usa texto plano únicamente.
            """


        # Construcción de historial y prompt como texto
        history_text = _history_as_text(request.user_id)
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

        # Registrar el mensaje actual en memoria y construir historial
        user_input = request.message
        
        # Agregar información sobre archivo si está presente
        if request.mime_type and request.file_base64:
            user_input += f" [Archivo adjunto: {request.mime_type}]"
        
        _append_message(request.user_id, "human", user_input)
        history_text = _history_as_text(request.user_id)

        direct_intention = _detect_direct_intention(user_input)
        if direct_intention:
            user_intention = direct_intention
        else:
            user_intention = None

        # Esquema de intención + clasificador estructurado
        intention_schema = {
            "title": "UserIntention",
            "description": (
                "Clasifica la intención del mensaje del usuario relacionado con robótica y ROS 2. "
                "Devuelve solo una de las etiquetas permitidas."
            ),
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
                        "Other"
                    ],
                    "description": (
                        "'List_topics': cuando el usuario solicita listar los tópicos activos de ROS 2. "
                        "'List_nodes': cuando el usuario quiere conocer los nodos actualmente activos. "
                        "'List_services': cuando el usuario desea ver los servicios disponibles. "
                        "'Get_info': cuando el usuario pide información sobre un tópico, nodo o parámetro específico. "
                        "'Move_robot': cuando el usuario da una orden de movimiento (ej. avanzar, girar, moverse hacia un punto). "
                        "'Stop_robot': cuando el usuario solicita detener el movimiento o cancelar una acción. "
                        "'Call_service': cuando el usuario pide ejecutar un servicio o acción de ROS 2. "
                        "'Query_state': cuando el usuario pregunta por el estado del robot (batería, posición, diagnóstico, etc.). "
                        "'Other': conversación casual o tema no relacionado directamente con ROS 2."
                    ),
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
            user_intention = result[0]["args"].get("userintention")

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
            history_text = _history_as_text(request.user_id)
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
            
            # Extraer qué información específica quiere el usuario
            info_extraction_schema = {
                "title": "ROSInfoRequest",
                "description": "Extrae qué información específica de ROS 2 quiere el usuario",
                "type": "object",
                "properties": {
                    "info_type": {
                        "type": "string",
                        "enum": ["topic_info", "node_info", "service_info", "message_type", "general_info"],
                        "description": "Tipo de información solicitada"
                    },
                    "target_name": {
                        "type": "string", 
                        "description": "Nombre del tópico, nodo o servicio sobre el que quiere información"
                    }
                },
                "required": ["info_type"],
                "additionalProperties": False,
            }
            
            info_extractor = llm.with_structured_output(info_extraction_schema)
            extract_text = f"Extrae qué tipo de información ROS 2 solicita el usuario.\n\nMensaje: {user_input}"
            
            try:
                extracted = info_extractor.invoke(extract_text)
                info_data = extracted[0]["args"] if isinstance(extracted, list) else extracted
                
                info_type = info_data.get("info_type", "general_info")
                target_name = info_data.get("target_name", "")
                
                # Ejecutar comando ROS usando el agente
                ros_agent = _get_ros_agent()
                if ros_agent and target_name:
                    try:
                        if info_type in ["topic_info", "node_info", "service_info"]:
                            # Usar el método get_info del agente
                            ros_type = info_type.replace("_info", "")  # topic, node, service
                            info_output = ros_agent.get_info(ros_type, target_name)
                            
                            reply_text = (
                                f"Información sobre {target_name}:\n"
                                f"{info_output if info_output else 'No se pudo obtener la información'}\n\n"
                                "¿Necesitas más detalles?"
                            )
                            ros_command = f"ros2 {ros_type} info {target_name}"
                            status = "success"
                        else:
                            reply_text = (
                                f"Tipo de información no soportado: {info_type}\n"
                                "Tipos disponibles: topic_info, node_info, service_info"
                            )
                            ros_command = "ros2 --help"
                            status = "unsupported_type"
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
                
            except Exception as e:
                ros_command = "ros2 --help"
                reply_text = (
                    "Error al procesar la solicitud de información.\n"
                    "Intenta ser más específico sobre qué información necesitas."
                )
                status = "extraction_error"
            
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
            
            # Combinar detección de robot y parámetros de movimiento en una sola llamada
            combined_schema = {
                "title": "RobotMovementAnalysis",
                "description": "Analiza el mensaje para extraer robot específico y parámetros de movimiento",
                "type": "object",
                "properties": {
                    "robot_specified": {
                        "type": "boolean",
                        "description": "True si el usuario menciona un robot específico (ej: turtlebot1, robot2, etc.)"
                    },
                    "robot_name": {
                        "type": "string",
                        "description": "Nombre del robot especificado por el usuario"
                    },
                    "linear_x": {
                        "type": "number",
                        "description": "Velocidad lineal en X (adelante/atrás) en m/s. Positivo = adelante, Negativo = atrás"
                    },
                    "linear_y": {
                        "type": "number", 
                        "description": "Velocidad lineal en Y (izquierda/derecha) en m/s para robots omnidireccionales"
                    },
                    "angular_z": {
                        "type": "number",
                        "description": "Velocidad angular en Z (giro) en rad/s. Positivo = giro izquierda, Negativo = giro derecha"
                    },
                    "movement_description": {
                        "type": "string",
                        "description": "Descripción del movimiento solicitado"
                    }
                },
                "required": ["robot_specified", "linear_x", "angular_z", "movement_description"],
                "additionalProperties": False,
            }
            
            combined_extractor = llm.with_structured_output(combined_schema)
            extract_text = (
                "Analiza el mensaje del usuario y extrae:\n"
                "1. Si especifica un robot particular (nombres como 'turtlebot1', 'robot2', etc.)\n"
                "2. Los parámetros de movimiento para ROS 2\n\n"
                "Para movimientos:\n"
                "- Velocidades lineales entre -2.0 y 2.0 m/s\n"
                "- Velocidades angulares entre -3.14 y 3.14 rad/s\n"
                "- 'adelante/avanzar' = linear_x positivo\n"
                "- 'atrás/retroceder' = linear_x negativo\n"
                "- 'girar izquierda' = angular_z positivo\n"
                "- 'girar derecha' = angular_z negativo\n\n"
                f"Mensaje del usuario: {user_input}"
            )
            
            try:
                extracted = combined_extractor.invoke(extract_text)
                combined_data = extracted[0]["args"] if isinstance(extracted, list) else extracted
                
                robot_specified = combined_data.get("robot_specified", False)
                robot_name = combined_data.get("robot_name", "")
                linear_x = combined_data.get("linear_x", 0.0)
                linear_y = combined_data.get("linear_y", 0.0) 
                angular_z = combined_data.get("angular_z", 0.0)
                description = combined_data.get("movement_description", "Movimiento")
                
                # Determinar el tópico a usar
                cmd_vel_topic = "/cmd_vel"  # Valor por defecto
                topic_status = "default"
                
                if robot_specified and robot_name:
                    # Obtener lista de tópicos y buscar el correcto (solo una llamada más)
                    ros_agent = _get_ros_agent()
                    if ros_agent:
                        try:
                            topics_output = ros_agent.list_topics()
                            if topics_output and not topics_output.startswith("Error"):
                                # Análisis rápido de tópicos con Gemini
                                topic_analysis_schema = {
                                    "title": "TopicAnalysis",
                                    "description": "Encuentra el tópico cmd_vel del robot especificado",
                                    "type": "object",
                                    "properties": {
                                        "found_topic": {
                                            "type": "boolean",
                                            "description": "True si se encontró un tópico cmd_vel para el robot"
                                        },
                                        "topic_name": {
                                            "type": "string",
                                            "description": "Nombre completo del tópico encontrado"
                                        }
                                    },
                                    "required": ["found_topic"],
                                    "additionalProperties": False,
                                }
                                
                                topic_analyzer = llm.with_structured_output(topic_analysis_schema)
                                analysis_text = (
                                    f"Busca el tópico cmd_vel para '{robot_name}' en:\n{topics_output}\n"
                                    f"Patrones: /{robot_name}/cmd_vel, /{robot_name}_cmd_vel, etc."
                                )
                                
                                try:
                                    topic_analysis = topic_analyzer.invoke(analysis_text)
                                    analysis_data = topic_analysis[0]["args"] if isinstance(topic_analysis, list) else topic_analysis
                                    
                                    if analysis_data.get("found_topic", False) and analysis_data.get("topic_name", ""):
                                        cmd_vel_topic = analysis_data.get("topic_name", "/cmd_vel")
                                        topic_status = "found_specific"
                                    else:
                                        topic_status = "robot_not_found"
                                        
                                except Exception as e:
                                    print(f"Error en análisis de tópicos: {e}")
                                    topic_status = "analysis_error"
                            else:
                                topic_status = "topics_unavailable"
                        except Exception as e:
                            print(f"Error obteniendo tópicos: {e}")
                            topic_status = "topics_error"
                    else:
                        topic_status = "ros_unavailable"
                
            except Exception as e:
                print(f"Error en análisis combinado: {e}")
                robot_specified = False
                robot_name = ""
                linear_x = 0.0
                linear_y = 0.0
                angular_z = 0.0
                description = "Movimiento"
                topic_status = "extraction_error"
            
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
            
            # Detección optimizada de robot específico
            robot_detection_schema = {
                "title": "RobotStopAnalysis",
                "description": "Detecta si el usuario especifica un robot particular para detener",
                "type": "object",
                "properties": {
                    "robot_specified": {
                        "type": "boolean",
                        "description": "True si el usuario menciona un robot específico (ej: turtlebot1, robot2, etc.)"
                    },
                    "robot_name": {
                        "type": "string",
                        "description": "Nombre del robot especificado por el usuario"
                    }
                },
                "required": ["robot_specified"],
                "additionalProperties": False,
            }
            
            robot_detector = llm.with_structured_output(robot_detection_schema)
            detect_text = f"¿Especifica un robot particular para detener? Mensaje: {user_input}"
            
            try:
                robot_detection = robot_detector.invoke(detect_text)
                robot_data = robot_detection[0]["args"] if isinstance(robot_detection, list) else robot_detection
                
                robot_specified = robot_data.get("robot_specified", False)
                robot_name = robot_data.get("robot_name", "")
                
                # Determinar el tópico a usar
                cmd_vel_topic = "/cmd_vel"  # Valor por defecto
                topic_status = "default"
                
                if robot_specified and robot_name:
                    # Búsqueda rápida de tópico específico
                    ros_agent = _get_ros_agent()
                    if ros_agent:
                        try:
                            topics_output = ros_agent.list_topics()
                            if topics_output and not topics_output.startswith("Error"):
                                # Búsqueda simple de patrón
                                for topic in topics_output.split('\n'):
                                    topic = topic.strip()
                                    if robot_name.lower() in topic.lower() and 'cmd_vel' in topic.lower():
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
                
            except Exception as e:
                print(f"Error en detección de robot: {e}")
                robot_specified = False
                robot_name = ""
                topic_status = "detection_error"
            
            # Ejecutar comando de parada usando el agente ROS con el tópico determinado
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
            
            # Extraer información del servicio a llamar
            service_schema = {
                "title": "ServiceCall",
                "description": "Extrae información sobre el servicio ROS 2 a llamar",
                "type": "object",
                "properties": {
                    "service_name": {
                        "type": "string",
                        "description": "Nombre del servicio a llamar"
                    },
                    "service_type": {
                        "type": "string", 
                        "description": "Tipo del servicio si se menciona"
                    },
                    "parameters": {
                        "type": "string",
                        "description": "Parámetros o argumentos para el servicio"
                    }
                },
                "required": ["service_name"],
                "additionalProperties": False,
            }
            
            service_extractor = llm.with_structured_output(service_schema)
            extract_text = f"Extrae el nombre del servicio ROS 2 que el usuario quiere llamar.\n\nMensaje: {user_input}"
            
            try:
                extracted = service_extractor.invoke(extract_text)
                service_data = extracted[0]["args"] if isinstance(extracted, list) else extracted
                
                service_name = service_data.get("service_name", "")
                service_type = service_data.get("service_type", "")
                parameters = service_data.get("parameters", "")
                
                # Ejecutar llamada al servicio usando el agente ROS
                ros_agent = _get_ros_agent()
                if ros_agent and service_name:
                    try:
                        # Nota: El método call_service del agente requiere el tipo de servicio y request
                        # Por ahora solo mostramos que se intentaría llamar
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
                    # Usar el agente para listar servicios
                    if ros_agent:
                        try:
                            services_output = ros_agent.list_services()
                            reply_text += f"\n\nServicios disponibles:\n{services_output}"
                        except:
                            pass
                    ros_command = "ros2 service list"
                    status = "service_not_found"
                
            except Exception as e:
                ros_command = "ros2 service list"
                reply_text = (
                    "❌ Error al procesar la solicitud del servicio.\n"
                    "Mostrando servicios disponibles..."
                )
                status = "extraction_error"
            
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
