#!/bin/bash
PID_FILE="$HOME/.cache/waybar-ycal/popup.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        kill -SIGUSR1 "$PID"
        exit 0
    fi
fi

# Not running — start the daemon in background
/usr/bin/python3 ~/.config/waybar-ycal/popup.py &
