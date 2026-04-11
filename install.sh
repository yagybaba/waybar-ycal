#!/bin/bash
set -e

# Run from the repo directory regardless of where the script is called from
cd "$(dirname "$0")"

INSTALL_DIR="$HOME/.config/waybar-ycal"
SERVICE_DIR="$HOME/.config/systemd/user"

echo "Installing waybar-ycal..."

# Copy scripts to install dir
mkdir -p "$INSTALL_DIR"
cp popup.py bar.py toggle.sh "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/popup.py" "$INSTALL_DIR/bar.py" "$INSTALL_DIR/toggle.sh"

# Install systemd user service
mkdir -p "$SERVICE_DIR"
cat > "$SERVICE_DIR/waybar-ycal.service" << EOF
[Unit]
Description=Waybar Google Calendar popup daemon
After=graphical-session.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 $INSTALL_DIR/popup.py
Restart=on-failure
RestartSec=3

[Install]
WantedBy=graphical-session.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now waybar-ycal.service

echo ""
echo "Done! Next steps:"
echo ""
echo "1. Place your Google OAuth credentials at:"
echo "     $INSTALL_DIR/credentials.json"
echo ""
echo "2. Add to your Waybar config (config.jsonc):"
echo '     "custom/ycal": {'
echo '       "exec": "'"$INSTALL_DIR"'/bar.py",'
echo '       "on-click": "'"$INSTALL_DIR"'/toggle.sh",'
echo '       "interval": 60,'
echo '       "return-type": "json"'
echo '     }'
echo ""
echo "3. Open the popup — it will guide you through authentication."
echo ""
echo "See README.md for full setup instructions."
