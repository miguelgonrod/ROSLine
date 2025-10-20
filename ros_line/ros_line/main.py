from dotenv import load_dotenv
from fastapi import FastAPI
import uvicorn
from ros_line.endpoints.hello_world_webservice import HelloWorldWebService, hello_webservice_api_router
from ros_line.endpoints.business_webservice import business_webservice_api_router
from ros_line.endpoints.chat_webservice import chat_webservice_api_router
import os

# Cargar el archivo .env desde la carpeta resource
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'resource', '.env')
load_dotenv(dotenv_path)

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    GOOGLE_API_KEY = input("Por favor, ingrese su API KEY de Google (GOOGLE_API_KEY): ")
    os.environ["GOOGLE_API_KEY"] = GOOGLE_API_KEY


def main():
    """Función principal para el entry point del paquete ROS."""
    app = FastAPI()
    app.include_router(hello_webservice_api_router)
    app.include_router(business_webservice_api_router)
    app.include_router(chat_webservice_api_router)
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()