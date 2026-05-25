"""Plotly chart generation for Greeks sensitivity analysis."""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import plotly.graph_objects as go

from core import OptionType, compute_greeks, price_option

CHART_POINTS = 51
VOL_MIN = 0.10
VOL_MAX = 0.60

_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="#1a2332",
    plot_bgcolor="#0f1419",
    font=dict(family="Segoe UI, system-ui, sans-serif", color="#e8edf4", size=12),
    margin=dict(l=60, r=24, t=56, b=52),
    hovermode="x unified",
)

# Distinct line colors per chart (dark-theme friendly)
COLOR_PRICE = "#3b82f6"   # blue
COLOR_DELTA = "#22c55e"   # green
COLOR_THETA = "#f59e0b"   # amber
COLOR_VEGA = "#a855f7"    # purple


def _figure_to_dict(fig: go.Figure) -> dict[str, Any]:
    return json.loads(fig.to_json())


def _base_layout(title: str, x_title: str, y_title: str) -> dict[str, Any]:
    layout = dict(_LAYOUT)
    layout["title"] = dict(text=title, x=0.03, xanchor="left")
    layout["xaxis"] = dict(title=x_title, gridcolor="#2f3f56", zerolinecolor="#2f3f56")
    layout["yaxis"] = dict(title=y_title, gridcolor="#2f3f56", zerolinecolor="#2f3f56")
    return layout


def _add_marker(fig: go.Figure, x: float, y: float, label: str, line_color: str) -> None:
    fig.add_vline(x=x, line=dict(color=line_color, width=1, dash="dash"))
    fig.add_trace(
        go.Scatter(
            x=[x],
            y=[y],
            mode="markers+text",
            name=label,
            marker=dict(color=line_color, size=10, line=dict(color="#e8edf4", width=1)),
            text=[label],
            textposition="top center",
            showlegend=False,
        )
    )


def build_greeks_charts(
    *,
    spot: float,
    strike: float,
    rate: float,
    vol: float,
    time_to_expiry: float,
    option_type: OptionType,
    is_american: bool,
    dividend_yield: float,
    steps: int,
) -> dict[str, dict[str, Any]]:
    """Build four sensitivity charts and return Plotly JSON dicts."""
    is_call = option_type == OptionType.CALL
    style_label = "American" if is_american else "European"
    opt_label = option_type.value.capitalize()

    sigmas = np.linspace(VOL_MIN, VOL_MAX, CHART_POINTS)
    prices = [
        price_option(
            spot, strike, rate, s, time_to_expiry, steps, is_call, is_american, dividend_yield
        )
        for s in sigmas
    ]
    fig_price = go.Figure(
        go.Scatter(
            x=sigmas * 100,
            y=prices,
            mode="lines",
            line=dict(color=COLOR_PRICE, width=2.5),
            name="Option price",
        )
    )
    fig_price.update_layout(**_base_layout(
        f"{opt_label} Price vs Volatility ({style_label})",
        "Volatility (%)",
        "Option price ($)",
    ))
    current_price = float(
        price_option(spot, strike, rate, vol, time_to_expiry, steps, is_call, is_american, dividend_yield)
    )
    _add_marker(fig_price, vol * 100, current_price, "Current σ", COLOR_PRICE)

    spot_min = max(strike * 0.5, 0.01)
    spot_max = strike * 1.5
    spots = np.linspace(spot_min, spot_max, CHART_POINTS)
    deltas = [
        compute_greeks(
            s, strike, rate, vol, time_to_expiry, steps, is_call, is_american, dividend_yield
        )[1]
        for s in spots
    ]
    fig_delta = go.Figure(
        go.Scatter(
            x=spots,
            y=deltas,
            mode="lines",
            line=dict(color=COLOR_DELTA, width=2.5),
            name="Delta",
        )
    )
    fig_delta.update_layout(**_base_layout(
        f"Delta vs Stock Price ({opt_label}, {style_label})",
        "Stock price S ($)",
        "Delta (Δ)",
    ))
    current_delta = compute_greeks(
        spot, strike, rate, vol, time_to_expiry, steps, is_call, is_american, dividend_yield
    )[1]
    _add_marker(fig_delta, spot, current_delta, "Current S", COLOR_DELTA)

    t_max = max(time_to_expiry, 1 / 365)
    t_min = max(1 / 365, t_max * 0.05)
    times = np.linspace(t_min, t_max, CHART_POINTS)
    thetas = [
        compute_greeks(
            spot, strike, rate, vol, t, steps, is_call, is_american, dividend_yield
        )[3]
        for t in times
    ]
    fig_theta = go.Figure(
        go.Scatter(
            x=times * 365,
            y=thetas,
            mode="lines",
            line=dict(color=COLOR_THETA, width=2.5),
            name="Theta",
        )
    )
    fig_theta.update_layout(**_base_layout(
        f"Theta vs Time to Expiration ({opt_label}, {style_label})",
        "Time to expiration (days)",
        "Theta (Θ, per year)",
    ))
    current_theta = compute_greeks(
        spot, strike, rate, vol, time_to_expiry, steps, is_call, is_american, dividend_yield
    )[3]
    _add_marker(fig_theta, time_to_expiry * 365, current_theta, "Current T", COLOR_THETA)

    vegas = [
        compute_greeks(
            spot, strike, rate, s, time_to_expiry, steps, is_call, is_american, dividend_yield
        )[4]
        for s in sigmas
    ]
    fig_vega = go.Figure(
        go.Scatter(
            x=sigmas * 100,
            y=vegas,
            mode="lines",
            line=dict(color=COLOR_VEGA, width=2.5),
            name="Vega",
        )
    )
    fig_vega.update_layout(**_base_layout(
        f"Vega vs Volatility ({opt_label}, {style_label})",
        "Volatility (%)",
        "Vega (ν)",
    ))
    current_vega = compute_greeks(
        spot, strike, rate, vol, time_to_expiry, steps, is_call, is_american, dividend_yield
    )[4]
    _add_marker(fig_vega, vol * 100, current_vega, "Current σ", COLOR_VEGA)

    return {
        "price_vs_volatility": _figure_to_dict(fig_price),
        "delta_vs_stock_price": _figure_to_dict(fig_delta),
        "theta_vs_time_to_expiration": _figure_to_dict(fig_theta),
        "vega_vs_volatility": _figure_to_dict(fig_vega),
    }
