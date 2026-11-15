"""NASA DONKI HTTP client (Space Weather Database Of Notifications, Knowledge, Information)."""

import os
from dataclasses import dataclass
from datetime import date

import httpx


DEFAULT_BASE_URL = 'https://api.nasa.gov/DONKI'


class DonkiError(Exception):
    """DONKI request failure (network, rate limit or invalid response)."""

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
        """Fetches events of one type (FLR, CME or SEP) in the interval [start, end]."""
        url = f'{self.settings.base_url}/{event_type}'
        params = {'startDate': start.isoformat(), 'endDate': end.isoformat(), 'api_key': self.settings.api_key}
        try:
            response = self.client.get(url, params=params, timeout=self.settings.timeout_seconds)
        except httpx.HTTPError as exc:
            raise DonkiError(f'Network failure while querying DONKI ({event_type}): {exc.__class__.__name__}') from exc
        if response.status_code == 429:
            raise DonkiError('NASA API rate limit reached. Set NASA_API_KEY to your own key.', 429)
        if response.status_code >= 400:
            raise DonkiError(f'DONKI answered {response.status_code} for {event_type}', response.status_code)
        # DONKI returns an empty body when there are no events in the period.
        if not response.content or not response.content.strip():
            return []
        try:
            payload = response.json()
        except ValueError as exc:
            raise DonkiError(f'DONKI response is not valid JSON ({event_type})') from exc
        if payload is None:
            return []
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise DonkiError(f'Unexpected DONKI response format ({event_type})')
        return payload
