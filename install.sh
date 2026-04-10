#!/bin/bash
set -e

INSTALL_DIR="$HOME/.config/waybar-ycal"
SERVICE_DIR="$HOME/.config/systemd/user"

echo "Installing waybar-ycal..."

# Copy scripts to install dir
mkdir -p "$INSTALL_DIR"
cp popup.py bar.py toggle.sh sync.py "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/popup.py" "$INSTALL_DIR/bar.py" "$INSTALL_DIR/toggle.sh" "$INSTALL_DIR/sync.py"

# Install systemd user service
mkdir -p "$SERVICE_DIR"
sed "s|%h|$HOME|g" waybar-ycal.service > "$SERVICE_DIR/waybar-ycal.service"
systemctl --user daemon-reload
systemctl --user enable --now waybar-ycal.service

echo ""
echo "Done. Add this to your Waybar config:"
echo ""
echo '  "custom/gcal": {'
echo '    "exec": "~/.config/waybar-ycal/bar.py",'
echo '    "on-click": "~/.config/waybar-ycal/toggle.sh",'
echo '    "interval": 60,'
echo '    "return-type": "json",'
echo '    "tooltip": true'
echo '  }'
