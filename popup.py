#!/usr/bin/python3
from ctypes import CDLL
CDLL('libgtk4-layer-shell.so')
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gtk, GLib, Gtk4LayerShell, Pango, PangoCairo
import calendar
import datetime
import json
import math
import os
import signal
import subprocess
import sys
import threading
import tomllib

CACHE_FILE = os.path.expanduser('~/.cache/waybar-ycal/events.json')
PID_FILE = os.path.expanduser('~/.cache/waybar-ycal/popup.pid')
THEME_FILE = os.path.expanduser('~/.config/omarchy/current/theme/colors.toml')
CREDENTIALS_FILE = os.path.expanduser('~/.config/waybar-ycal/credentials.json')
TOKEN_FILE = os.path.expanduser('~/.cache/waybar-ycal/token.json')
SYNC_INTERVAL_SEC = 15 * 60  # 15 minutes

# Nerd Font family used for icon buttons (refresh + edit).
# Change this to match whichever Nerd Font you have installed.
NERD_FONT = "JetBrainsMonoNL Nerd Font, JetBrainsMono Nerd Font, Symbols Nerd Font"
SCOPES = [
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/tasks',
]


def _get_credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                return None
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
        with open(TOKEN_FILE, 'w') as f:
            f.write(creds.to_json())
    return creds


def _run_sync():
    """Fetch events from Google Calendar and write to cache. Runs in a thread."""
    try:
        from googleapiclient.discovery import build

        # Don't attempt sync if not authenticated — avoids opening browser on startup
        if not os.path.exists(TOKEN_FILE):
            return

        creds = _get_credentials()
        if creds is None:
            return

        service = build('calendar', 'v3', credentials=creds)
        today = datetime.date.today()
        time_min = (today - datetime.timedelta(days=60)).isoformat() + 'T00:00:00Z'
        time_max = (today + datetime.timedelta(days=365)).isoformat() + 'T23:59:59Z'

        # Fetch from all calendars
        cal_list = service.calendarList().list().execute()
        calendar_ids = [c['id'] for c in cal_list.get('items', [])]

        events_by_date = {}
        for cal_id in calendar_ids:
            try:
                result = service.events().list(
                    calendarId=cal_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy='startTime',
                    maxResults=500,
                ).execute()
            except Exception:
                continue
            for item in result.get('items', []):
                start = item['start']
                end = item['end']
                title = item.get('summary', '(no title)')
                if 'dateTime' in start:
                    # Timed event: show on start date with time range
                    dt = datetime.datetime.fromisoformat(start['dateTime'])
                    dt_end = datetime.datetime.fromisoformat(end['dateTime'])
                    label = f"{title} {dt.strftime('%H:%M')}-{dt_end.strftime('%H:%M')}"
                    events_by_date.setdefault(dt.date().isoformat(), []).append(label)
                else:
                    # All-day event: Google end date is exclusive, so expand across all days
                    d = datetime.date.fromisoformat(start['date'])
                    d_end = datetime.date.fromisoformat(end['date'])
                    while d < d_end:
                        events_by_date.setdefault(d.isoformat(), []).append(title)
                        d += datetime.timedelta(days=1)

        # Fetch Google Tasks with due dates
        tasks_service = build('tasks', 'v1', credentials=creds)
        task_lists = tasks_service.tasklists().list().execute()
        for tl in task_lists.get('items', []):
            try:
                tasks = tasks_service.tasks().list(
                    tasklist=tl['id'],
                    showCompleted=True,
                    showHidden=True,
                    maxResults=100,
                ).execute()
            except Exception:
                continue
            for task in tasks.get('items', []):
                due = task.get('due')
                title = task.get('title', '(no title)')
                completed = task.get('status') == 'completed'
                if due:
                    date_key = due[:10]  # YYYY-MM-DD
                    events_by_date.setdefault(date_key, []).append({
                        'type': 'task',
                        'id': task['id'],
                        'lid': tl['id'],
                        'title': title,
                        'done': completed,
                    })

        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        tmp = CACHE_FILE + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(events_by_date, f)
        os.replace(tmp, CACHE_FILE)

    except Exception as e:
        print(f'[gcal sync error] {e}', file=sys.stderr)


