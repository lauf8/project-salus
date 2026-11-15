"""Imports the GOES integral proton flux (NOAA SWPC) without going through the HTTP API.

Usage (inside the container):
    python -m scripts.sync_proton_flux                 # last day
    python -m scripts.sync_proton_flux --window 7-day

SWPC only publishes the last few days; schedule it often (e.g. every hour).
"""

import argparse
import sys

import httpx
from fastapi import HTTPException
from sqlmodel import Session

from app.database import engine
from app.providers.swpc import SwpcClient, SwpcSettings
from app.services.radiation_service import RadiationService


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Imports the NOAA SWPC proton flux')
    parser.add_argument('--window', choices=['6-hour', '1-day', '3-day', '7-day'], default='1-day')
    args = parser.parse_args(argv)
    with httpx.Client() as http_client, Session(engine) as session:
        try:
            result = RadiationService(session, None).sync_proton_flux(SwpcClient(http_client, SwpcSettings.from_environment()), args.window, check_permission=False)
        except HTTPException as exc:
            print(f'Failure: {exc.detail}')
            return 1
    print(f'{result.fetched_count} readings received, {result.stored_count} new, {result.skipped_count} skipped, {result.alerts_created} alerts')
    return 0


if __name__ == '__main__':
    sys.exit(main())
