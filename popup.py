#!/usr/bin/python3
from ctypes import CDLL
CDLL('libgtk4-layer-shell.so')
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gtk, GLib, Gtk4LayerShell
import calendar
import datetime
import json
import math
import os
import signal
import subprocess
import threading
import tomllib

CACHE_FILE = os.path.expanduser('~/.cache/waybar-ycal/events.json')
PID_FILE = os.path.expanduser('~/.cache/waybar-ycal/popup.pid')
THEME_FILE = os.path.expanduser('~/.config/omarchy/current/theme/colors.toml')
CREDENTIALS_FILE = os.path.expanduser('~/.config/waybar-ycal/credentials.json')
TOKEN_FILE = os.path.expanduser('~/.cache/waybar-ycal/token.json')
SYNC_INTERVAL_SEC = 15 * 60  # 15 minutes


def _run_sync():
    """Fetch events from Google Calendar and write to cache. Runs in a thread."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        SCOPES = [
            'https://www.googleapis.com/auth/calendar.readonly',
            'https://www.googleapis.com/auth/tasks',
        ]

        creds = None
        if os.path.exists(TOKEN_FILE):
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(CREDENTIALS_FILE):
                    return  # No credentials, skip silently
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                creds = flow.run_local_server(port=0)
            os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
            with open(TOKEN_FILE, 'w') as f:
                f.write(creds.to_json())

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
                    dt = datetime.datetime.fromisoformat(start['dateTime'])
                    dt_end = datetime.datetime.fromisoformat(end['dateTime'])
                    label = f"{title} {dt.strftime('%H:%M')}-{dt_end.strftime('%H:%M')}"
                    date_key = dt.date().isoformat()
                else:
                    label = title
                    date_key = start['date']
                events_by_date.setdefault(date_key, []).append(label)

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
        with open(CACHE_FILE, 'w') as f:
            json.dump(events_by_date, f)

    except Exception as e:
        import sys
        print(f'[gcal sync error] {e}', file=sys.stderr)


def sync_in_background():
    threading.Thread(target=_run_sync, daemon=True).start()
    return True  # Keep GLib timer repeating

def load_theme():
    defaults = {
        'foreground': '#ffcead',
        'background': '#060B1E',
        'accent': '#7d82d9',
        'color1': '#f85525',
    }
    try:
        with open(THEME_FILE, 'rb') as f:
            t = tomllib.load(f)
            return {**defaults, **t}
    except Exception:
        return defaults

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

        self._setup_window()
        self._apply_css()
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
        self.today = datetime.date.today()
        self.year = self.today.year
        self.month = self.today.month
        self.selected_date = self.today
        self.events = load_events()
        self._apply_css()
        self._build_grid()
        self.month_label.set_markup(
            f"<b>{datetime.date(self.year, self.month, 1).strftime('%B %Y').upper()}</b>"
        )
        self._update_day_panel(self.today)
        self.present()

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
        prev_btn = Gtk.Button(label="‹")
        prev_btn.connect("clicked", lambda _: self._navigate(-1))

        self.month_label = Gtk.Label()
        self.month_label.set_markup(
            f"<b>{datetime.date(self.year, self.month, 1).strftime('%B %Y').upper()}</b>"
        )
        self.month_label.set_hexpand(True)

        next_btn = Gtk.Button(label="›")
        next_btn.connect("clicked", lambda _: self._navigate(1))

        self.refresh_btn = Gtk.Button()
        refresh_lbl = Gtk.Label(label="\uf021")
        refresh_lbl.set_halign(Gtk.Align.CENTER)
        refresh_lbl.set_valign(Gtk.Align.CENTER)
        self.refresh_btn.set_child(refresh_lbl)
        self.refresh_btn.set_size_request(28, 28)
        self.refresh_btn.set_hexpand(False)
        self.refresh_btn.set_vexpand(False)
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
        add_btn = Gtk.Button(label="+ Add event")
        add_btn.add_css_class('add-btn')
        add_btn.set_hexpand(True)
        add_btn.connect("clicked", self._on_add_clicked)
        edit_btn = Gtk.Button()
        edit_lbl = Gtk.Label(label="\uf044")
        edit_lbl.set_halign(Gtk.Align.CENTER)
        edit_lbl.set_valign(Gtk.Align.CENTER)
        edit_btn.set_child(edit_lbl)
        edit_btn.set_size_request(28, 28)
        edit_btn.set_hexpand(False)
        edit_btn.set_vexpand(False)
        edit_btn.set_valign(Gtk.Align.CENTER)
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

            if day_events:
                btn.add_css_class('has-events')
            if date.month != self.month:
                btn.add_css_class("other-month")
            if date.weekday() >= 5:
                btn.add_css_class("weekend")
            if date == self.today:
                btn.add_css_class("today")
            if date == self.selected_date:
                btn.add_css_class("selected")

            row = i // 7 + 1
            col = i % 7
            self.grid.attach(btn, col, row, 1, 1)

        self.left_box.append(self.grid)

    def _on_day_clicked(self, btn):
        self.selected_date = btn.date
        self._update_day_panel(btn.date)
        # Rebuild grid to update selected highlight
        self._build_grid()

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

        day_events = sorted(
            self.events.get(date.isoformat(), []),
            key=lambda e: 0 if isinstance(e, dict) else 1
        )
        if day_events:
            for ev in day_events:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                if isinstance(ev, dict):
                    done = ev.get('done', False)
                    dot = Gtk.Label(label="•")
                    dot.add_css_class('done-dot' if done else 'task-dot')
                    name = Gtk.Label(label=ev['title'])
                    name.set_halign(Gtk.Align.START)
                    name.set_hexpand(True)
                    name.set_ellipsize(3)
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
                    dot = Gtk.Label(label="•")
                    dot.add_css_class('event-dot')
                    name = Gtk.Label(label=ev)
                    name.set_halign(Gtk.Align.START)
                    name.set_ellipsize(3)
                    name.set_tooltip_text(ev)
                    name.add_css_class('event-name')
                    row.append(dot)
                    row.append(name)
                self.events_box.append(row)
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
        def do_toggle():
            try:
                from google.oauth2.credentials import Credentials
                from googleapiclient.discovery import build
                SCOPES = [
                    'https://www.googleapis.com/auth/calendar.readonly',
                    'https://www.googleapis.com/auth/tasks',
                ]
                creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
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
                import sys
                print(f'[task toggle error] {e}', file=sys.stderr)
        threading.Thread(target=do_toggle, daemon=True).start()

    def _on_refresh_clicked(self, _):
        self.refresh_btn.set_sensitive(False)
        def do_sync():
            _run_sync()
            def after():
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
          font-family: "JetBrainsMonoNL Nerd Font";
          font-size: 13px;
          padding: 0;
      }}
      .refresh-btn label {{
          all: unset;
          font-family: "JetBrainsMonoNL Nerd Font";
          font-size: 13px;
          color: {fg};
      }}
      .refresh-btn:hover {{
          background: {hex_to_rgba(accent, 0.28)};
      }}
      .add-btn.nerd {{
          font-family: "JetBrainsMonoNL Nerd Font";
          font-size: 13px;
          padding: 0;
      }}
      .add-btn.nerd label {{
          all: unset;
          font-family: "JetBrainsMonoNL Nerd Font";
          font-size: 13px;
          color: {fg};
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


app = Gtk.Application(application_id="com.waybar.gcal")
app.connect("activate", on_activate)

try:
    app.run(None)
finally:
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)
