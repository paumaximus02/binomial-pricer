"""Cox-Ross-Rubinstein binomial tree pricing engine (Numba-accelerated)."""

from __future__ import annotations

from enum import Enum

import numpy as np
from numba import njit


class OptionStyle(str, Enum):
    EUROPEAN = "european"
    AMERICAN = "american"


class OptionType(str, Enum):
    CALL = "call"
    PUT = "put"


@njit(cache=True)
def _payoff(spot: float, strike: float, is_call: bool) -> float:
    if is_call:
        return max(spot - strike, 0.0)
    return max(strike - spot, 0.0)


@njit(cache=True)
def _crr_params(
    spot: float,
    strike: float,
    rate: float,
    vol: float,
    time_to_expiry: float,
    steps: int,
    dividend_yield: float,
) -> tuple[float, float, float, float, float]:
    """Return dt, u, d, p, discount."""
    dt = time_to_expiry / steps
    u = np.exp(vol * np.sqrt(dt))
    d = 1.0 / u
    p = (np.exp((rate - dividend_yield) * dt) - d) / (u - d)
    discount = np.exp(-rate * dt)
    return dt, u, d, p, discount


@njit(cache=True)
def price_european(
    spot: float,
    strike: float,
    rate: float,
    vol: float,
    time_to_expiry: float,
    steps: int,
    is_call: bool,
    dividend_yield: float,
) -> float:
    if time_to_expiry <= 0.0:
        return _payoff(spot, strike, is_call)

    _, u, d, p, discount = _crr_params(
        spot, strike, rate, vol, time_to_expiry, steps, dividend_yield
    )

    values = np.empty(steps + 1, dtype=np.float64)
    for j in range(steps + 1):
        terminal_spot = spot * (u ** (steps - j)) * (d ** j)
        values[j] = _payoff(terminal_spot, strike, is_call)

    for i in range(steps - 1, -1, -1):
        for j in range(i + 1):
            values[j] = discount * (p * values[j] + (1.0 - p) * values[j + 1])

    return values[0]


@njit(cache=True)
def price_american(
    spot: float,
    strike: float,
    rate: float,
    vol: float,
    time_to_expiry: float,
    steps: int,
    is_call: bool,
    dividend_yield: float,
) -> float:
    if time_to_expiry <= 0.0:
        return _payoff(spot, strike, is_call)

    _, u, d, p, discount = _crr_params(
        spot, strike, rate, vol, time_to_expiry, steps, dividend_yield
    )

    tree = np.empty((steps + 1, steps + 1), dtype=np.float64)

    for j in range(steps + 1):
        terminal_spot = spot * (u ** (steps - j)) * (d ** j)
        tree[steps, j] = _payoff(terminal_spot, strike, is_call)

    for i in range(steps - 1, -1, -1):
        for j in range(i + 1):
            continuation = discount * (p * tree[i + 1, j] + (1.0 - p) * tree[i + 1, j + 1])
            node_spot = spot * (u ** (i - j)) * (d ** j)
            intrinsic = _payoff(node_spot, strike, is_call)
            tree[i, j] = max(intrinsic, continuation)

    return tree[0, 0]


@njit(cache=True)
def price_option(
    spot: float,
    strike: float,
    rate: float,
    vol: float,
    time_to_expiry: float,
    steps: int,
    is_call: bool,
    is_american: bool,
    dividend_yield: float,
) -> float:
    if is_american:
        return price_american(
            spot, strike, rate, vol, time_to_expiry, steps, is_call, dividend_yield
        )
    return price_european(
        spot, strike, rate, vol, time_to_expiry, steps, is_call, dividend_yield
    )


@njit(cache=True)
def compute_greeks(
    spot: float,
    strike: float,
    rate: float,
    vol: float,
    time_to_expiry: float,
    steps: int,
    is_call: bool,
    is_american: bool,
    dividend_yield: float,
) -> tuple[float, float, float, float, float]:
    """
    Return price, delta, gamma, theta, vega via bump-and-reprice.

    Theta is per calendar year. Vega is sensitivity to a 1.0 absolute vol move.
    """
    price = price_option(
        spot, strike, rate, vol, time_to_expiry, steps, is_call, is_american, dividend_yield
    )

    d_spot = max(spot * 0.01, 0.01)
    p_up = price_option(
        spot + d_spot, strike, rate, vol, time_to_expiry, steps, is_call, is_american, dividend_yield
    )
    p_down = price_option(
        spot - d_spot, strike, rate, vol, time_to_expiry, steps, is_call, is_american, dividend_yield
    )
    delta = (p_up - p_down) / (2.0 * d_spot)
    gamma = (p_up - 2.0 * price + p_down) / (d_spot ** 2)

    d_t = min(1.0 / 365.0, time_to_expiry / 2.0) if time_to_expiry > 0 else 0.0
    if d_t > 0:
        p_shorter = price_option(
            spot, strike, rate, vol, time_to_expiry - d_t, steps, is_call, is_american, dividend_yield
        )
        theta = (p_shorter - price) / d_t
    else:
        theta = 0.0

    d_vol = 0.01
    p_vol_up = price_option(
        spot, strike, rate, vol + d_vol, time_to_expiry, steps, is_call, is_american, dividend_yield
    )
    vega = (p_vol_up - price) / d_vol

    return price, delta, gamma, theta, vega


@njit(cache=True)
def implied_volatility(
    market_price: float,
    spot: float,
    strike: float,
    rate: float,
    time_to_expiry: float,
    steps: int,
    is_call: bool,
    is_american: bool,
    dividend_yield: float,
    tol: float = 1e-6,
    max_iter: int = 100,
) -> float:
    """Bisection on volatility in [1e-4, 5.0]."""
    lo, hi = 1e-4, 5.0
    f_lo = (
        price_option(spot, strike, rate, lo, time_to_expiry, steps, is_call, is_american, dividend_yield)
        - market_price
    )
    f_hi = (
        price_option(spot, strike, rate, hi, time_to_expiry, steps, is_call, is_american, dividend_yield)
        - market_price
    )

    if f_lo * f_hi > 0:
        return np.nan

    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        f_mid = (
            price_option(spot, strike, rate, mid, time_to_expiry, steps, is_call, is_american, dividend_yield)
            - market_price
        )
        if abs(f_mid) < tol:
            return mid
        if f_lo * f_mid <= 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid

    return 0.5 * (lo + hi)
