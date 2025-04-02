# Hoogland
A security alert application with random popups, sound notifications, and silent updates.

## Features
- Random alerts within a configurable time window
- Web-based configuration UI
- Encrypted password storage
- Silent updates via GitHub
- System tray integration

## Installation
1. Install dependencies: `pip install -r requirements.txt`
2. Run: `python app.py`
3. Or use the installer built with `setup.iss`

## Building
- `pyinstaller --onedir --windowed --add-data "alert_sound.mp3;." --add-data "templates;templates" app.py`
- Compile `setup.iss` with Inno Setup
