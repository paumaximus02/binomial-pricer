"""FastAPI server for binomial option pricing."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from core import OptionStyle, OptionType
from market import MarketDataError, MassiveMarketData, Settings, SpotQuote
from model import BinomialModel, PricingResult

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="Binomial Option Pricer",
    description="CRR binomial tree pricer with Greeks and implied volatility.",
    version="1.0.0",
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def get_settings() -> Settings:
    return Settings()


def get_model(settings: Annotated[Settings, Depends(get_settings)]) -> BinomialModel:
    return BinomialModel(steps=settings.default_tree_steps)


def get_market(settings: Annotated[Settings, Depends(get_settings)]) -> MassiveMarketData:
    try:
        return MassiveMarketData(settings)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def get_optional_market(settings: Annotated[Settings, Depends(get_settings)]) -> MassiveMarketData | None:
    try:
        return MassiveMarketData(settings)
    except ValueError:
        return None


class PriceRequest(BaseModel):
    spot: float | None = Field(None, gt=0, description="Spot price; omit to fetch from Massive")
    symbol: str | None = Field(None, min_length=1, description="Ticker when spot is omitted")
    strike: float = Field(..., gt=0)
    rate: float | None = Field(None, ge=-1, le=1)
    vol: float = Field(..., ge=0)
    expiry: date = Field(..., description="Option expiry date (YYYY-MM-DD)")
    option_type: OptionType
    style: OptionStyle = OptionStyle.EUROPEAN
    valuation_date: date = Field(default_factory=date.today)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, v: str | None) -> str | None:
        return v.upper().strip() if v else None

    @field_validator("expiry")
    @classmethod
    def expiry_after_valuation(cls, expiry: date, info) -> date:
        valuation = info.data.get("valuation_date", date.today())
        if expiry < valuation:
            raise ValueError("expiry must be on or after valuation_date")
        return expiry


class PriceResponse(BaseModel):
    symbol: str | None
    spot: float
    strike: float
    rate: float
    vol: float
    time_to_expiry: float
    option_type: OptionType
    style: OptionStyle
    price: float
    delta: float
    gamma: float
    theta: float
    vega: float


class IVRequest(BaseModel):
    market_price: float = Field(..., gt=0)
    spot: float | None = Field(None, gt=0)
    symbol: str | None = Field(None, min_length=1)
    strike: float = Field(..., gt=0)
    rate: float | None = Field(None, ge=-1, le=1)
    expiry: date
    option_type: OptionType
    style: OptionStyle = OptionStyle.EUROPEAN
    valuation_date: date = Field(default_factory=date.today)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, v: str | None) -> str | None:
        return v.upper().strip() if v else None


class IVResponse(BaseModel):
    implied_volatility: float
    market_price: float
    spot: float
    strike: float
    time_to_expiry: float
    option_type: OptionType
    style: OptionStyle


class SpotResponse(BaseModel):
    symbol: str
    price: float
    as_of: str


def _years_between(start: date, end: date) -> float:
    return max((end - start).days, 0) / 365.0


def _market_http_exception(exc: MarketDataError) -> HTTPException:
    status = exc.status_code if exc.status_code < 500 else 502
    return HTTPException(status_code=status, detail=exc.message)


async def _resolve_spot(
    req_spot: float | None,
    symbol: str | None,
    market: MassiveMarketData | None,
) -> tuple[float, str | None]:
    if req_spot is not None:
        return req_spot, symbol
    if not symbol:
        raise HTTPException(status_code=422, detail="Either spot or symbol is required")
    if market is None:
        raise HTTPException(
            status_code=503,
            detail="MASSIVE_API_KEY is not configured. Enter spot manually or set a valid API key in .env.",
        )
    try:
        quote = await market.get_spot(symbol)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MarketDataError as exc:
        raise _market_http_exception(exc) from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach Massive.com: {exc}") from exc
    return quote.price, quote.symbol


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/market/spot/{symbol}", response_model=SpotResponse)
async def get_spot(
    symbol: str,
    market: Annotated[MassiveMarketData, Depends(get_market)],
) -> SpotResponse:
    try:
        quote: SpotQuote = await market.get_spot(symbol)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MarketDataError as exc:
        raise _market_http_exception(exc) from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach Massive.com: {exc}") from exc
    return SpotResponse(symbol=quote.symbol, price=quote.price, as_of=quote.as_of)


@app.post("/price", response_model=PriceResponse)
async def price_option_endpoint(
    body: PriceRequest,
    model: Annotated[BinomialModel, Depends(get_model)],
    market: Annotated[MassiveMarketData | None, Depends(get_optional_market)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PriceResponse:
    spot, symbol = await _resolve_spot(body.spot, body.symbol, market)
    rate = body.rate if body.rate is not None else settings.default_risk_free_rate
    tte = _years_between(body.valuation_date, body.expiry)

    try:
        result: PricingResult = model.price_with_greeks(
            spot=spot,
            strike=body.strike,
            rate=rate,
            vol=body.vol,
            time_to_expiry=tte,
            option_type=body.option_type,
            style=body.style,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return PriceResponse(
        symbol=symbol,
        spot=spot,
        strike=body.strike,
        rate=rate,
        vol=body.vol,
        time_to_expiry=tte,
        option_type=body.option_type,
        style=body.style,
        price=result.price,
        delta=result.delta,
        gamma=result.gamma,
        theta=result.theta,
        vega=result.vega,
    )


@app.post("/iv", response_model=IVResponse)
async def solve_implied_vol(
    body: IVRequest,
    model: Annotated[BinomialModel, Depends(get_model)],
    market: Annotated[MassiveMarketData | None, Depends(get_optional_market)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> IVResponse:
    spot, _ = await _resolve_spot(body.spot, body.symbol, market)
    rate = body.rate if body.rate is not None else settings.default_risk_free_rate
    tte = _years_between(body.valuation_date, body.expiry)

    try:
        iv = model.solve_iv(
            market_price=body.market_price,
            spot=spot,
            strike=body.strike,
            rate=rate,
            time_to_expiry=tte,
            option_type=body.option_type,
            style=body.style,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return IVResponse(
        implied_volatility=iv,
        market_price=body.market_price,
        spot=spot,
        strike=body.strike,
        time_to_expiry=tte,
        option_type=body.option_type,
        style=body.style,
    )
