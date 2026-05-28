"""
Chat endpoints for ROSLine.

Classes:
    ChatWebService: Class that provides the endpoint routes.
"""

import os
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from dotenv import load_dotenv
from fastapi import APIRouter
from fastapi_utils.cbv import cbv
from langchain_google_genai import ChatGoogleGenerativeAI

from ros_line.endpoints.chat.context import (
    append_message as _append_message,
    get_ros_agent as _get_ros_agent,
    history_as_text as _history_as_text,
    history_window_size,
)
from ros_line.endpoints.chat.handlers import (
    handle_move_robot as _handle_move_robot,
    handle_stop_robot as _handle_stop_robot,
)
from ros_line.endpoints.chat.parsing import (
    detect_direct_intention as _detect_direct_intention,
    extract_info_request as _extract_info_request,
    extract_movement_request as _extract_movement_request,
)
from ros_line.endpoints.chat.prompts import (
    build_classify_text,
    GENERAL_SYSTEM_PROMPT,
)
from ros_line.endpoints.chat.vision import (
    analyze_rqt_graph_image as _analyze_rqt_graph_image,
    is_image_attachment as _is_image_attachment,
)
from ros_line.endpoints.dto.message_dto import ChatRequestDTO

# --- Environment variables configuration ---
current_file = Path(__file__).resolve()
dotenv_candidates = [
    current_file.parents[3] / 'resource' / '.env',
    current_file.parents[2] / 'resource' / '.env',
    Path(get_package_share_directory('ros_line')) / 'config' / '.env',
]
for dotenv_path in dotenv_candidates:
    if dotenv_path.is_file():
        load_dotenv(dotenv_path)
        break


chat_webservice_api_router = APIRouter()


