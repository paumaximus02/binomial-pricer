"""Market data client for Massive.com (formerly Polygon.io)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import httpx
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_PLACEHOLDER_KEYS = frozenset(
    {
        "",
        "your_massive_api_key_here",
        "your_polygon_api_key_here",
    }
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    massive_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("MASSIVE_API_KEY", "POLYGON_API_KEY"),
    )
    massive_base_url: str = Field(
        default="https://api.massive.com",
        validation_alias=AliasChoices("MASSIVE_BASE_URL", "POLYGON_BASE_URL"),
    )
    default_risk_free_rate: float = 0.05
    default_tree_steps: int = 200


@dataclass(frozen=True, slots=True)
class SpotQuote:
    symbol: str
    price: float
    as_of: str


class MarketDataError(Exception):
    """Raised when Massive.com returns an API error."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(message)


class MassiveMarketData:
    """Fetch spot prices from the Massive REST API."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        key = self.settings.massive_api_key.strip()
        if key in _PLACEHOLDER_KEYS or key.startswith("your_"):
            raise ValueError(
                "MASSIVE_API_KEY is not configured. Copy .env.example to .env and set a valid API key."
            )
        if not key:
            raise ValueError("MASSIVE_API_KEY is required")

    async def get_spot(self, symbol: str) -> SpotQuote:
        symbol = symbol.upper().strip()
        if not symbol:
            raise ValueError("symbol must be non-empty")

        # https://massive.com/docs/rest/stocks/aggregates/previous-day-bar
        url = f"{self.settings.massive_base_url}/v2/aggs/ticker/{symbol}/prev"
        params = {"adjusted": "true", "apiKey": self.settings.massive_api_key.strip()}
        headers = {"Authorization": f"Bearer {self.settings.massive_api_key.strip()}"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params, headers=headers)

        if response.is_success:
            payload = response.json()
        else:
            raise _http_error_from_response(response)

        results = payload.get("results") or []
        if not results:
            raise LookupError(f"No market data found for symbol {symbol}")

        bar = results[0]
        price = float(bar["c"])
        as_of = date.fromtimestamp(bar["t"] / 1000).isoformat()

        return SpotQuote(symbol=symbol, price=price, as_of=as_of)


def _http_error_from_response(response: httpx.Response) -> MarketDataError:
    try:
        payload = response.json()
        detail = payload.get("error") or payload.get("message") or response.reason_phrase
    except ValueError:
        detail = response.reason_phrase or "Unknown error"

    if response.status_code in (401, 403):
        message = f"Massive API authentication failed: {detail}. Check MASSIVE_API_KEY in .env."
    elif response.status_code == 404:
        message = f"Massive API resource not found: {detail}"
    elif response.status_code == 429:
        message = f"Massive API rate limit exceeded: {detail}"
    else:
        message = f"Massive API error ({response.status_code}): {detail}"

    return MarketDataError(response.status_code, message)


# Backward-compatible alias for earlier project versions.
PolygonMarketData = MassiveMarketData
