"""Cliente HTTP do NASA DONKI (Space Weather Database Of Notifications, Knowledge, Information)."""

import os
from dataclasses import dataclass
from datetime import date

import httpx


DEFAULT_BASE_URL = 'https://api.nasa.gov/DONKI'


class DonkiError(Exception):
    """Falha ao consultar o DONKI (rede, limite de requisições ou resposta inválida)."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class DonkiSettings:
    api_key: str = 'DEMO_KEY'
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: float = 30.0

    @classmethod
    def from_environment(cls) -> 'DonkiSettings':
        return cls(
            api_key=os.getenv('NASA_API_KEY') or 'DEMO_KEY',
            base_url=(os.getenv('DONKI_BASE_URL') or DEFAULT_BASE_URL).rstrip('/'),
            timeout_seconds=float(os.getenv('DONKI_TIMEOUT_SECONDS') or 30),
        )


class DonkiClient:
    def __init__(self, client: httpx.Client, settings: DonkiSettings | None = None):
        self.client = client
        self.settings = settings or DonkiSettings.from_environment()

    def fetch(self, event_type: str, start: date, end: date) -> list[dict]:
        """Busca eventos de um tipo (FLR, CME ou SEP) no intervalo [start, end]."""
        url = f'{self.settings.base_url}/{event_type}'
        params = {'startDate': start.isoformat(), 'endDate': end.isoformat(), 'api_key': self.settings.api_key}
        try:
            response = self.client.get(url, params=params, timeout=self.settings.timeout_seconds)
        except httpx.HTTPError as exc:
            raise DonkiError(f'Falha de rede ao consultar o DONKI ({event_type}): {exc.__class__.__name__}') from exc
        if response.status_code == 429:
            raise DonkiError('Limite de requisições da API da NASA atingido. Configure NASA_API_KEY com uma chave própria.', 429)
        if response.status_code >= 400:
            raise DonkiError(f'O DONKI respondeu {response.status_code} para {event_type}', response.status_code)
        # O DONKI responde com corpo vazio quando não há eventos no período.
        if not response.content or not response.content.strip():
            return []
        try:
            payload = response.json()
        except ValueError as exc:
            raise DonkiError(f'Resposta do DONKI não é JSON válido ({event_type})') from exc
        if payload is None:
            return []
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise DonkiError(f'Formato inesperado na resposta do DONKI ({event_type})')
        return payload
