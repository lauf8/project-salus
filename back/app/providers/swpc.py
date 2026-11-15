"""NOAA SWPC HTTP client for the GOES integral proton flux.

SWPC publishes JSON files with recent readings (6 hours, 1, 3 or 7 days).
The service has no older history: for past events use the flux simulation
(POST /v1/radiation/proton-flux/simulate).
"""

import os
from dataclasses import dataclass
from typing import Literal

import httpx


DEFAULT_BASE_URL = 'https://services.swpc.noaa.gov/json/goes'
SwpcWindow = Literal['6-hour', '1-day', '3-day', '7-day']


class SwpcError(Exception):
    """NOAA SWPC request failure (network or invalid response)."""

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
        """Readings in SWPC format: time_tag, satellite, flux (pfu) and energy (e.g. '>=10 MeV')."""
        url = f'{self.settings.base_url}/{self.settings.satellite}/integral-protons-{window}.json'
        try:
            response = self.client.get(url, timeout=self.settings.timeout_seconds)
        except httpx.HTTPError as exc:
            raise SwpcError(f'Network failure while querying NOAA SWPC: {exc.__class__.__name__}') from exc
        if response.status_code >= 400:
            raise SwpcError(f'A NOAA SWPC respondeu {response.status_code}', response.status_code)
        try:
            payload = response.json()
        except ValueError as exc:
            raise SwpcError('NOAA SWPC response is not valid JSON') from exc
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise SwpcError('Unexpected NOAA SWPC response format')
        return payload
