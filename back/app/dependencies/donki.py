from fastapi import Request

from app.providers.donki import DonkiClient, DonkiSettings


def get_donki_client(request: Request) -> DonkiClient:
    return DonkiClient(request.app.state.donki_http_client, DonkiSettings.from_environment())
