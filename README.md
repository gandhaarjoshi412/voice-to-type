# Voice to Type

A background voice-to-text service that automatically types out speech in any active window. It uses PyQt6 to display a translucent overlay with a real-time reactive waveform, and sends the recorded audio to the Groq API (Whisper) for transcription.

## Features

* **Global hotkey trigger**: Start and stop recording from anywhere using a single hotkey (configured in `.env`, e.g., `Ctrl + Shift + Space`).
* **Live visual feedback**: A sleek "Apple Liquid Glass" translucent overlay appears at the bottom of the screen when recording, displaying a real-time waveform that dynamically reacts to microphone volume.
* **Instant Keyboard Injection**: Uses a fast clipboard-swap and paste action (`Ctrl+V` on Windows, `Cmd+V` on macOS) to insert transcribed text instantly, automatically preserving and restoring the user's original clipboard content immediately after.
* **Keystroke Simulation Fallback**: Gracefully falls back to simulated character-by-character typing if the clipboard is restricted or fails.
* **Context-Aware Transcriptions**: Automatically detects the active window application category (e.g., Cursor/VS Code, Slack/Discord, Command Prompt/PowerShell, Outlook/Gmail) and injects customized prompts to guide Whisper's formatting, slang, syntax, and jargon matching that application's style.
* **Local Audio Backup (7-day Retention & 1GB Limit)**: Automatically saves every voice recording inside `data/audio_backup/`. Keeps a rolling 7-day backup of your voice files, automatically pruning older files or oldest items to guarantee audio storage does not exceed 1 GB.
* **Custom SQLite History DB (14-day Retention)**: Stores all transcribed text, window titles, application names, timestamps, and audio links in a local SQLite database (`data/history.db`). Automatically deletes records older than 14 days on a rolling basis.
* **WhisperFlow-Style Analytics & Productivity Metrics**: Tracks total words spoken, dictation duration, speaking pace (WPM), active streaks, and calculates real time saved compared to standard 40 WPM manual keyboard typing (averaging a 3.5x to 4.5x speed multiplier).
* **Analytics Dashboard UI**: A dedicated, dark-themed control center and productivity dashboard displaying key performance indicators (KPI cards), an interactive 7-day daily activity trend chart, breakdown of top applications spoken into, and a recent dictations log with inline audio playback.
* **Persistent System Tray Integration**: Displays a live system tray icon with real-time status indication (sleek cyan idle icon vs glowing red recording icon). Click or double-click to immediately open the Analytics Dashboard. Context menu provides instant controls, recording toggle, history search, and real-time audio backup storage monitoring (MB / 1GB).
* **Spotlight/Apple Finder-like Search UI**: Press a separate hotkey (`Ctrl + Shift + F` by default) to open a beautiful, translucent, drop-shadow history search panel. You can query your past transcriptions and play back the original voice files with the click of a button (if within the 7-day retention window).
* **Background execution**: Runs silently in the background without stealing focus from the target window.

## Architecture and Components

The codebase is split into modular components inside the src directory.

### 1. Service Orchestrator (src/main.py)
VoiceToTypeService coordinates all other components. It listens for control triggers (record, finder, dashboard, quit), starts and stops the recorder, manages background threading for transcription and typing injection, captures active window context, logs text with duration and word counts into SQLite, updates the system tray and dashboard in real time, and schedules storage cleanup operations.

### 2. Audio Recorder (src/core/recorder.py)
Uses sounddevice to record mono audio from the default input device. It calculates the RMS (Root Mean Square) amplitude for each block of audio and passes it to the UI callback to animate the waveform. When stopped, it writes the recorded stream to the designated audio backup path and returns the exact audio duration in seconds.

### 3. Hotkey & Pipe Listener (src/service/listener.py & trigger.py)
Sets up a Named Pipe (FIFO at `/tmp/antigravity_pipe`) to listen for control triggers and execute callbacks for `TRIGGER` (record toggle), `SEARCH` (finder toggle), `DASHBOARD` (analytics dashboard toggle), and `QUIT` (graceful termination).

### 4. Translucent Overlay (src/ui/overlay.py)
A custom PyQt6 widget with frameless, translucent, and stay-on-top window flags. It paints a custom glass-like UI element with shadows and a 7-bar waveform. The bar heights are updated dynamically via Qt signals sent from the audio thread.

### 5. Analytics Dashboard (src/ui/dashboard.py)
A modern WhisperFlow-inspired dashboard showing productivity metrics (Time Saved, Words Spoken, Dictations, Audio & Streak), an interactive 7-day bar chart, application distribution breakdown, and recent dictations list with audio playback.

### 6. System Tray (src/ui/tray.py)
A PyQt6 QSystemTrayIcon with dynamically generated high-DPI vector icons reflecting idle and recording states, interactive notifications, and a context menu providing shortcuts to toggle dictation, launch the dashboard, open the search finder, and inspect storage usage.

### 7. Transcriber (src/core/transcriber.py)
A thin wrapper around the Groq Python client. It opens the recorded audio file and sends it to the whisper-large-v3-turbo model with context-aware prompts matching the active window, returning the transcribed text.

### 8. Keyboard Typer (src/core/typer.py)
Performs high-speed text injection into the active window. It copies the text to the system clipboard, simulates a paste hotkey (`Ctrl+V` or `Cmd+V`), and instantly restores the original clipboard content. It automatically falls back to simulated character typing if clipboard interaction fails.

### 9. Storage Manager (src/core/storage.py)
Manages local SQLite connections, stores transcription text records with word counts and durations, computes WhisperFlow analytics, and enforces the rolling retention policy: 14 days for database records, 7 days for backup WAV files, and a hard 1 GB ceiling limit on audio storage size.

### 10. Search History Finder (src/ui/finder.py)
Implements the Apple-style Spotlight search bar window. Displays a queryable list of recent text transcriptions with context metadata and an audio player for listening to active backup files.

## Prerequisites

* Python 3.11 or newer
* A Groq API Key (available on console.groq.com)
* A working microphone

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/gandhaarjoshi412/voice-to-type.git
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
   * Edit .env and enter your Groq API key and preferred hotkeys:
     ```env
     GROQ_API_KEY=gsk_your_api_key_here
     HOTKEY=ctrl+shift+space
     SEARCH_HOTKEY=ctrl+alt+f
     ```

## Usage

Start the service from the terminal:
```bash
python src/main.py
```

* **Dictation**: Press `Ctrl + Shift + Space` or run `python trigger.py trigger` to start recording. Speak clearly, then press the hotkey again to stop. The service automatically transcribes and types the text into your active application.
* **Analytics Dashboard**: Click or double-click the System Tray icon, select **Open Analytics Dashboard** from the tray menu, or run `python trigger.py dashboard` to view your WhisperFlow-style metrics, 7-day trend chart, and top app distribution. Press `Esc` to minimize back to tray.
* **System Tray Controls**: Look at your system tray / notification area. The icon displays an active cyan microphone when idle and a glowing red indicator when recording. Right-click to access dictation controls, dashboard, finder, and live audio backup storage usage.
* **History Search**: Press `Ctrl + Shift + F`, select from the tray menu, or run `python trigger.py search` to open the Spotlight-style history search panel. Type queries to search past transcriptions, and click the **Play** button next to any item to listen to the recorded audio. Press `Esc` or the hotkey again to close the window.

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
