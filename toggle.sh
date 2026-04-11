#!/bin/bash
PID_FILE="$HOME/.cache/waybar-ycal/popup.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        kill -SIGUSR1 "$PID"
        exit 0
    fi
fi

# Not running — restart via systemd if enabled, else launch directly
if systemctl --user is-enabled waybar-ycal.service &>/dev/null; then
    systemctl --user start waybar-ycal.service
else
    python3 "$HOME/.config/waybar-ycal/popup.py" &
fi
