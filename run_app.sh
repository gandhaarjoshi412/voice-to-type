#!/bin/bash
set -e

PROJECT_DIR="/home/gandhaar/project/projects/voice_to_type_project"
cd "$PROJECT_DIR"

# Clean up stale named pipe if left over from improper shutdown
rm -f /tmp/antigravity_pipe

# Select virtual environment python binary
if [ -x "$PROJECT_DIR/.venv_linux/bin/python" ]; then
    PYTHON_EXEC="$PROJECT_DIR/.venv_linux/bin/python"
elif [ -x "$PROJECT_DIR/.venv/bin/python" ]; then
    PYTHON_EXEC="$PROJECT_DIR/.venv/bin/python"
else
    PYTHON_EXEC="python3"
fi

# Ensure GUI and sound services are ready
sleep 2

# Launch the service directly replacing the shell
exec "$PYTHON_EXEC" src/main.py
