#!/usr/bin/env python3
import sys
import os

PIPE_PATH = "/tmp/antigravity_pipe"

def main():
    # Use first argument if provided, otherwise default to "TRIGGER"
    command = sys.argv[1].upper() if len(sys.argv) > 1 else "TRIGGER"

    if not os.path.exists(PIPE_PATH):
        print(f"Error: Named pipe at {PIPE_PATH} does not exist. Is the main service running?", file=sys.stderr)
        sys.exit(1)

    try:
        # Open the pipe in write mode and write the command
        with open(PIPE_PATH, 'w') as f:
            f.write(command)
        print(f"Successfully sent command '{command}' to pipe.")
    except Exception as e:
        print(f"Error writing to pipe: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
