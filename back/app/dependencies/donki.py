from fastapi import Request

from app.providers.donki import DonkiClient, DonkiSettings
from app.providers.swpc import SwpcClient, SwpcSettings


def get_donki_client(request: Request) -> DonkiClient:
    return DonkiClient(request.app.state.donki_http_client, DonkiSettings.from_environment())


def get_swpc_client(request: Request) -> SwpcClient:
    # Reaproveita o cliente HTTP síncrono criado no lifespan da aplicação.
    return SwpcClient(request.app.state.donki_http_client, SwpcSettings.from_environment())
