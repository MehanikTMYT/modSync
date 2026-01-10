# ModSync - Minecraft Mod Synchronization Tool

A comprehensive tool for synchronizing Minecraft mods between clients and servers with adaptive download strategies and robust error handling.

## Table of Contents
- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Installation](#installation)
- [Usage](#usage)
- [Client](#client)
- [Server](#server)
- [Configuration](#configuration)
- [Development](#development)
- [Build Instructions](#build-instructions)
- [License](#license)

## Overview

ModSync is a client-server application designed to synchronize Minecraft mods across multiple clients. It provides both a GUI client for end users and a server component for hosting mod files.

## Features

### Client Features
- **GUI Interface**: Intuitive tkinter-based interface with real-time progress tracking
- **Adaptive Download Strategies**: Automatically selects optimal download strategy based on connection speed and file distribution
- **Connection Testing**: Built-in speed and connectivity testing with quality assessment
- **File Integrity**: MD5 hash verification for downloaded files
- **Resume Support**: Ability to resume interrupted downloads for large files
- **Problem File Management**: Visual interface for handling missing or corrupted files
- **Multi-threaded Downloads**: Parallel downloads with configurable worker counts
- **Auto-reconnection**: Automatic reconnection on network failures

### Server Features
- **Simple HTTP Server**: Lightweight server for file distribution
- **File Monitoring**: Real-time monitoring of mod directory changes
- **Hash Generation**: Automatic generation of file hash lists
- **Threading Support**: Concurrent request handling

## Architecture

### Client Architecture
```
modsync/
├── client/
│   ├── config/           # Configuration management
│   │   └── manager.py    # Config file handling
│   ├── download/         # Download management
│   │   ├── manager.py    # Download orchestrator
│   │   └── simple_strategy.py # Download strategies
│   ├── network/          # Network utilities
│   │   ├── connection_utils.py # Connection management
│   │   └── speed_test_manager.py # Speed testing
│   ├── ui/               # User interface
│   │   └── main_window.py # Main GUI application
│   └── main.py           # Client entry point
├── server/               # Server components
│   ├── server.py         # Main server
│   ├── handlers.py       # Request handlers
│   ├── models.py         # Data models
│   ├── services.py       # Core services
│   ├── utils.py          # Server utilities
│   └── __init__.py
├── shared/               # Shared utilities
│   └── utils/            # Common helper functions
└── __init__.py
```

### Server Architecture
The server uses a simple HTTP server architecture with file monitoring capabilities to automatically update when mod files change.

## Installation

### Prerequisites
- Python 3.7 or higher
- pip package manager

### Client Installation
```bash
# Install client requirements
pip install -r requirements_client.txt

# For GUI client (includes tkinter)
pip install -r requirements_client.txt
```

### Server Installation
```bash
# Install server requirements
pip install -r requirements_server.txt
```

### Complete Installation
```bash
# Install all requirements
pip install -r requirements.txt
pip install -r requirements_client.txt
pip install -r requirements_server.txt
```

## Usage

### Running the Client

#### GUI Client
```bash
python -m modsync.client.main
```

#### Command Line Client (if available)
```bash
python -m modsync.client.cli
```

### Running the Server

```bash
# Start server on default port 8000
python -m modsync.server.server

# Start server on custom port
python -m modsync.server.server --port 8080

# Start server with custom mods directory
python -m modsync.server.server --mods-dir /path/to/mods

# Start server without file monitoring
python -m modsync.server.server --no-monitoring
```

## Client

### GUI Interface
The client provides a comprehensive GUI with the following features:

1. **Connection Status**: Real-time server connectivity status
2. **Mod Folder Selection**: Easy folder management
3. **Download Strategy Selection**: Automatic or manual strategy selection
4. **Synchronization**: One-click mod synchronization
5. **Problem File Management**: Visual handling of missing/corrupted files
6. **Progress Tracking**: Detailed download progress with speed metrics
7. **Settings**: Configuration options for sync behavior

### Download Strategies
The client implements multiple download strategies:

- **Stable Sequential**: Maximum reliability, single-threaded downloads
- **Balanced Adaptive**: Optimal balance of speed and reliability
- **Fast Optimized**: Maximum speed for fast connections
- **Gaming Priority**: Critical files first for quick game start
- **Adaptive Auto**: Automatically selects strategy based on connection and file distribution

### Auto Strategy Selection
The client automatically selects the optimal strategy based on:
- Connection speed and quality
- File size distribution
- Network stability

## Server

### Server Configuration
- Default port: 8000
- Default mods directory: ./mods
- File monitoring enabled by default

### Server Endpoints
- `/` - Root directory listing
- `/hashes.json` - File hash information
- `/[filename]` - Individual file download
- `/ping` - Connectivity test
- `/speedtest` - Speed test endpoint

### File Monitoring
The server monitors the mods directory for changes and automatically updates the hash list when files are added, modified, or removed.

## Configuration

### Client Configuration
The client uses `modsync_config.ini` for storing settings:

```ini
[paths]
minecraft_folder = ./minecraft
mods_folder = ./minecraft/mods
backup_folder = ./backups

[connection]
server_url = http://147.45.184.36:8000
timeout = 30
max_retries = 3

[download]
max_workers = 4
chunk_size = 32768
enable_resume = True

[ui]
theme = dark
language = ru_RU
auto_check_updates = True
```

### Server Configuration
Server configuration is done via command-line arguments (see usage section).

## Development

### Project Structure
- `modsync/client/` - Client-side code
- `modsync/server/` - Server-side code
- `modsync/shared/` - Shared utilities
- `modsync/utils/` - General utilities

### Code Style
- Follow PEP 8 guidelines
- Use descriptive variable names
- Include docstrings for all functions and classes

### Testing
To run basic functionality tests:
```bash
python -c "from modsync.client.ui.main_window import ModSyncApp; print('Import successful')"
python -c "from modsync.server.server import ModSyncServer; print('Server import successful')"
```

## Build Instructions

### Client Build (PyInstaller)
For Windows (GUI):
```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name ModSyncClient modsync/client/main.py
```

For Windows (CLI):
```bash
pyinstaller --onefile --name ModSyncClientCLI modsync/client/main.py
```

For Linux:
```bash
pyinstaller --onefile --name ModSyncClient modsync/client/main.py
```

### Server Build (PyInstaller)
For Linux:
```bash
pyinstaller --onefile --name ModSyncServer modsync/server/server.py
```

### Build Requirements
- PyInstaller
- All application dependencies

## Error Handling

### Client Error Handling
- Network connection failures with auto-retry
- File integrity verification
- Resume interrupted downloads
- Graceful handling of missing files

### Server Error Handling
- Thread-safe request handling
- File system monitoring errors
- Network error recovery

## Troubleshooting

### Common Issues
1. **tkinter not found**: Install tkinter with your system package manager
2. **Connection timeouts**: Check server URL in configuration
3. **Permission errors**: Ensure proper file permissions for mod directories

### Debugging
Enable verbose logging by adding debug statements to relevant modules.

## License

MIT License

Copyright (c) 2024 modSync

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.