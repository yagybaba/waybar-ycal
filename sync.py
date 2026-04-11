#!/usr/bin/python3
"""Initial auth + full sync script. Run once to authenticate with Google."""
import datetime
import json
import os
import sys

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/tasks',
]
CREDENTIALS_FILE = os.path.expanduser('~/.config/waybar-ycal/credentials.json')
TOKEN_FILE = os.path.expanduser('~/.cache/waybar-ycal/token.json')
CACHE_FILE = os.path.expanduser('~/.cache/waybar-ycal/events.json')


def get_credentials():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                print(f'credentials.json not found at {CREDENTIALS_FILE}', file=sys.stderr)
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
        with open(TOKEN_FILE, 'w') as f:
            f.write(creds.to_json())
    return creds


def main():
    creds = get_credentials()
    print('Authenticated. Syncing all calendars and tasks...')

    today = datetime.date.today()
    time_min = (today - datetime.timedelta(days=60)).isoformat() + 'T00:00:00Z'
    time_max = (today + datetime.timedelta(days=365)).isoformat() + 'T23:59:59Z'

    # All calendars
    cal_service = build('calendar', 'v3', credentials=creds)
    cal_list = cal_service.calendarList().list().execute()
    calendar_ids = [c['id'] for c in cal_list.get('items', [])]

    events_by_date = {}
    for cal_id in calendar_ids:
        try:
            result = cal_service.events().list(
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

    # Tasks
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
            if due:
                events_by_date.setdefault(due[:10], []).append({
                    'type': 'task',
                    'id': task['id'],
                    'lid': tl['id'],
                    'title': task.get('title', '(no title)'),
                    'done': task.get('status') == 'completed',
                })

    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    tmp = CACHE_FILE + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(events_by_date, f)
    os.replace(tmp, CACHE_FILE)

    event_count = sum(1 for v in events_by_date.values() for e in v if isinstance(e, str))
    task_count = sum(1 for v in events_by_date.values() for e in v if isinstance(e, dict))
    print(f'Done. {event_count} events, {task_count} tasks across {len(events_by_date)} days.')


if __name__ == '__main__':
    main()
