"""High-level binomial option pricing model."""

from __future__ import annotations

from dataclasses import dataclass

from core import OptionStyle, OptionType, compute_greeks, implied_volatility, price_option


@dataclass(frozen=True, slots=True)
class PricingResult:
    price: float
    delta: float
    gamma: float
    theta: float
    vega: float


class BinomialModel:
    """CRR binomial tree wrapper with configurable step count."""

    def __init__(self, steps: int = 200) -> None:
        if steps < 1:
            raise ValueError("steps must be >= 1")
        self.steps = steps

    def price(
        self,
        spot: float,
        strike: float,
        rate: float,
        vol: float,
        time_to_expiry: float,
        option_type: OptionType,
        style: OptionStyle = OptionStyle.EUROPEAN,
    ) -> float:
        self._validate_inputs(spot, strike, rate, vol, time_to_expiry)
        return price_option(
            spot=spot,
            strike=strike,
            rate=rate,
            vol=vol,
            time_to_expiry=time_to_expiry,
            steps=self.steps,
            is_call=option_type == OptionType.CALL,
            is_american=style == OptionStyle.AMERICAN,
            dividend_yield=0.0,
        )

    def price_with_greeks(
        self,
        spot: float,
        strike: float,
        rate: float,
        vol: float,
        time_to_expiry: float,
        option_type: OptionType,
        style: OptionStyle = OptionStyle.EUROPEAN,
        dividend_yield: float = 0.0,
    ) -> PricingResult:
        self._validate_inputs(spot, strike, rate, vol, time_to_expiry, dividend_yield)
        price, delta, gamma, theta, vega = compute_greeks(
            spot=spot,
            strike=strike,
            rate=rate,
            vol=vol,
            time_to_expiry=time_to_expiry,
            steps=self.steps,
            is_call=option_type == OptionType.CALL,
            is_american=style == OptionStyle.AMERICAN,
            dividend_yield=dividend_yield,
        )
        return PricingResult(price=price, delta=delta, gamma=gamma, theta=theta, vega=vega)

    def solve_iv(
        self,
        market_price: float,
        spot: float,
        strike: float,
        rate: float,
        time_to_expiry: float,
        option_type: OptionType,
        style: OptionStyle = OptionStyle.EUROPEAN,
    ) -> float:
        self._validate_inputs(spot, strike, rate, 0.2, time_to_expiry)
        if market_price <= 0:
            raise ValueError("market_price must be positive")

        iv = implied_volatility(
            market_price=market_price,
            spot=spot,
            strike=strike,
            rate=rate,
            time_to_expiry=time_to_expiry,
            steps=self.steps,
            is_call=option_type == OptionType.CALL,
            is_american=style == OptionStyle.AMERICAN,
            dividend_yield=0.0,
        )
        if iv != iv:  # NaN check
            raise ValueError("Could not bracket implied volatility for given market price")
        return iv

    @staticmethod
    def _validate_inputs(
        spot: float,
        strike: float,
        rate: float,
        vol: float,
        time_to_expiry: float,
        dividend_yield: float = 0.0,
    ) -> None:
        if spot <= 0:
            raise ValueError("spot must be positive")
        if strike <= 0:
            raise ValueError("strike must be positive")
        if vol < 0:
            raise ValueError("vol must be non-negative")
        if time_to_expiry < 0:
            raise ValueError("time_to_expiry must be non-negative")
        if not (-1.0 <= rate <= 1.0):
            raise ValueError("rate must be between -1 and 1")
        if not (0.0 <= dividend_yield <= 1.0):
            raise ValueError("dividend_yield must be between 0 and 1")
