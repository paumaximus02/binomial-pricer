# Binomial Option Pricer

Production-ready Cox-Ross-Rubinstein (CRR) binomial tree pricer with Numba acceleration, FastAPI, and [Massive.com](https://massive.com/docs/rest/quickstart) market data (formerly Polygon.io).

## Features

- European and American calls/puts
- Price + Greeks: delta, gamma, theta, vega
- Implied volatility solver (bisection)
- Live spot prices via Massive.com REST API

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env        # add MASSIVE_API_KEY
```

## Run

```bash
uvicorn main:app --reload
```

Or for cloud/production:

```bash
python main.py
```

Open http://127.0.0.1:8000/ for the web UI, or http://127.0.0.1:8000/docs for the Swagger API.

## Deploy

Set environment variables on your host:

- `MASSIVE_API_KEY` — required for live spot lookups
- `PORT` — optional; default is 8000 when using `python main.py`

Start command:

```bash
python main.py
```

Or:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/market/spot/{symbol}` | Latest spot price from Massive.com |
| POST | `/price` | Price option with Greeks |
| POST | `/iv` | Solve implied volatility |
| GET | `/greeks-chart` | Price, Greeks, and 4 Plotly sensitivity charts |

## Example: price an American put

```bash
curl -X POST http://127.0.0.1:8000/price ^
  -H "Content-Type: application/json" ^
  -d "{\"spot\":185,\"strike\":180,\"vol\":0.25,\"expiry\":\"2026-06-20\",\"option_type\":\"put\",\"style\":\"american\"}"
```

## Example: price using Massive spot

```bash
curl -X POST http://127.0.0.1:8000/price ^
  -H "Content-Type: application/json" ^
  -d "{\"symbol\":\"AAPL\",\"strike\":180,\"vol\":0.25,\"expiry\":\"2026-06-20\",\"option_type\":\"call\"}"
```

## Example: implied volatility

```bash
curl -X POST http://127.0.0.1:8000/iv ^
  -H "Content-Type: application/json" ^
  -d "{\"market_price\":5.2,\"spot\":185,\"strike\":180,\"expiry\":\"2026-06-20\",\"option_type\":\"call\"}"
```

## Example: Greeks charts

```bash
curl "http://127.0.0.1:8000/greeks-chart?S=100&K=100&T=1.0&r=0.05&sigma=0.25&option_type=call&american=false&q=0"
```

Returns option price, Greeks, and four Plotly chart JSON objects (`price_vs_volatility`, `delta_vs_stock_price`, `theta_vs_time_to_expiration`, `vega_vs_volatility`).

## Notes

- Theta is returned per calendar year.
- Vega is sensitivity to a 1.0 absolute vol move (not 1%).
- First request may be slower while Numba JIT compiles.
- Provide either `spot` or `symbol` in pricing/IV requests.
