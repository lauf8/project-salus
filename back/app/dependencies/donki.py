from fastapi import Request

from app.providers.donki import DonkiClient, DonkiSettings
from app.providers.swpc import SwpcClient, SwpcSettings


def get_donki_client(request: Request) -> DonkiClient:
    return DonkiClient(request.app.state.donki_http_client, DonkiSettings.from_environment())


def get_swpc_client(request: Request) -> SwpcClient:
    # Reuses the synchronous HTTP client created in the application lifespan.
    return SwpcClient(request.app.state.donki_http_client, SwpcSettings.from_environment())
