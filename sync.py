#!/usr/bin/python3
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


def fmt_time(dt_str):
    """Parse ISO datetime string and return HH:MM."""
    # dateTime fields include timezone offset
    dt = datetime.datetime.fromisoformat(dt_str)
    return dt.strftime('%H:%M')


def fetch_events(creds):
    service = build('calendar', 'v3', credentials=creds)

    today = datetime.date.today()
    # Fetch 2 months back and 3 months forward to cover calendar navigation
    time_min = (today - datetime.timedelta(days=60)).isoformat() + 'T00:00:00Z'
    time_max = (today + datetime.timedelta(days=90)).isoformat() + 'T23:59:59Z'

    result = service.events().list(
        calendarId='primary',
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy='startTime',
        maxResults=500,
    ).execute()

    events_by_date = {}
    for item in result.get('items', []):
        start = item['start']
        end = item['end']
        title = item.get('summary', '(no title)')

        if 'dateTime' in start:
            # Timed event
            start_str = fmt_time(start['dateTime'])
            end_str = fmt_time(end['dateTime'])
            label = f'{title} {start_str}-{end_str}'
            date_key = datetime.datetime.fromisoformat(start['dateTime']).date().isoformat()
        else:
            # All-day event
            label = title
            date_key = start['date']

        events_by_date.setdefault(date_key, []).append(label)

    return events_by_date


def main():
    creds = get_credentials()
    events = fetch_events(creds)
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, 'w') as f:
        json.dump(events, f)
    print(f'Synced {sum(len(v) for v in events.values())} events across {len(events)} days.')


if __name__ == '__main__':
    main()
