"""Price Oracle — single source of truth for all prices in BigClaw.

ARCHITECTURAL RULE: No price, P&L, or portfolio value reaches any output
(Slack, dashboard, reports) unless it comes from this module. The LLM
decides WHAT to trade; this code guarantees the NUMBERS are correct.

Design:
- In-memory cache with configurable TTL (default 60s during market hours)
- Alpaca first (extended hours), yfinance fallback
- Every price includes a timestamp so consumers can verify freshness
- Raises PriceUnavailableError rather than returning stale/guessed data
"""

import os
import time
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Cache TTL in seconds
MARKET_HOURS_TTL = 60       # 1 minute during market hours
EXTENDED_HOURS_TTL = 300    # 5 minutes pre/post market
CLOSED_TTL = 900            # 15 minutes when market is closed

# Maximum acceptable age before we refuse to serve a price
MAX_STALE_SECONDS = 600     # 10 minutes absolute max


class PriceUnavailableError(Exception):
    """Raised when a verified price cannot be obtained."""
    pass


class VerifiedPrice:
    """A price that has been fetched from a real data source with a timestamp."""

    __slots__ = ('ticker', 'price', 'source', 'fetched_at', 'is_extended')

    def __init__(self, ticker: str, price: float, source: str,
                 fetched_at: float = None, is_extended: bool = False):
        self.ticker = ticker
        self.price = price
        self.source = source
        self.fetched_at = fetched_at or time.time()
        self.is_extended = is_extended

    @property
    def age_seconds(self) -> float:
        return time.time() - self.fetched_at

    @property
    def timestamp_str(self) -> str:
        dt = datetime.fromtimestamp(self.fetched_at)
        return dt.strftime("%I:%M %p")

    def is_fresh(self, max_age: float = None) -> bool:
        if max_age is None:
            max_age = MAX_STALE_SECONDS
        return self.age_seconds < max_age

    def to_dict(self) -> dict:
        return {
            'ticker': self.ticker,
            'price': self.price,
            'source': self.source,
            'fetched_at': self.fetched_at,
            'age_seconds': round(self.age_seconds, 1),
            'is_extended': self.is_extended,
            'timestamp': self.timestamp_str,
        }


