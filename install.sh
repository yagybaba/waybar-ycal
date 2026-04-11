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
echo "Done! Next steps:"
echo ""
echo "1. Place your Google OAuth credentials at:"
echo "     $INSTALL_DIR/credentials.json"
echo ""
echo "2. Authenticate (opens browser once):"
echo "     python3 $INSTALL_DIR/sync.py"
echo ""
echo "3. Add to your Waybar config (config.jsonc):"
echo '     "custom/ycal": {'
echo '       "exec": "~/.config/waybar-ycal/bar.py",'
echo '       "on-click": "~/.config/waybar-ycal/toggle.sh",'
echo '       "interval": 60,'
echo '       "return-type": "json"'
echo '     }'
echo ""
echo "4. Add to your Waybar style.css:"
echo '     #custom-ycal { letter-spacing: 0.5px; }'
echo ""
echo "See README.md for full setup instructions."
