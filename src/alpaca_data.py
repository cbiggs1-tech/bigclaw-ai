"""Alpaca market data integration for extended hours prices.

Provides access to pre-market and after-hours stock prices
using the Alpaca Markets API.
"""

import os
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Alpaca API endpoints
ALPACA_DATA_URL = "https://data.alpaca.markets/v2"
ALPACA_PAPER_URL = "https://paper-api.alpaca.markets/v2"


def get_alpaca_client():
    """Get Alpaca REST client if credentials are configured."""
    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")

    if not api_key or not secret_key:
        logger.debug("Alpaca credentials not configured")
        return None

    try:
        from alpaca.data import StockHistoricalDataClient
        return StockHistoricalDataClient(api_key, secret_key)
    except ImportError:
        logger.warning("alpaca-py not installed - run: pip install alpaca-py")
        return None
    except Exception as e:
        logger.error(f"Failed to create Alpaca client: {e}")
        return None


def get_extended_hours_prices(tickers: list[str]) -> dict[str, dict]:
    """Get current prices including pre/post market data.

    Args:
        tickers: List of stock symbols

    Returns:
        Dict of ticker -> {price, pre_market, post_market, is_extended}
    """
    client = get_alpaca_client()
    if not client:
        return {}

    prices = {}

    try:
        from alpaca.data.requests import StockLatestQuoteRequest, StockLatestTradeRequest

        # Get latest quotes
        request = StockLatestQuoteRequest(symbol_or_symbols=tickers)
        quotes = client.get_stock_latest_quote(request)

        for ticker in tickers:
            if ticker in quotes:
                quote = quotes[ticker]
                prices[ticker] = {
                    'bid': float(quote.bid_price) if quote.bid_price else None,
                    'ask': float(quote.ask_price) if quote.ask_price else None,
                    'price': float(quote.ask_price) if quote.ask_price else None,
                    'timestamp': quote.timestamp.isoformat() if quote.timestamp else None,
                }

        # Get latest trades for more accurate prices
        trade_request = StockLatestTradeRequest(symbol_or_symbols=tickers)
        trades = client.get_stock_latest_trade(trade_request)

        for ticker in tickers:
            if ticker in trades:
                trade = trades[ticker]
                if ticker not in prices:
                    prices[ticker] = {}
                prices[ticker]['price'] = float(trade.price)
                prices[ticker]['timestamp'] = trade.timestamp.isoformat() if trade.timestamp else None

                # Check if this is extended hours
                if trade.timestamp:
                    hour = trade.timestamp.hour
                    # Pre-market: 4am-9:30am ET, Post-market: 4pm-8pm ET
                    is_extended = hour < 9 or (hour == 9 and trade.timestamp.minute < 30) or hour >= 16
                    prices[ticker]['is_extended'] = is_extended

    except Exception as e:
        logger.error(f"Error fetching Alpaca prices: {e}")

    return prices


def get_market_status() -> dict:
    """Check if market is open and get session info."""
    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")

    if not api_key or not secret_key:
        return {'is_open': False, 'session': 'unknown'}

    try:
        from alpaca.trading.client import TradingClient
        client = TradingClient(api_key, secret_key, paper=True)
        clock = client.get_clock()

        return {
            'is_open': clock.is_open,
            'next_open': clock.next_open.isoformat() if clock.next_open else None,
            'next_close': clock.next_close.isoformat() if clock.next_close else None,
            'session': 'regular' if clock.is_open else 'closed'
        }
    except Exception as e:
        logger.error(f"Error getting market status: {e}")
        return {'is_open': False, 'session': 'unknown'}


def get_best_price(ticker: str) -> Optional[float]:
    """Get the best available price for a ticker.

    Uses Alpaca for extended hours, falls back to yfinance.
    """
    # Try Alpaca first for extended hours
    alpaca_prices = get_extended_hours_prices([ticker])
    if ticker in alpaca_prices and alpaca_prices[ticker].get('price'):
        return alpaca_prices[ticker]['price']

    # Fall back to yfinance
    try:
        import yfinance as yf
        stock = yf.Ticker(ticker)
        info = stock.info
        return info.get('regularMarketPrice') or info.get('currentPrice')
    except:
        return None


if __name__ == "__main__":
    # Test the module
    import sys
    from dotenv import load_dotenv
    load_dotenv()

    logging.basicConfig(level=logging.INFO)

    test_tickers = ["AAPL", "NVDA", "TSLA"]

    print("Testing Alpaca data...")
    print(f"Market status: {get_market_status()}")

    prices = get_extended_hours_prices(test_tickers)
    for ticker, data in prices.items():
        print(f"{ticker}: ${data.get('price', 'N/A'):.2f} (extended: {data.get('is_extended', 'N/A')})")
