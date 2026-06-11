# Voice to Type

A background voice-to-text service that automatically types out speech in any active window. It uses PyQt6 to display a translucent overlay with a real-time reactive waveform, and sends the recorded audio to the Groq API (Whisper) for transcription.

## Features

* Global hotkey trigger: Start and stop recording from anywhere using Ctrl + Shift + Space.
* Live visual feedback: A clean, translucent overlay appears at the bottom of the screen when recording, displaying a real-time waveform that reacts to input volume.
* Keyboard simulation: The service types the transcribed text directly into the active text field.
* Background execution: Runs in the background without stealing active window focus.

## Architecture and Components

The codebase is split into modular components inside the src directory.

### 1. Service Orchestrator (src/main.py)
VoiceToTypeService coordinates all other components. It listens for the toggle hotkey, starts and stops the recorder, manages threading for the transcription call to keep the UI responsive, and triggers the keyboard emulator when transcription is ready.

### 2. Audio Recorder (src/core/recorder.py)
Uses sounddevice to record mono audio from the default input device. It calculates the RMS (Root Mean Square) amplitude for each block of audio and passes it to the UI callback to animate the waveform. When stopped, it writes the recorded stream to a temporary WAV file.

### 3. Hotkey Listener (src/service/listener.py)
Uses pynput to register and monitor global keyboard inputs. It handles modifier keys and triggers the recording toggle when the registered hotkey is pressed.

### 4. Translucent Overlay (src/ui/overlay.py)
A custom PyQt6 widget with frameless, translucent, and stay-on-top window flags. It paints a custom glass-like UI element with shadows and a 7-bar waveform. The bar heights are updated dynamically via Qt signals sent from the audio thread.

### 5. Transcriber (src/core/transcriber.py)
A thin wrapper around the Groq Python client. It opens the recorded audio file and sends it to the whisper-large-v3-turbo model, returning the transcribed text.

### 6. Keyboard Typer (src/core/typer.py)
Uses pyautogui to simulate keystrokes, injecting the transcribed text into whichever text box currently has focus.

## Prerequisites

* Python 3.11 or newer
* A Groq API Key (available on console.groq.com)
* A working microphone

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/YOUR_USERNAME/voice-to-type.git
   cd voice-to-type
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   
   # Windows:
   .venv\Scripts\activate
   
   # Linux/macOS:
   source .venv/bin/activate
   ```

3. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up the environment variables:
   * Copy .env.example to .env
   * Edit .env and enter your Groq API key and preferred hotkey:
     ```env
     GROQ_API_KEY=gsk_your_api_key_here
     HOTKEY=ctrl+shift+space
     ```

## Usage

Start the service from the terminal:
```bash
python src/main.py
```

* Press Ctrl + Shift + Space to start recording. The translucent overlay will appear.
* Speak clearly into your microphone.
* Press Ctrl + Shift + Space again to stop recording. The overlay will close and the service will type the transcribed text.

## Auto-Startup Configuration

### Windows Setup

To run the script automatically and silently on system login:

1. Press Win + R, type `shell:startup`, and press Enter to open the startup folder.
2. Create a new file named `StartVoiceToType.vbs` inside the folder.
3. Open the file in a text editor and add the following script (replace the path with your actual project directory):
   ```vbscript
   Set WshShell = CreateObject("WScript.Shell")
   WshShell.Run "cmd.exe /c cd /d D:\PROJECT\voice_to_type_project && .venv\Scripts\pythonw.exe src\main.py", 0, False
   ```
   Note: Using pythonw.exe prevents a terminal window from opening.

### Linux Setup (Systemd User Service)

On Linux, you can manage the script as a user systemd service to run it when your graphical session starts:

1. Create the user systemd directory if it does not exist:
   ```bash
   mkdir -p ~/.config/systemd/user/
   ```

2. Create a new service file named `voice-to-type.service` in that directory:
   ```bash
   nano ~/.config/systemd/user/voice-to-type.service
   ```

3. Add the following service definition (update paths and username accordingly):
   ```ini
   [Unit]
   Description=Voice to Type Service
   After=graphical-session.target
   
   [Service]
   Type=simple
   WorkingDirectory=/home/YOUR_USER/path/to/voice-to-type
   ExecStart=/home/YOUR_USER/path/to/voice-to-type/.venv/bin/python src/main.py
   Environment="DISPLAY=:0"
   Environment="XAUTHORITY=/home/YOUR_USER/.Xauthority"
   Restart=on-failure
   RestartSec=5
   
   [Install]
   WantedBy=default.target
   ```

4. Reload systemd and enable the service:
   ```bash
   systemctl --user daemon-reload
   systemctl --user enable voice-to-type.service
   systemctl --user start voice-to-type.service
   ```

5. View logs using journalctl:
   ```bash
   journalctl --user -u voice-to-type.service -f
   ```

## License

This project is licensed under the MIT License.
