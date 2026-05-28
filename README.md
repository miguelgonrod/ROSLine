# ROSLine
[![language](https://img.shields.io/badge/language-python-239120)](#)
[![language](https://img.shields.io/badge/language-typescript-3178c6)](#)
[![OS](https://img.shields.io/badge/OS-Ubuntu_24.04-0078D4)](#)
[![ROS](https://img.shields.io/badge/ROS_Version-Jazzy_Jalisco-0078D4)](#)
[![CPU](https://img.shields.io/badge/CPU-x86%2C%20x64%2C%20ARM%2C%20ARM64-FF8C00)](#)
[![GitHub release](https://img.shields.io/badge/release-v1.0.0-4493f8)](#)
[![GitHub release date](https://img.shields.io/badge/release_date-october_2025-96981c)](#)
[![GitHub last commit](https://img.shields.io/badge/last_commit-october_2025-96981c)](#)

⭐ Star us on GitHub — it motivates us a lot!

## Table of Contents
- [About](#-about)
- [Architecture](#-architecture)
- [Features](#-features)
- [How to Build](#-how-to-build)
- [WhatsApp Setup](#-whatsapp-setup)
- [Usage](#-usage)
- [Configuration](#-configuration)
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
- Node.js and npm/yarn
- Google Gemini API key
- Supabase account (optional)

### ROS 2 Package Setup

```shell
# First clone the repository in your workspace
cd ~/ros2_ws/src
git clone https://github.com/miguelgonrod/ROSLine

# Install Python dependencies for ROS 2 node
cd ROSLine/ros_line/resource
pip install -r requirements.txt --break-system-packages

# Build the ROS 2 package
cd ~/ros2_ws
colcon build --packages-select ros_line
source install/setup.bash
```

### WhatsApp Client Setup

```shell
# Navigate to WhatsApp client directory
cd ~/ros2_ws/src/ROSLine/ros-line-whatsapp-qr

# Install Node.js dependencies
npm install

# Build TypeScript code (if needed)
npx tsx src/index.ts
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

ROS_DOMAIN_ID=0
ROS_DISTRO=jazzy
```

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
- "Take a photo"

The system will interpret your commands and execute the corresponding ROS 2 actions.

## ⚙️ Configuration

### API Endpoints

The ROS 2 node exposes the following endpoints:

- `POST /api/chat_v1.1` - Main chat interface
- `GET /api/hello` - Health check
- `POST /api/business` - Business logic endpoint

## Code Quality

The Python package follows the same linting rules used in the Padawan project:

- `flake8` with a maximum line length of 120
- `E203` ignored for Black-compatible slicing spacing
- `pep257` docstring checks through the existing `ament_pep257` test

To run the checks locally from the repository root:

```bash
python3 -m pytest ros_line/test
```

To make Git run them before commits and pushes, enable the repo hooks once:

```bash
git config core.hooksPath .githooks
```

GitHub Actions runs the same Python checks on every push and pull request.

### Supported Message Types

- **Text messages**: Natural language commands
- **Image messages**: Visual input for robot perception
- **Audio messages**: Voice commands (transcribed to text)

### ROS 2 Integration

The system can interact with standard ROS 2 interfaces:
- `geometry_msgs/Twist` for robot movement
- `std_msgs/String` for status messages
- Custom service calls for specific robot functions

## 📃 License

ROSLine is available under the BSD-3-Clause license. See the LICENSE file for more details.
