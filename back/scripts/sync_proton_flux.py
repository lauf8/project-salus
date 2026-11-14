"""Importa o fluxo integral de prótons do GOES (NOAA SWPC) sem passar pela API HTTP.

Uso (dentro do container):
    python -m scripts.sync_proton_flux                 # último dia
    python -m scripts.sync_proton_flux --window 7-day

O SWPC só publica os últimos dias; agende com frequência (ex.: a cada hora).
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
    parser = argparse.ArgumentParser(description='Importa o fluxo de prótons da NOAA SWPC')
    parser.add_argument('--window', choices=['6-hour', '1-day', '3-day', '7-day'], default='1-day')
    args = parser.parse_args(argv)
    with httpx.Client() as http_client, Session(engine) as session:
        try:
            result = RadiationService(session, None).sync_proton_flux(SwpcClient(http_client, SwpcSettings.from_environment()), args.window, check_permission=False)
        except HTTPException as exc:
            print(f'Falha: {exc.detail}')
            return 1
    print(f'{result.fetched_count} leituras recebidas, {result.stored_count} novas, {result.skipped_count} ignoradas, {result.alerts_created} alertas')
    return 0


if __name__ == '__main__':
    sys.exit(main())
