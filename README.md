# waybar-ycal

A Google Calendar + Google Tasks popup widget for [Waybar](https://github.com/Alexays/Waybar) on Wayland.

- Click the bar module to open/close the popup
- Browse months, see events and tasks per day
- Toggle tasks complete/incomplete inline
- Auto-syncs every 15 minutes, manual refresh button available
- Themed from your system colors (supports [Omarchy](https://github.com/basecamp/omarchy), falls back to built-in defaults)

## Usage philosophy

This widget treats **Google Tasks** and **Google Calendar events** as two distinct things:

- **Tasks** (red indicator) — important deadlines only. Things that *must* happen by a specific date. The red color makes them stand out so you never miss them.
- **Events** (accent color indicator) — everything else. Meetings, plans, reminders, anything time-based.

The separation keeps the calendar clean: if you see red, it matters.

## Installation

### Arch Linux (AUR) — recommended

```bash
yay -S waybar-ycal-git
```

The package installs scripts to `/usr/share/waybar-ycal/` and registers the systemd user service. Updates automatically with `yay -Syu`.

After installing, enable the daemon:
```bash
systemctl --user enable --now waybar-ycal.service
```

### Manual (other distros)

```bash
git clone https://github.com/yagybaba/waybar-ycal
cd waybar-ycal
./install.sh
```

---

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

   You can create `~/.config/waybar-ycal/` manually or let the popup create it for you (see First-time setup below).

## First-time setup

Open the popup by clicking the bar module. If `credentials.json` is missing, the popup will guide you through placing it and offer to create the config folder. Once the file is in place, it will show a **Connect Google Account** screen — click **Authenticate**, log in through the browser, and the popup fetches your calendars and tasks automatically. The token is saved to `~/.cache/waybar-ycal/token.json` and refreshed automatically after that.

## Waybar config

Add to your `config.jsonc`:

**AUR install:**
```jsonc
"custom/ycal": {
    "exec": "/usr/share/waybar-ycal/bar.py",
    "on-click": "/usr/share/waybar-ycal/toggle.sh",
    "interval": 60,
    "return-type": "json"
}
```

**Manual install:**
```jsonc
"custom/ycal": {
    "exec": "~/.config/waybar-ycal/bar.py",
    "on-click": "~/.config/waybar-ycal/toggle.sh",
    "interval": 60,
    "return-type": "json"
}
```

Add to your modules list where you want it (it includes a clock, so no need for a separate `clock` module):
```jsonc
"modules-center": ["custom/ycal"]
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
| `toggle.sh` | Sends SIGUSR1 to daemon to show/hide popup |
| `waybar-ycal.service` | Systemd user service to keep daemon running |

The daemon syncs on startup, then every 15 minutes. Click the refresh button in the popup header for an immediate sync.
