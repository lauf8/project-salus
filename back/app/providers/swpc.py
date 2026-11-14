"""Cliente HTTP da NOAA SWPC para o fluxo integral de prótons do GOES.

O SWPC publica arquivos JSON com as leituras recentes (6 horas, 1, 3 ou 7 dias).
Não há histórico mais antigo nesse serviço: para eventos passados use a simulação
de fluxo (POST /v1/radiation/proton-flux/simulate).
"""

import os
from dataclasses import dataclass
from typing import Literal

import httpx


DEFAULT_BASE_URL = 'https://services.swpc.noaa.gov/json/goes'
SwpcWindow = Literal['6-hour', '1-day', '3-day', '7-day']


class SwpcError(Exception):
    """Falha ao consultar a NOAA SWPC (rede ou resposta inválida)."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class SwpcSettings:
    base_url: str = DEFAULT_BASE_URL
    satellite: str = 'primary'
    timeout_seconds: float = 30.0

    @classmethod
    def from_environment(cls) -> 'SwpcSettings':
        return cls(
            base_url=(os.getenv('SWPC_BASE_URL') or DEFAULT_BASE_URL).rstrip('/'),
            satellite=os.getenv('SWPC_GOES_SATELLITE') or 'primary',
            timeout_seconds=float(os.getenv('SWPC_TIMEOUT_SECONDS') or 30),
        )


class SwpcClient:
    def __init__(self, client: httpx.Client, settings: SwpcSettings | None = None):
        self.client = client
        self.settings = settings or SwpcSettings.from_environment()

    def integral_protons(self, window: SwpcWindow = '1-day') -> list[dict]:
        """Leituras no formato do SWPC: time_tag, satellite, flux (pfu) e energy (ex.: '>=10 MeV')."""
        url = f'{self.settings.base_url}/{self.settings.satellite}/integral-protons-{window}.json'
        try:
            response = self.client.get(url, timeout=self.settings.timeout_seconds)
        except httpx.HTTPError as exc:
            raise SwpcError(f'Falha de rede ao consultar a NOAA SWPC: {exc.__class__.__name__}') from exc
        if response.status_code >= 400:
            raise SwpcError(f'A NOAA SWPC respondeu {response.status_code}', response.status_code)
        try:
            payload = response.json()
        except ValueError as exc:
            raise SwpcError('Resposta da NOAA SWPC não é JSON válido') from exc
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise SwpcError('Formato inesperado na resposta da NOAA SWPC')
        return payload
