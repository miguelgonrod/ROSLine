# ROSLine
[![language](https://img.shields.io/badge/language-python-239120)](#)
[![language](https://img.shields.io/badge/language-typescript-3178c6)](#)
[![OS](https://img.shields.io/badge/OS-Ubuntu_24.04-0078D4)](#)
[![ROS](https://img.shields.io/badge/ROS_Version-Jazzy_Jalisco-0078D4)](#)
[![CPU](https://img.shields.io/badge/CPU-x86%2C%20x64%2C%20ARM%2C%20ARM64-FF8C00)](#)
[![GitHub release](https://img.shields.io/badge/release-v2.0.0-4493f8)](#)
[![GitHub last commit](https://img.shields.io/badge/last_commit-may_2026-96981c)](#)

⭐ Star us on GitHub — it motivates us a lot!

## Table of Contents
- [About](#-about)
- [Architecture](#-architecture)
- [Features](#-features)
- [How to Build](#-how-to-build)
- [WhatsApp Setup](#-whatsapp-setup)
- [Usage](#-usage)
- [License](#-license)

## 🚀 About

ROSLine is a natural language interface that bridges WhatsApp and ROS 2. It allows users to control and monitor ROS-based robots through chat commands powered by Gemini and a lightweight reasoning layer. The system consists of two main components: a ROS 2 node that provides a FastAPI web service for robot control, and a WhatsApp client built with Baileys that handles message processing and communication.

## 🏗️ Architecture

The system architecture consists of:

- **ROS 2 Node (`ros_line`)**: FastAPI-based web service that processes natural language commands and translates them into ROS 2 actions
- **WhatsApp Client (`ros-line-whatsapp-qr`)**: TypeScript/Node.js application using Baileys library for WhatsApp Web API integration
- **AI Integration**: Google Gemini for natural language processing and command interpretation

## ✨ Features

- 📱 **WhatsApp Integration**: Send commands directly through WhatsApp messages
- 🤖 **Natural Language Processing**: AI-powered command interpretation using Google Gemini
- 🔄 **ROS 2 Communication**: Seamless integration with ROS 2 topics and services
- 🚀 **FastAPI Backend**: High-performance async web service
- 📡 **Real-time Communication**: Instant message processing and robot control

## 📝 How to Build

To build the packages (only if you are using ROS 2 Jazzy and Python 3.12), follow these steps:

### Prerequisites
- ROS 2 Jazzy Jalisco
- Python 3.12
- Node.js 20.x and npm/yarn
- Google Gemini API key

### ROS 2 Package Setup

```shell
# First clone the repository in your workspace and create a symlink
cd ~/ros2_ws/src
git clone https://github.com/miguelgonrod/ROSLine
ln -s /home/$USER/ros2_ws/src/ROSLine/ros_line /home/$USER/ros2_ws/src

# Install Python dependencies for ROS 2 node
cd ROSLine/ros_line/resource
pip install -r requirements.txt --break-system-packages

# Build the ROS 2 package
cd ~/ros2_ws
colcon build --packages-select ros_line
source install/setup.bash
```

### WhatsApp Client Setup
⚠️ WARNING: This package uses the Baileys library to connect to WhatsApp. Using it may result in your WhatsApp account being restricted or banned. Use it at your own risk. We strongly recommend using the official WhatsApp Business API, or testing with a separate WhatsApp Business account.
```shell
# Navigate to WhatsApp client directory
cd ~/ros2_ws/src/ROSLine/ros-line-whatsapp-qr

# Install Node.js dependencies
npm install

# Build TypeScript code (if needed)
npx tsx src/index.ts
```
If npm is not working as expected, is because you need to install nodejs 20.x and this is not supported by default by Ubuntu 24.04. If this is your case run this command before `sudo apt install`:
```shell
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
```

### Environment Configuration

Create a `.env` file in the ROS 2 package directory:

```bash
# Create environment file
cd ~/ros2_ws/src/ROSLine/ros_line/resource
touch .env
```

Add your API keys and configuration (you should use **ros_line/resource/.env.example** as a template):
```env
GOOGLE_API_KEY=[Your API KEY]
GOOGLE_APPLICATION_CREDENTIALS=[Absolute route to your json API KEY]

ROS_DOMAIN_ID=0
ROS_DISTRO=jazzy
```
`GOOGLE_API_KEY` is needed to connect to Gemini API. This API KEY is created in [Google AI Studio](https://aistudio.google.com/app/api-keys)
`GOOGLE_APPLICATION_CREDENTIALS` is needed to connect to Google TTS. To create this API Credentials you need to follow this steps:
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Go to "APIs and services > Library" and install `Cloud Speech-to-Text API`
3. Go to "Credentials", click "Create credentials", create a `Service account` and give it the name you prefer. (No more configurations needed)
4. Click on the new Service account, go to "Keys", create a new "JSON" key and save it preferably in `ROSLine/ros_line/resource`. (Don't forget to edit the `.env`)

## 📱 WhatsApp Setup

### Initial Authentication

1. **Start the WhatsApp client:**
```shell
cd ~/ros2_ws/src/ROSLine/ros-line-whatsapp-qr
npx tsx src/index.ts
```

2. **Scan QR Code:**
   - A QR code will appear in the terminal
   - Open WhatsApp on your phone
   - Go to Settings > Linked Devices > Link a Device
   - Scan the QR code displayed in the terminal

3. **Authentication files will be automatically saved in `auth_info_baileys/` directory**

## 🚀 Usage

### Starting the System

1. **Launch the ROS 2 node:**
```shell
cd ~/ros2_ws
colcon build
source install/setup.bash
ros2 launch ros_line ros_agent.launch.py
```

2. **Start the WhatsApp client:**
```shell
cd ~/ros2_ws/src/ROSLine/ros-line-whatsapp-qr
npx tsx src/index.ts
```

### Sending Commands

Once both services are running, you can send natural language commands through WhatsApp:

- "Move the robot forward"
- "Turn left 90 degrees"
- "Stop the robot"
- "Get robot status"
- "Analize this rqt graph"

The system will interpret your commands and execute the corresponding ROS 2 actions.

## ⚙️ Configuration

### API Endpoints

The ROS 2 node exposes the following endpoint:

- `POST /api/chat_webservice` - Main chat interface

### Supported Message Types

- **Text messages**: Natural language commands
- **Image messages**: Visual input for robot perception
- **Audio messages**: Voice commands (transcribed to text)

## 📃 License

ROSLine is available under the BSD-3-Clause license. See the LICENSE file for more details.
