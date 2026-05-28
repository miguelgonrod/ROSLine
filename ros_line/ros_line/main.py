"""
Load the package entry point and initialize the FastAPI routers.

This module also loads the environment variables required for the API calls.
"""
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from ros_line.endpoints.chat_webservice import chat_webservice_api_router
import uvicorn


# Loads .env file from resource folder.
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'resource', '.env')
load_dotenv(dotenv_path)

GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
if not GOOGLE_API_KEY:
    GOOGLE_API_KEY = input('Por favor, ingrese su API KEY de Google (GOOGLE_API_KEY): ')
    os.environ['GOOGLE_API_KEY'] = GOOGLE_API_KEY


def main():
    """Initialize the ROS Line FastAPI application."""
    app = FastAPI()
    app.include_router(chat_webservice_api_router)
    uvicorn.run(app, host='127.0.0.1', port=8000)


if __name__ == '__main__':
    main()