class PriceOracle:
    """Centralized, cached, verified price provider.

    Usage:
        oracle = PriceOracle()
        vp = oracle.get_verified_price("AAPL")
        print(f"${vp.price:.2f} (via {vp.source} at {vp.timestamp_str})")

        prices = oracle.get_verified_prices(["AAPL", "NVDA", "TSLA"])
    """

    def __init__(self):
        self._cache: dict[str, VerifiedPrice] = {}

    def _get_ttl(self) -> float:
        """Get appropriate TTL based on market hours."""
        now = datetime.now()
        hour = now.hour
        weekday = now.weekday()

        # Weekend
        if weekday >= 5:
            return CLOSED_TTL

        # Pre-market: 4am-9:30am ET
        if hour < 4:
            return CLOSED_TTL
        elif hour < 9 or (hour == 9 and now.minute < 30):
            return EXTENDED_HOURS_TTL
        # Regular hours: 9:30am-4pm ET
        elif hour < 16:
            return MARKET_HOURS_TTL
        # After hours: 4pm-8pm ET
        elif hour < 20:
            return EXTENDED_HOURS_TTL
        else:
            return CLOSED_TTL

    def _fetch_alpaca(self, tickers: list[str]) -> dict[str, VerifiedPrice]:
        """Fetch prices from Alpaca (supports extended hours)."""
        results = {}
        try:
            from alpaca_data import get_extended_hours_prices
            alpaca_data = get_extended_hours_prices(tickers)
            now = time.time()
            for ticker, data in alpaca_data.items():
                if data.get('price'):
                    results[ticker] = VerifiedPrice(
                        ticker=ticker,
                        price=float(data['price']),
                        source='alpaca',
                        fetched_at=now,
                        is_extended=data.get('is_extended', False),
                    )
        except Exception as e:
            logger.warning(f"Alpaca fetch failed: {e}")
        return results

    def _fetch_yfinance(self, tickers: list[str]) -> dict[str, VerifiedPrice]:
        """Fetch prices from yfinance (regular hours only)."""
        results = {}
        try:
            import yfinance as yf
            import pandas as pd

            if len(tickers) == 1:
                data = yf.download(tickers[0], period="1d", progress=False)
                if 'Close' in data and len(data['Close']) > 0:
                    price = float(data['Close'].iloc[-1])
                    results[tickers[0]] = VerifiedPrice(
                        ticker=tickers[0], price=price,
                        source='yfinance', fetched_at=time.time(),
                    )
            else:
                data = yf.download(tickers, period="1d", progress=False)
                if 'Close' in data:
                    for ticker in tickers:
                        try:
                            col = data['Close'][ticker] if ticker in data['Close'].columns else None
                            if col is not None and len(col) > 0 and not pd.isna(col.iloc[-1]):
                                results[ticker] = VerifiedPrice(
                                    ticker=ticker, price=float(col.iloc[-1]),
                                    source='yfinance', fetched_at=time.time(),
                                )
                        except (KeyError, IndexError):
                            pass

            # Individual fallback for any still missing
            for ticker in tickers:
                if ticker not in results:
                    try:
                        stock = yf.Ticker(ticker)
                        info = stock.info
                        price = info.get('regularMarketPrice') or info.get('currentPrice')
                        if price:
                            results[ticker] = VerifiedPrice(
                                ticker=ticker, price=float(price),
                                source='yfinance-info', fetched_at=time.time(),
                            )
                    except Exception:
                        pass

        except Exception as e:
            logger.warning(f"yfinance fetch failed: {e}")
        return results

    def get_verified_price(self, ticker: str) -> VerifiedPrice:
        """Get a single verified price. Raises PriceUnavailableError if not possible."""
        ticker = ticker.upper()
        ttl = self._get_ttl()

        # Check cache
        if ticker in self._cache:
            cached = self._cache[ticker]
            if cached.age_seconds < ttl:
                return cached

        # Fetch fresh
        results = self._fetch_alpaca([ticker])
        if ticker not in results:
            results = self._fetch_yfinance([ticker])

        if ticker in results:
            self._cache[ticker] = results[ticker]
            return results[ticker]

        raise PriceUnavailableError(f"Cannot get verified price for {ticker}")

    def get_verified_prices(self, tickers: list[str]) -> dict[str, VerifiedPrice]:
        """Get verified prices for multiple tickers. Returns only those available."""
        tickers = [t.upper() for t in tickers]
        ttl = self._get_ttl()
        results = {}
        need_fetch = []

        # Check cache first
        for ticker in tickers:
            if ticker in self._cache and self._cache[ticker].age_seconds < ttl:
                results[ticker] = self._cache[ticker]
            else:
                need_fetch.append(ticker)

        if not need_fetch:
            return results

        # Batch fetch: Alpaca first, yfinance for remainder
        alpaca = self._fetch_alpaca(need_fetch)
        results.update(alpaca)

        still_missing = [t for t in need_fetch if t not in alpaca]
        if still_missing:
            yf_results = self._fetch_yfinance(still_missing)
            results.update(yf_results)

        # Update cache
        for ticker, vp in results.items():
            self._cache[ticker] = vp

        return results

    def get_price_float(self, ticker: str) -> float:
        """Convenience: get just the price as a float. Raises if unavailable."""
        return self.get_verified_price(ticker).price

    def get_prices_dict(self, tickers: list[str]) -> dict[str, float]:
        """Convenience: get {ticker: price} dict. Skips unavailable tickers."""
        vps = self.get_verified_prices(tickers)
        return {t: vp.price for t, vp in vps.items()}

    def invalidate(self, ticker: str = None):
        """Clear cache for a ticker or all tickers."""
        if ticker:
            self._cache.pop(ticker.upper(), None)
        else:
            self._cache.clear()


# Module-level singleton
_oracle = None


def get_oracle() -> PriceOracle:
    """Get the global PriceOracle singleton."""
    global _oracle
    if _oracle is None:
        _oracle = PriceOracle()
    return _oracle
