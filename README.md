# waybar-ycal

A Google Calendar + Google Tasks popup widget for [Waybar](https://github.com/Alexays/Waybar) on Wayland.

- Click the bar module to open/close the popup
- Browse months, see events and tasks per day
- Toggle tasks complete/incomplete inline
- Auto-syncs every 15 minutes, manual refresh button available
- Themed from your system colors (supports [Omarchy](https://github.com/basecamp/omarchy), falls back to built-in defaults)

## Requirements

### System packages

**Arch Linux:**
```bash
sudo pacman -S python-gobject gtk4 gtk4-layer-shell python-google-auth python-google-auth-oauthlib
yay -S python-google-api-python-client  # or paru
```

**Ubuntu/Debian:**
```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 \
    python3-google-auth python3-google-auth-oauthlib
pip install --user google-api-python-client gtk4-layer-shell
```

> **gtk4-layer-shell** is required. On Ubuntu it may need to be built from source or installed via pip.

### Nerd Font

The refresh (``) and edit (``) icons require a [Nerd Font](https://www.nerdfonts.com/).
Any Nerd Font works — just update `NERD_FONT` at the top of `popup.py` to match your font name.

The bar module uses the `󰃭` icon (Nerd Font codepoint `U+F00ED`).

## Google Cloud setup

You need OAuth2 credentials from Google Cloud. This is a one-time setup.

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or use an existing one)
3. **Enable APIs:** search and enable both:
   - Google Calendar API
   - Google Tasks API
4. Go to **APIs & Services → OAuth consent screen**
   - Choose **External**, fill in app name (e.g. `waybar-ycal`)
   - Under **Test users**, add your Google account email
5. Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID**
   - Application type: **Desktop app**
   - Download the JSON file
6. Place the downloaded file at:
   ```
   ~/.config/waybar-ycal/credentials.json
   ```

## Installation

```bash
git clone https://github.com/yourname/waybar-ycal
cd waybar-ycal
./install.sh
```

The installer copies scripts, installs a systemd user service, and starts the daemon.

### First-time auth

After placing `credentials.json`, run:
```bash
python3 ~/.config/waybar-ycal/sync.py
```

A browser window will open — log in and allow access. The token is saved to `~/.cache/waybar-ycal/token.json` and refreshed automatically after that.

## Waybar config

Add to your `config.jsonc`:
```jsonc
"custom/ycal": {
    "exec": "~/.config/waybar-ycal/bar.py",
    "on-click": "~/.config/waybar-ycal/toggle.sh",
    "interval": 60,
    "return-type": "json"
}
```

Add to your modules list where you want it:
```jsonc
"modules-center": ["clock", "custom/ycal"]
```

### style.css (optional)

```css
#custom-ycal {
    letter-spacing: 0.5px;
}
```

The popup window is self-styled and does not depend on Waybar's CSS.

## Theming

If you use [Omarchy](https://github.com/basecamp/omarchy), the popup reads colors from:
```
~/.config/omarchy/current/theme/colors.toml
```

Expected keys: `foreground`, `background`, `accent`. Falls back to built-in dark defaults if the file is missing.

Task indicators are always red (`#ff5555`) and completed task dots are green (`#50fa7b`) — hardcoded by design to stay visible across themes.

## How it works

| File | Role |
|------|------|
| `popup.py` | GTK4 daemon — renders the popup, handles Google API calls |
| `bar.py` | Waybar module — prints JSON with icon + date |
| `sync.py` | Standalone auth/sync script — use for initial login |
| `toggle.sh` | Sends SIGUSR1 to daemon to show/hide popup |
| `waybar-ycal.service` | Systemd user service to keep daemon running |

The daemon syncs on startup, then every 15 minutes. Click the refresh button in the popup header for an immediate sync.
