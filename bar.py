#!/usr/bin/python3
import json
import datetime
import os

CACHE_FILE = os.path.expanduser('~/.cache/waybar-ycal/events.json')

def load_events():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}

now = datetime.datetime.now()
today = now.date()
events = load_events()
today_events = events.get(today.isoformat(), [])

output = {
    "text": f"\U000f00ed  {now.strftime('%A %H:%M')}",
    "tooltip": "",
    "class": "has-events" if today_events else ""
}

print(json.dumps(output))
