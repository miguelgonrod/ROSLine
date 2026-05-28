"""
Load the package entry point and initialize the FastAPI routers.

This module also loads the environment variables required for the API calls.
"""
import os
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from dotenv import load_dotenv
from fastapi import FastAPI
from ros_line.endpoints.chat_webservice import chat_webservice_api_router
import uvicorn


def load_environment() -> None:
    """Load the .env file from the source tree or the installed package layout."""
    current_file = Path(__file__).resolve()
    candidate_paths = [
        current_file.parents[2] / 'resource' / '.env',
        current_file.parents[1] / 'resource' / '.env',
        Path(get_package_share_directory('ros_line')) / 'config' / '.env',
    ]

    for candidate in candidate_paths:
        if candidate.is_file():
            load_dotenv(candidate)
            return


load_environment()

GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
if not GOOGLE_API_KEY:
    print('Warning: GOOGLE_API_KEY not configured. Most functionalities will fail without a key.')
    GOOGLE_API_KEY = ''
    os.environ['GOOGLE_API_KEY'] = GOOGLE_API_KEY


def main():
    """Initialize the ROS Line FastAPI application."""
    app = FastAPI()
    app.include_router(chat_webservice_api_router)
    uvicorn.run(app, host='127.0.0.1', port=8000)


if __name__ == '__main__':
    main()