@cbv(chat_webservice_api_router)
class ChatWebService:
    """
    A class that provides the API routes, classifies.

    This class creates the agent functions, processes this ones, and
    manages local ROS nodes, topics, and so on.
    """

    @chat_webservice_api_router.post('/api/chat_v1.1')
    async def chat_with_structure_output(self, request: ChatRequestDTO):
        api_key = os.getenv('GOOGLE_API_KEY')
        if not api_key:
            return {
                'userintention': 'Other',
                'reply': (
                    "GOOGLE_API_KEY isn't configured. "
                    'Define the key in `ros_line/resource/.env` and launch the node again.'
                ),
            }

        llm = ChatGoogleGenerativeAI(model='gemini-2.5-flash')

        has_image_attachment = _is_image_attachment(request.mime_type, request.file_base64)
        user_input = request.message.strip() if request.message else ''

        if has_image_attachment:
            try:
                reply = _analyze_rqt_graph_image(
                    api_key=api_key,
                    caption=user_input,
                    mime_type=request.mime_type or 'image/*',
                    file_base64=request.file_base64 or '',
                )
                history_input = user_input or 'Imagen de rqt_graph adjunta'
                _append_message(request.user_id, 'human', f"""{history_input}
                                [Archivo adjunto: {request.mime_type}]""")
                _append_message(request.user_id, 'ai', reply)
                return {
                    'userintention': 'Other',
                    'analysis_type': 'rqt_graph_image',
                    'reply': reply,
                }
            except Exception as e:
                fallback_reply = (
                    'No pude analizar la imagen adjunta. '
                    f'Error: {str(e)}'
                )
                _append_message(request.user_id, 'human', f"""{user_input}
                                [Archivo adjunto: {request.mime_type}]""")
                _append_message(request.user_id, 'ai', fallback_reply)
                return {
                    'userintention': 'Other',
                    'analysis_type': 'rqt_graph_image',
                    'reply': fallback_reply,
                }

        if request.mime_type and request.file_base64:
            user_input += f' [Archivo adjunto: {request.mime_type}]'

        _append_message(request.user_id, 'human', user_input)
        history_text = _history_as_text(request.user_id, history_window_size())

        direct_intention = _detect_direct_intention(user_input)
        if direct_intention:
            user_intention = direct_intention
        else:
            user_intention = None

        intention_schema = {
            'title': 'UserIntention',
            'description': """Clasifica la intención del mensaje del usuario
                relacionado con robótica y ROS 2.""",
            'type': 'object',
            'properties': {
                'userintention': {
                    'type': 'string',
                    'enum': [
                        'List_topics',
                        'List_nodes',
                        'List_services',
                        'Get_info',
                        'Move_robot',
                        'Stop_robot',
                        'Query_state',
                        'Other',
                    ],
                }
            },
            'required': ['userintention'],
            'additionalProperties': False,
        }

        model_with_structure = llm.with_structured_output(intention_schema)

        classify_text = build_classify_text(history_text, user_input)

        if user_intention is None:
            result = model_with_structure.invoke(classify_text)
            print(result)
            if isinstance(result, list):
                first_result = result[0]
                user_intention = (
                    first_result.get('args', {}).get('userintention')
                    if isinstance(first_result, dict)
                    else getattr(first_result, 'userintention', None)
                )
            else:
                user_intention = getattr(result, 'userintention', None)

        if user_intention == 'Other':
            system_prompt = GENERAL_SYSTEM_PROMPT

            history_text = _history_as_text(request.user_id, history_window_size())
            user_input = request.message

            prompt_text = f"""{system_prompt}\n\n
                Historial:\n{history_text}\n\n
                Usuario: {user_input}\nAsistente:"""

            ai_result = llm.invoke(prompt_text)
            reply = getattr(ai_result, 'content', str(ai_result))
            _append_message(request.user_id, 'ai', reply)
            print(ai_result)
            return {
                'userintention': 'Other',
                'reply': reply,
            }

        elif user_intention == 'List_topics':
            user_input = request.message

            ros_agent = _get_ros_agent()
            if ros_agent:
                try:
                    topics_output = ros_agent.list_topics()
                    reply_text = (
                        'Tópicos ROS 2 activos:\n'
                        f"""{topics_output if topics_output else
                             'No se pudieron obtener los tópicos'}\n\n"""
                        '¿Necesitas información específica de algún tópico?'
                    )
                    status = 'success'
                except Exception as e:
                    reply_text = (
                        'Error al ejecutar el comando ROS:\n'
                        f'ros2 topic list\n\n'
                        f'Error: {str(e)}'
                    )
                    status = 'error'
            else:
                reply_text = (
                    'El agente ROS no está disponible.\n'
                    'Comando que se ejecutaría: ros2 topic list\n\n'
                    'Verifica que ROS 2 esté configurado correctamente.'
                )
                status = 'ros_unavailable'

            _append_message(request.user_id, 'ai', reply_text)
            return {
                'userintention': 'List_topics',
                'status': status,
                'ros_command': 'ros2 topic list',
                'reply': reply_text,
            }

        elif user_intention == 'List_nodes':
            user_input = request.message

            ros_agent = _get_ros_agent()
            if ros_agent:
                try:
                    nodes_output = ros_agent.list_nodes()
                    reply_text = (
                        'Nodos ROS 2 activos:\n'
                        f"""{nodes_output if nodes_output else
                             'No se pudieron obtener los nodos'}\n\n"""
                        '¿Necesitas información específica de algún nodo?'
                    )
                    status = 'success'
                except Exception as e:
                    reply_text = (
                        'Error al ejecutar el comando ROS:\n'
                        f'ros2 node list\n\n'
                        f'Error: {str(e)}'
                    )
                    status = 'error'
            else:
                reply_text = (
                    'El agente ROS no está disponible.\n'
                    'Comando que se ejecutaría: ros2 node list\n\n'
                    'Verifica que ROS 2 esté configurado correctamente.'
                )
                status = 'ros_unavailable'

            _append_message(request.user_id, 'ai', reply_text)
            return {
                'userintention': 'List_nodes',
                'status': status,
                'ros_command': 'ros2 node list',
                'reply': reply_text,
            }

        elif user_intention == 'List_services':
            user_input = request.message

            ros_agent = _get_ros_agent()
            if ros_agent:
                try:
                    services_output = ros_agent.list_services()
                    reply_text = (
                        'Servicios ROS 2 disponibles:\n'
                        f"""{services_output if services_output else
                             'No se pudieron obtener los servicios'}\n\n"""
                        '¿Quieres llamar algún servicio específico?'
                    )
                    status = 'success'
                except Exception as e:
                    reply_text = (
                        'Error al ejecutar el comando ROS:\n'
                        f'ros2 service list\n\n'
                        f'Error: {str(e)}'
                    )
                    status = 'error'
            else:
                reply_text = (
                    'El agente ROS no está disponible.\n'
                    'Comando que se ejecutaría: ros2 service list\n\n'
                    'Verifica que ROS 2 esté configurado correctamente.'
                )
                status = 'ros_unavailable'

            _append_message(request.user_id, 'ai', reply_text)
            return {
                'userintention': 'List_services',
                'status': status,
                'ros_command': 'ros2 service list',
                'reply': reply_text,
            }

        elif user_intention == 'Get_info':
            user_input = request.message
            info_data = _extract_info_request(user_input)
            info_type = info_data.get('info_type', 'general_info')
            target_name = info_data.get('target_name', '')

            if (
                    info_type in ['topic_info', 'node_info', 'service_info']
                    and target_name
                    and not target_name.startswith('/')):
                target_name = f'/{target_name}'

            ros_agent = _get_ros_agent()

            inferred_info_type = info_type
            if (
                    ros_agent and target_name and inferred_info_type == 'general_info'
                    and target_name.startswith('/')):
                try:
                    topics_output = ros_agent.list_topics() or ''
                    nodes_output = ros_agent.list_nodes() or ''
                    services_output = ros_agent.list_services() or ''

                    topics = [t.strip() for t in topics_output.splitlines() if t.strip()]
                    nodes = [n.strip() for n in nodes_output.splitlines() if n.strip()]
                    services = [s.strip() for s in services_output.splitlines() if s.strip()]

                    def matches(name_list, target):
                        for item in name_list:
                            if (item == target
                                    or item == target.lstrip('/')
                                    or item.rstrip('/') == target):
                                return True
                        return False

                    if matches(topics, target_name):
                        inferred_info_type = 'topic_info'
                    elif matches(nodes, target_name):
                        inferred_info_type = 'node_info'
                    elif matches(services, target_name):
                        inferred_info_type = 'service_info'
                except Exception:
                    inferred_info_type = info_type

            if (inferred_info_type == 'topic_info'
                    and target_name
                    and not target_name.startswith('/')):
                target_name = f'/{target_name}'

            if (
                ros_agent
                and target_name
                and inferred_info_type in ['topic_info', 'node_info', 'service_info']
            ):
                try:
                    ros_type = inferred_info_type.replace('_info', '')
                    info_output = ros_agent.get_info(ros_type, target_name)

                    reply_text = (
                        f'Información sobre {target_name}:\n'
                        f"""{info_output if info_output else
                             'No se pudo obtener la información'}\n\n"""
                        '¿Necesitas más detalles?'
                    )
                    ros_command = f'ros2 {ros_type} info {target_name}'
                    status = 'success'
                except Exception as e:
                    reply_text = (
                        f'Error al obtener información sobre {target_name}:\n'
                        f'Error: {str(e)}'
                    )
                    ros_command = f"""ros2 {inferred_info_type.replace('_info', '')}
                    info {target_name}"""
                    status = 'error'
            else:
                reply_text = (
                    'Necesito más información específica sobre qué quieres consultar.\n'
                    "Ejemplo: 'información del tópico /cmd_vel' o 'info del nodo /turtlesim'"
                )
                ros_command = 'ros2 --help'
                status = 'need_more_info'

            _append_message(request.user_id, 'ai', reply_text)
            return {
                'userintention': 'Get_info',
                'status': status,
                'ros_command': ros_command,
                'reply': reply_text,
            }

        elif user_intention == 'Move_robot':
            return _handle_move_robot(request, llm,
                                      request.message,
                                      _extract_movement_request(request.message),
                                      _append_message)

        elif user_intention == 'Stop_robot':
            return _handle_stop_robot(request, llm, request.message, _append_message)

        elif user_intention == 'Query_state':
            user_input = request.message

            reply_text = (
                '📊 Consulta de estado del robot\n'
                'Esta funcionalidad está por implementar.\n\n'
                'Próximamente podrás consultar:\n'
                '- Posición y odometría\n'
                '- Estado de batería\n'
                '- Datos de sensores\n'
                '- Diagnósticos del sistema\n'
                '- Transformadas (TF)'
            )

            _append_message(request.user_id, 'ai', reply_text)
            return {
                'userintention': 'Query_state',
                'status': 'not_implemented',
                'ros_command': '# Por implementar',
                'reply': reply_text,
            }

        else:
            user_input = request.message
            history_text = _history_as_text(request.user_id)

            default_text = (
                'ROLE: ROSLine, asistente especializado en ROS 2.\n'
                'El usuario ha enviado una solicitud que no pude clasificar correctamente. '
                'Responde de manera amigable y sugiere las capacidades disponibles.\n\n'
                f'Historial:\n{history_text}\n\n'
                f'Usuario: {user_input}\n'
                f'Asistente:'
            )

            reply_obj = llm.invoke(default_text)
            reply_text = getattr(reply_obj, 'content', str(reply_obj))
            _append_message(request.user_id, 'ai', reply_text)

            return {
                'userintention': user_intention or 'Unknown',
                'status': 'unhandled',
                'reply': reply_text,
            }
