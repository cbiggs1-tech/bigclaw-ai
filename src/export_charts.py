#!/usr/bin/env python3
"""
BigClaw Chart Data Generator

Generates per-ticker JSON files with OHLCV, MACD, RSI, and Monte Carlo data
for the interactive charts on the BigClaw website.

Usage:
    python3 src/export_charts.py              # All tickers from signals + portfolios
    python3 src/export_charts.py TSLA NVDA    # Specific tickers only
"""

import os
import sys
import json
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DATA = os.path.join(REPO_ROOT, "docs", "data")
CHARTS_DIR = os.path.join(DOCS_DATA, "charts")


def get_all_tickers():
    """Read unique tickers from signals.json and portfolios.json."""
    tickers = set()
    for fname in ["signals.json", "portfolios.json"]:
        path = os.path.join(DOCS_DATA, fname)
        try:
            with open(path) as f:
                data = json.load(f)
            for s in data.get("signals", []):
                if s.get("ticker"):
                    tickers.add(s["ticker"])
            for p in data.get("portfolios", []):
                for h in p.get("holdings", []):
                    if h.get("ticker"):
                        tickers.add(h["ticker"])
        except Exception:
            pass
    return sorted(tickers)


def compute_ohlcv(hist):
    """Convert yfinance DataFrame to list of compact dicts."""
    rows = []
    for dt, row in hist.iterrows():
        rows.append({
            "t": dt.strftime("%Y-%m-%d"),
            "o": round(float(row["Open"]), 4),
            "h": round(float(row["High"]), 4),
            "l": round(float(row["Low"]), 4),
            "c": round(float(row["Close"]), 4),
            "v": int(row["Volume"])
        })
    return rows


def compute_macd(closes, dates):
    """EMA12/26/9 MACD — same math as src/tools/technical.py lines 74-78."""
    closes_s = pd.Series(closes)
    exp1 = closes_s.ewm(span=12, adjust=False).mean()
    exp2 = closes_s.ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()
    histogram = macd - signal
    return {
        "dates": dates,
        "macd": [round(x, 6) for x in macd.tolist()],
        "signal": [round(x, 6) for x in signal.tolist()],
        "histogram": [round(x, 6) for x in histogram.tolist()]
    }


def compute_rsi(closes, dates, period=14):
    """14-period RSI — same math as src/tools/technical.py lines 184-188."""
    closes_s = pd.Series(closes)
    delta = closes_s.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return {
        "dates": dates,
        "values": [round(x, 2) if not np.isnan(x) else None for x in rsi.tolist()]
    }


def compute_montecarlo(closes, days_forward=60, simulations=500):
    """Monte Carlo GBM — same math as src/tools/technical.py lines 412-437."""
    closes_s = pd.Series(closes)
    returns = closes_s.pct_change().dropna()
    mu = returns.mean()
    sigma = returns.std()
    current_price = closes[-1]

    np.random.seed(42)
    sims = np.zeros((simulations, days_forward))
    for i in range(simulations):
        prices = [current_price]
        for _ in range(days_forward - 1):
            prices.append(prices[-1] * (1 + np.random.normal(mu, sigma)))
        sims[i] = prices

    return {
        "currentPrice": round(float(current_price), 2),
        "days": days_forward,
        "simulations": simulations,
        "p5":  [round(float(x), 2) for x in np.percentile(sims, 5, axis=0)],
        "p25": [round(float(x), 2) for x in np.percentile(sims, 25, axis=0)],
        "p50": [round(float(x), 2) for x in np.percentile(sims, 50, axis=0)],
        "p75": [round(float(x), 2) for x in np.percentile(sims, 75, axis=0)],
        "p95": [round(float(x), 2) for x in np.percentile(sims, 95, axis=0)]
    }


def export_chart_data_batch(tickers):
    """Batch download OHLCV then compute indicators per-ticker."""
    os.makedirs(CHARTS_DIR, exist_ok=True)

    print(f"[export_charts] Batch downloading {len(tickers)} tickers...")
    raw = yf.download(tickers, period="1y", progress=False, threads=True)

    if raw.empty:
        print("[export_charts] No data returned from yfinance")
        return

    generated = datetime.now(timezone.utc).isoformat()
    count = 0

    for ticker in tickers:
        try:
            # Extract single-ticker slice from batch data
            if len(tickers) == 1:
                hist = raw.copy()
            else:
                hist = pd.DataFrame({
                    "Open":   raw["Open"][ticker],
                    "High":   raw["High"][ticker],
                    "Low":    raw["Low"][ticker],
                    "Close":  raw["Close"][ticker],
                    "Volume": raw["Volume"][ticker]
                }).dropna()

            if len(hist) < 30:
                print(f"[export_charts] Skipping {ticker} — only {len(hist)} rows")
                continue

            dates = [d.strftime("%Y-%m-%d") for d in hist.index]
            closes = hist["Close"].tolist()

            data = {
                "ticker": ticker,
                "generated": generated,
                "ohlcv": compute_ohlcv(hist),
                "macd": compute_macd(closes, dates),
                "rsi": compute_rsi(closes, dates),
                "montecarlo": compute_montecarlo(closes)
            }

            path = os.path.join(CHARTS_DIR, f"{ticker}.json")
            with open(path, "w") as f:
                json.dump(data, f)
            count += 1

        except Exception as e:
            print(f"[export_charts] Error for {ticker}: {e}")

    print(f"[export_charts] Done — wrote {count}/{len(tickers)} ticker files")


def run():
    """Entry point for pipeline integration."""
    tickers = get_all_tickers()
    if not tickers:
        print("[export_charts] No tickers found in signals/portfolios JSON")
        return
    export_chart_data_batch(tickers)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        tickers = [t.upper() for t in sys.argv[1:]]
        export_chart_data_batch(tickers)
    else:
        run()
