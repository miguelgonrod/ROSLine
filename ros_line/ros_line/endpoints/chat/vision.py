"""Vision helpers for chat image analysis."""

import base64
import os

import google.generativeai as genai


def is_image_attachment(mime_type: str | None, file_base64: str | None) -> bool:
    return bool(mime_type and mime_type.startswith("image/") and file_base64)


def is_quota_error(error: Exception) -> bool:
    error_text = str(error).lower()
    return "429" in error_text or "quota" in error_text or "rate limit" in error_text


def analyze_rqt_graph_image(api_key: str, caption: str, mime_type: str, file_base64: str) -> str:
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
            if not is_quota_error(error):
                raise

    if last_error is not None and is_quota_error(last_error):
        return (
            "No pude analizar la imagen porque se agotó la cuota del modelo de visión. "
            "Prueba de nuevo en unos minutos o cambia la variable ROSLINE_IMAGE_MODELS para usar otro modelo."
        )

    return "No pude interpretar la imagen adjunta. Si quieres, reenvíala con más resolución o una captura más centrada del rqt_graph."