def sync_in_background():
    threading.Thread(target=_run_sync, daemon=True).start()
    return True  # Keep GLib timer repeating

def load_theme():
    defaults = {
        'foreground': '#ffcead',
        'background': '#060B1E',
        'accent': '#7d82d9',
    }
    try:
        with open(THEME_FILE, 'rb') as f:
            t = tomllib.load(f)
            return {**defaults, **t}
    except Exception:
        return defaults

def hex_to_rgb_float(hex_color):
    h = hex_color.lstrip('#')
    return int(h[0:2], 16)/255, int(h[2:4], 16)/255, int(h[4:6], 16)/255

def hex_to_rgba(hex_color, alpha):
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f'rgba({r}, {g}, {b}, {alpha})'

def load_events():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


class CalendarPopup(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.set_title("waybar-ycal")
        self.set_default_size(-1, -1)

        self.today = datetime.date.today()
        self.year = self.today.year
        self.month = self.today.month
        self.selected_date = self.today
        self.events = load_events()
        self._selected_btn = None
        self._cred_poll_timer = None

        self._setup_window()
        self._apply_css()  # sets self._refresh_fg
        self._build_ui()

    def _setup_window(self):
        self.set_decorated(False)
        self.set_resizable(False)
        self.connect("close-request", lambda *_: self._hide())

        Gtk4LayerShell.init_for_window(self)
        Gtk4LayerShell.set_layer(self, Gtk4LayerShell.Layer.TOP)
        Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.TOP, True)
        Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.LEFT, False)
        Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.RIGHT, False)
        Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.TOP, 4)
        Gtk4LayerShell.set_keyboard_mode(self, Gtk4LayerShell.KeyboardMode.ON_DEMAND)

        self._hide_timer = None
        self.connect('notify::is-active', self._on_active_changed)

        self.set_visible(False)

    def toggle(self):
        if self.get_visible():
            self._hide()
        else:
            self._show()

    def _show(self):
        self._apply_css()
        if not os.path.exists(CREDENTIALS_FILE):
            self._show_setup_screen('no_credentials')
            self.present()
            return
        if not os.path.exists(TOKEN_FILE):
            self._show_setup_screen('no_token')
            self.present()
            return
        self._reset_to_today()
        self._show_calendar()
        self.present()

    def _reset_to_today(self):
        """Reset calendar state to today and reload events from cache."""
        self.today = datetime.date.today()
        self.year = self.today.year
        self.month = self.today.month
        self.selected_date = self.today
        self.events = load_events()

    def _show_calendar(self):
        """Switch from setup screen (or initial state) to the calendar view."""
        self.set_child(self.main_box)
        self._build_grid()
        self.month_label.set_markup(
            f"<b>{datetime.date(self.year, self.month, 1).strftime('%B %Y').upper()}</b>"
        )
        self._update_day_panel(self.today)

    def _make_setup_card(self, title_text, msg_text):
        """Build the shared card widget used by both setup screens."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.add_css_class('popup-bg')
        box.set_size_request(360, -1)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)

        title = Gtk.Label(label=title_text)
        title.add_css_class('setup-title')

        msg = Gtk.Label(label=msg_text)
        msg.add_css_class('setup-msg')
        msg.set_justify(Gtk.Justification.CENTER)

        box.append(title)
        box.append(msg)
        return box

    def _show_setup_screen(self, state):
        """Show the appropriate setup screen and replace the window child."""
        # Force window to shrink-wrap to new content size
        self.set_default_size(-1, -1)

        # Cancel any running credentials poll
        if self._cred_poll_timer is not None:
            GLib.source_remove(self._cred_poll_timer)
            self._cred_poll_timer = None

        if state == 'no_credentials':
            short_path = CREDENTIALS_FILE.replace(os.path.expanduser('~'), '~')
            box = self._make_setup_card(
                "Connect Google Calendar",
                f"Place your OAuth credentials at:\n{short_path}\n\nWaiting for file...",
            )
            open_btn = Gtk.Button(label="Open Google Cloud Console")
            open_btn.add_css_class('add-btn')
            open_btn.connect("clicked", self._on_open_console_clicked)
            box.append(open_btn)

            # Poll every 2s — auto-advance when credentials.json appears
            def poll_for_credentials():
                if os.path.exists(CREDENTIALS_FILE):
                    self._cred_poll_timer = None
                    self._show_setup_screen('no_token')
                    return False
                return True
            self._cred_poll_timer = GLib.timeout_add(2000, poll_for_credentials)

        elif state == 'no_token':
            box = self._make_setup_card(
                "Connect Google Account",
                "Click below to open a browser and\nauthenticate with Google.",
            )
            auth_btn = Gtk.Button(label="Authenticate")
            auth_btn.add_css_class('add-btn')
            auth_btn.connect("clicked", self._on_auth_clicked)
            box.append(auth_btn)

        self._setup_box = box
        self.set_child(box)

    def _on_open_console_clicked(self, btn):
        os.makedirs(os.path.dirname(CREDENTIALS_FILE), exist_ok=True)
        btn.set_sensitive(False)
        btn.set_label("Opened — place credentials.json and wait...")
        subprocess.Popen(['xdg-open', 'https://console.cloud.google.com/apis/credentials'])

    def _on_auth_clicked(self, btn):
        btn.set_sensitive(False)
        btn.set_label("Opening browser...")
        def do_auth():
            try:
                _get_credentials()
                _run_sync()
                def after():
                    self._reset_to_today()
                    self._show_calendar()
                    return False
                GLib.idle_add(after)
            except Exception as e:
                def after_err():
                    btn.set_label("Failed — try again")
                    btn.set_sensitive(True)
                    return False
                GLib.idle_add(after_err)
        threading.Thread(target=do_auth, daemon=True).start()

    def _on_active_changed(self, win, _):
        if win.is_active():
            if self._hide_timer:
                GLib.source_remove(self._hide_timer)
                self._hide_timer = None
        else:
            if self._hide_timer is None:
                self._hide_timer = GLib.timeout_add(150, self._hide)

    def _hide(self):
        self._hide_timer = None
        if self._cred_poll_timer is not None:
            GLib.source_remove(self._cred_poll_timer)
            self._cred_poll_timer = None
        self.set_visible(False)
        return False

    def _build_ui(self):
        # Outer horizontal box: calendar left, day panel right
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.main_box.add_css_class('popup-bg')
        self.set_child(self.main_box)

        # ── Left: calendar ──────────────────────────────────────
        self.left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.left_box.set_size_request(220, -1)
        self.main_box.append(self.left_box)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        header.set_size_request(-1, 32)
        prev_btn = Gtk.Button(label="‹")
        prev_btn.connect("clicked", lambda _: self._navigate(-1))

        self.month_label = Gtk.Label()
        self.month_label.set_markup(
            f"<b>{datetime.date(self.year, self.month, 1).strftime('%B %Y').upper()}</b>"
        )
        self.month_label.set_hexpand(True)

        next_btn = Gtk.Button(label="›")
        next_btn.connect("clicked", lambda _: self._navigate(1))

        self._refresh_angle = 0.0
        self._refresh_spin_timer = None
        self._refresh_da = Gtk.DrawingArea()
        self._refresh_da.set_size_request(20, 20)
        self._refresh_da.set_draw_func(self._draw_refresh_icon)

        self.refresh_btn = Gtk.Button()
        self.refresh_btn.set_child(self._refresh_da)
        self.refresh_btn.set_size_request(28, 28)
        self.refresh_btn.set_valign(Gtk.Align.CENTER)
        self.refresh_btn.add_css_class('refresh-btn')
        self.refresh_btn.connect("clicked", self._on_refresh_clicked)

        header.append(prev_btn)
        header.append(self.month_label)
        header.append(next_btn)
        header.append(self.refresh_btn)
        self.left_box.append(header)

        self.grid = None
        self._build_grid()

        # ── Divider ──────────────────────────────────────────────
        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep.add_css_class('panel-divider')
        self.main_box.append(sep)

        # ── Right: day panel ─────────────────────────────────────
        self.right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.right_box.set_size_request(180, -1)
        self.right_box.add_css_class('day-panel')
        self.main_box.append(self.right_box)

        # Date heading
        self.day_label = Gtk.Label()
        self.day_label.set_halign(Gtk.Align.START)
        self.day_label.add_css_class('day-heading')
        self.right_box.append(self.day_label)

        # Scrollable event list
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        self.right_box.append(scroll)

        self.events_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        scroll.set_child(self.events_box)

        # Buttons at the bottom
        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_row.set_size_request(-1, 32)
        add_btn = Gtk.Button(label="+ Add event")
        add_btn.add_css_class('add-btn')
        add_btn.set_hexpand(True)
        add_btn.connect("clicked", self._on_add_clicked)
        edit_btn = Gtk.Button()
        edit_lbl = Gtk.Label(label="\uf044")
        edit_lbl.set_halign(Gtk.Align.CENTER)
        edit_lbl.set_valign(Gtk.Align.CENTER)
        edit_btn.set_child(edit_lbl)
        edit_btn.set_size_request(36, -1)
        edit_btn.set_hexpand(False)
        edit_btn.add_css_class('add-btn')
        edit_btn.add_css_class('nerd')
        edit_btn.connect("clicked", self._on_edit_clicked)
        btn_row.append(add_btn)
        btn_row.append(edit_btn)
        self.right_box.append(btn_row)

        self._update_day_panel(self.today)

    def _build_grid(self):
        if self.grid is not None:
            self.left_box.remove(self.grid)
        self._selected_btn = None

        self.grid = Gtk.Grid()
        self.grid.set_row_spacing(4)
        self.grid.set_column_spacing(0)
        self.grid.set_column_homogeneous(True)

        day_names = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
        for col, name in enumerate(day_names):
            lbl = Gtk.Label(label=name)
            lbl.add_css_class('weekday')
            if col >= 5:
                lbl.add_css_class('weekend-label')
            lbl.set_size_request(28, 18)
            self.grid.attach(lbl, col, 0, 1, 1)

        first = datetime.date(self.year, self.month, 1)
        start = first - datetime.timedelta(days=first.weekday())
        last = datetime.date(self.year, self.month, calendar.monthrange(self.year, self.month)[1])
        weeks = math.ceil((first.weekday() + last.day) / 7)
        total_days = weeks * 7

        for i in range(total_days):
            date = start + datetime.timedelta(days=i)
            day_events = self.events.get(date.isoformat(), [])

            overlay = Gtk.Overlay()
            overlay.set_size_request(28, 28)

            number = Gtk.Label(label=str(date.day))
            number.set_halign(Gtk.Align.CENTER)
            number.set_valign(Gtk.Align.CENTER)
            overlay.set_child(number)

            has_events = any(isinstance(e, str) for e in day_events)
            has_tasks = any(isinstance(e, dict) and not e.get('done') for e in day_events)

            if has_events or has_tasks:
                bar_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
                bar_box.set_halign(Gtk.Align.CENTER)
                bar_box.set_valign(Gtk.Align.END)
                bar_box.set_margin_bottom(4)
                w = 8 if (has_events and has_tasks) else 18
                if has_tasks:
                    task_bar = Gtk.Box()
                    task_bar.add_css_class('task-bar')
                    task_bar.set_size_request(w, 2)
                    bar_box.append(task_bar)
                if has_events:
                    bar = Gtk.Box()
                    bar.add_css_class('event-bar')
                    bar.set_size_request(w, 2)
                    bar_box.append(bar)
                overlay.add_overlay(bar_box)

            btn = Gtk.Button()
            btn.set_child(overlay)
            btn.set_size_request(28, 28)
            btn.date = date
            btn.connect("clicked", self._on_day_clicked)

            if date.month != self.month:
                btn.add_css_class("other-month")
            if date.weekday() >= 5:
                btn.add_css_class("weekend")
            if date == self.today:
                btn.add_css_class("today")
            if date == self.selected_date:
                btn.add_css_class("selected")
                self._selected_btn = btn

            row = i // 7 + 1
            col = i % 7
            self.grid.attach(btn, col, row, 1, 1)

        self.left_box.append(self.grid)

    def _on_day_clicked(self, btn):
        if self._selected_btn is not None:
            self._selected_btn.remove_css_class('selected')
        self._selected_btn = btn
        btn.add_css_class('selected')
        self.selected_date = btn.date
        self._update_day_panel(btn.date)

    def _make_event_row(self, ev):
        """Build a single event or task row for the day panel."""
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        if isinstance(ev, dict):
            # Task row: colored dot, title, done toggle button
            done = ev.get('done', False)
            dot = Gtk.Label(label="•")
            dot.add_css_class('done-dot' if done else 'task-dot')
            name = Gtk.Label(label=ev['title'])
            name.set_hexpand(True)
            name.set_ellipsize(Pango.EllipsizeMode.END)
            name.set_tooltip_text(ev['title'])
            name.add_css_class('event-name')
            toggle = Gtk.Button(label="✓")
            toggle.add_css_class('done-toggle')
            toggle.add_css_class('done-toggle-active' if done else 'done-toggle-inactive')
            toggle.connect("clicked", self._on_task_toggle, ev)
            row.append(dot)
            row.append(name)
            row.append(toggle)
        else:
            # Event row: accent dot + title
            dot = Gtk.Label(label="•")
            dot.add_css_class('event-dot')
            name = Gtk.Label(label=ev)
            name.set_ellipsize(Pango.EllipsizeMode.END)
            name.set_tooltip_text(ev)
            name.add_css_class('event-name')
            row.append(dot)
            row.append(name)

        return row

    def _update_day_panel(self, date):
        # Update heading
        if date == self.today:
            heading = f"<b>Today</b>  <span alpha='60%'>{date.strftime('%d %b').lstrip('0')}</span>"
        else:
            heading = f"<b>{date.strftime('%A')}</b>  <span alpha='60%'>{date.strftime('%d %b').lstrip('0')}</span>"
        self.day_label.set_markup(heading)

        # Clear old events
        while True:
            child = self.events_box.get_first_child()
            if child is None:
                break
            self.events_box.remove(child)

        # Sort order: undone tasks (0) → done tasks (1) → events (2)
        day_events = sorted(
            self.events.get(date.isoformat(), []),
            key=lambda e: 0 if (isinstance(e, dict) and not e.get('done')) else (1 if isinstance(e, dict) else 2)
        )
        if day_events:
            for ev in day_events:
                self.events_box.append(self._make_event_row(ev))
        else:
            empty = Gtk.Label(label="No events")
            empty.add_css_class('no-events')
            empty.set_halign(Gtk.Align.START)
            self.events_box.append(empty)

    def _on_add_clicked(self, _):
        d = self.selected_date
        url = (f"https://calendar.google.com/calendar/r/eventedit"
               f"?dates={d.strftime('%Y%m%d')}/{d.strftime('%Y%m%d')}")
        subprocess.Popen(['xdg-open', url])
        self._hide()

    def _on_edit_clicked(self, _):
        d = self.selected_date
        url = f"https://calendar.google.com/calendar/r/day/{d.year}/{d.month}/{d.day}"
        subprocess.Popen(['xdg-open', url])
        self._hide()

    def _on_task_toggle(self, btn, task):
        btn.set_sensitive(False)
        btn.add_css_class('pulsing')
        def do_toggle():
            try:
                from googleapiclient.discovery import build
                creds = _get_credentials()
                if creds is None:
                    return
                service = build('tasks', 'v1', credentials=creds)
                new_status = 'needsAction' if task.get('done') else 'completed'
                service.tasks().patch(
                    tasklist=task['lid'],
                    task=task['id'],
                    body={'status': new_status},
                ).execute()
                _run_sync()
                def after():
                    self.events = load_events()
                    self._build_grid()
                    self._update_day_panel(self.selected_date)
                    return False
                GLib.idle_add(after)
            except Exception as e:
                print(f'[task toggle error] {e}', file=sys.stderr)
                def after_err():
                    btn.remove_css_class('pulsing')
                    btn.set_sensitive(True)
                    return False
                GLib.idle_add(after_err)
        threading.Thread(target=do_toggle, daemon=True).start()

    def _draw_refresh_icon(self, da, ctx, width, height):
        """Cairo draw callback. Renders the Nerd Font refresh glyph, rotated when spinning.
        Uses ink extents for pixel-perfect centering regardless of font metrics."""
        r, g, b = self._refresh_fg

        if not hasattr(self, '_refresh_layout'):
            self._refresh_layout = PangoCairo.create_layout(ctx)
            font_name = NERD_FONT.split(',')[0].strip()
            self._refresh_layout.set_font_description(
                Pango.FontDescription.from_string(f"{font_name} 12"))
            self._refresh_layout.set_text("\uf021")
            ink, _ = self._refresh_layout.get_pixel_extents()
            self._refresh_ink = ink
        else:
            PangoCairo.update_layout(ctx, self._refresh_layout)

        ink = self._refresh_ink
        x = (width - ink.width) / 2 - ink.x
        y = (height - ink.height) / 2 - ink.y

        if self._refresh_angle != 0.0:
            ctx.translate(width / 2, height / 2)
            ctx.rotate(self._refresh_angle)
            ctx.translate(-width / 2, -height / 2)

        ctx.set_source_rgba(r, g, b, 1.0)
        ctx.move_to(x, y)
        PangoCairo.show_layout(ctx, self._refresh_layout)

    def _on_refresh_clicked(self, _):
        self.refresh_btn.set_sensitive(False)

        def tick():
            self._refresh_angle += 0.15
            self._refresh_da.queue_draw()
            return not self.refresh_btn.get_sensitive()
        self._refresh_spin_timer = GLib.timeout_add(16, tick)

        def do_sync():
            _run_sync()
            def after():
                if self._refresh_spin_timer:
                    GLib.source_remove(self._refresh_spin_timer)
                    self._refresh_spin_timer = None
                self._refresh_angle = 0.0
                self._refresh_da.queue_draw()
                self.events = load_events()
                self._build_grid()
                self._update_day_panel(self.selected_date)
                self.refresh_btn.set_sensitive(True)
                return False
            GLib.idle_add(after)
        threading.Thread(target=do_sync, daemon=True).start()

    def _navigate(self, delta):
        self.month += delta
        if self.month < 1:
            self.month = 12
            self.year -= 1
        elif self.month > 12:
            self.month = 1
            self.year += 1
        self.month_label.set_markup(
            f"<b>{datetime.date(self.year, self.month, 1).strftime('%B %Y').upper()}</b>"
        )
        self._build_grid()

    def _apply_css(self):
        t = load_theme()
        fg = t['foreground']
        bg = t['background']
        accent = t['accent']
        red = '#ff5555'
        self._refresh_fg = hex_to_rgb_float(fg)

        css = f"""
      window {{
          background: transparent;
      }}
      .popup-bg {{
          background: {hex_to_rgba(bg, 0.92)};
          border-radius: 12px;
          border: 1px solid {hex_to_rgba(accent, 0.35)};
          padding: 10px;
      }}
      button {{
          background: transparent;
          border: 1px solid transparent;
          border-radius: 10px;
          color: {fg};
          font-size: 11px;
          font-weight: 500;
      }}
      button:hover {{
          background: rgba(255, 255, 255, 0.07);
      }}
      button:active {{
          background: rgba(255, 255, 255, 0.18);
          transition: background 50ms;
      }}
      button:focus,
      button:focus-visible {{
          outline: none;
          box-shadow: none;
      }}
      label {{
          color: {fg};
      }}
      .weekday {{
          color: {hex_to_rgba(fg, 0.4)};
          font-size: 11px;
      }}
      .other-month {{
          opacity: 0.2;
      }}
      .other-month:hover {{
          background: transparent;
      }}
      .weekend {{
          background: {hex_to_rgba(fg, 0.04)};
          border-radius: 10px;
      }}
      .weekend-label {{
          color: {hex_to_rgba(accent, 0.6)};
      }}
      .today {{
          background: {hex_to_rgba(accent, 0.5)};
          border-radius: 10px;
          font-weight: bold;
      }}
      .today:hover {{
          background: {hex_to_rgba(accent, 0.65)};
      }}
      .selected {{
          border: 1px solid {hex_to_rgba(accent, 0.8)};
          border-radius: 10px;
      }}
      .today.selected {{
          border: 1px solid {fg};
      }}
      .event-bar {{
          background: {hex_to_rgba(accent, 0.9)};
          border-radius: 2px;
          min-height: 2px;
      }}
      .today .event-bar {{
          background: {fg};
      }}
      .panel-divider {{
          background: {hex_to_rgba(accent, 0.2)};
          min-width: 1px;
          margin: 0 8px;
      }}
      .day-panel {{
          padding: 2px 4px 2px 0;
      }}
      .day-heading {{
          font-size: 11px;
          margin-bottom: 4px;
      }}
      .event-dot {{
          color: {hex_to_rgba(accent, 0.9)};
          font-size: 10px;
      }}
      .event-name {{
          font-size: 11px;
          color: {fg};
      }}
      .task-bar {{
          background: {hex_to_rgba(red, 0.9)};
          border-radius: 2px;
          min-height: 2px;
      }}
      .task-dot {{
          color: {hex_to_rgba(red, 0.9)};
          font-size: 10px;
      }}
      .done-dot {{
          color: {hex_to_rgba('#50fa7b', 0.9)};
          font-size: 10px;
      }}
      .done-toggle {{
          font-size: 10px;
          min-width: 18px;
          min-height: 18px;
          padding: 0;
          border-radius: 4px;
      }}
      .done-toggle-inactive {{
          border: 1px solid {hex_to_rgba(fg, 0.2)};
          color: transparent;
      }}
      .done-toggle-inactive:hover {{
          border-color: {hex_to_rgba('#50fa7b', 0.6)};
          color: {hex_to_rgba('#50fa7b', 0.6)};
      }}
      .done-toggle-active {{
          border: 1px solid {hex_to_rgba('#50fa7b', 0.6)};
          color: {hex_to_rgba('#50fa7b', 0.9)};
          background: {hex_to_rgba('#50fa7b', 0.15)};
      }}
      .no-events {{
          font-size: 11px;
          color: {hex_to_rgba(fg, 0.35)};
          font-style: italic;
      }}
      .add-btn {{
          background: {hex_to_rgba(accent, 0.15)};
          border: 1px solid {hex_to_rgba(accent, 0.35)};
          border-radius: 8px;
          color: {fg};
          font-size: 11px;
          padding: 4px 0;
          margin-top: 4px;
      }}
      .add-btn:hover {{
          background: {hex_to_rgba(accent, 0.28)};
      }}
      .refresh-btn {{
          background: {hex_to_rgba(accent, 0.15)};
          border: 1px solid {hex_to_rgba(accent, 0.35)};
          color: {fg};
          font-size: 15px;
          padding: 0;
      }}
      .refresh-btn:hover {{
          background: {hex_to_rgba(accent, 0.28)};
      }}
      .add-btn.nerd {{
          font-family: "{NERD_FONT}";
          font-size: 13px;
          padding: 0;
      }}
      .add-btn.nerd label {{
          all: unset;
          font-family: "{NERD_FONT}";
          font-size: 13px;
          color: {fg};
          margin-left: -2px;
      }}
      @keyframes pulse {{
          0%, 100% {{ opacity: 1; }}
          50%       {{ opacity: 0.25; }}
      }}
      .pulsing {{
          animation: pulse 0.6s ease-in-out infinite;
      }}
      .setup-icon {{
          font-family: "{NERD_FONT}";
          font-size: 32px;
          color: {hex_to_rgba(accent, 0.8)};
          margin-bottom: 4px;
      }}
      .setup-title {{
          font-size: 14px;
          font-weight: bold;
          color: {fg};
          margin-top: 8px;
          margin-bottom: 6px;
      }}
      .setup-msg {{
          font-size: 11px;
          color: {hex_to_rgba(fg, 0.6)};
          margin-bottom: 12px;
      }}
      """.encode()
        if not hasattr(self, '_css_provider'):
            self._css_provider = Gtk.CssProvider()
            Gtk.StyleContext.add_provider_for_display(
                self.get_display(), self._css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
        self._css_provider.load_from_data(css)


win = None

def on_activate(app):
    global win
    win = CalendarPopup(app)
    os.makedirs(os.path.dirname(PID_FILE), exist_ok=True)
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, lambda: win.toggle() or True)
    # Sync immediately on start, then every 15 minutes
    sync_in_background()
    GLib.timeout_add_seconds(SYNC_INTERVAL_SEC, sync_in_background)


app = Gtk.Application(application_id="com.waybar.ycal")
app.connect("activate", on_activate)

try:
    app.run(None)
finally:
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)
