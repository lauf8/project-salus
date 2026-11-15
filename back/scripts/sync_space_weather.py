"""Synchronizes FLR, CME and SEP from NASA DONKI without going through the HTTP API.

Usage (inside the container):
    python -m scripts.sync_space_weather                 # last 30 days
    python -m scripts.sync_space_weather --days 7
    python -m scripts.sync_space_weather --start 2024-10-01 --end 2024-11-14 --types SEP FLR

Designed for scheduling (cron). Uses NASA_API_KEY from the environment.
"""

import argparse
import sys
from datetime import date, datetime, timedelta, timezone

import httpx
from sqlmodel import Session

from app.database import engine
from app.providers.donki import DonkiClient, DonkiSettings
from app.schemas.space_weather import MAX_SYNC_DAYS
from app.services.space_weather_service import SpaceWeatherService


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Synchronizes NASA DONKI events')
    parser.add_argument('--start', type=date.fromisoformat)
    parser.add_argument('--end', type=date.fromisoformat)
    parser.add_argument('--days', type=int, default=30, help='Used when --start is not given')
    parser.add_argument('--types', nargs='+', choices=['FLR', 'CME', 'SEP'], default=['FLR', 'CME', 'SEP'])
    args = parser.parse_args(argv)

    end = args.end or datetime.now(timezone.utc).date()
    start = args.start or end - timedelta(days=args.days - 1)
    if end < start or (end - start).days + 1 > MAX_SYNC_DAYS:
        parser.error(f'Invalid interval: use up to {MAX_SYNC_DAYS} days with an end equal to or after the start')

    with httpx.Client() as http_client, Session(engine) as session:
        service = SpaceWeatherService(session, None, DonkiClient(http_client, DonkiSettings.from_environment()))
        runs = service.sync(start, end, list(dict.fromkeys(args.types)), check_permission=False)

    for run in runs:
        detail = f'{run.fetched_count} received, {run.created_count} new, {run.updated_count} updated' if run.status == 'success' else run.error
        print(f'{run.event_type} {run.start_date}..{run.end_date}: {run.status} — {detail}')
    return 1 if any(run.status == 'failed' for run in runs) else 0


if __name__ == '__main__':
    sys.exit(main())
