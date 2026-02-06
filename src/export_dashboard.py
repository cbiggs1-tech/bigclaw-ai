"""Export BigClaw data to GitHub Pages dashboard.

This script reads portfolio data from the SQLite database,
fetches current prices, and exports JSON files for the web dashboard.
It then commits and pushes changes to GitHub.
"""

import os
import json
import logging
import subprocess
from datetime import datetime
from typing import Optional

import pandas as pd
import yfinance as yf

from portfolio import (
    get_active_portfolios,
    list_portfolios,
    Portfolio,
)

logger = logging.getLogger(__name__)

# Path to docs/data folder (relative to repo root)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DATA_PATH = os.path.join(REPO_ROOT, "docs", "data")


def get_current_prices(tickers: list[str]) -> dict[str, float]:
    """Fetch current prices for a list of tickers."""
    prices = {}
    if not tickers:
        return prices

    try:
        # Batch fetch for efficiency
        data = yf.download(tickers, period="1d", progress=False)
        if len(tickers) == 1:
            # Single ticker returns Series, not DataFrame
            ticker = tickers[0]
            if 'Close' in data and len(data['Close']) > 0:
                prices[ticker] = float(data['Close'].iloc[-1])
        else:
            # Multiple tickers
            if 'Close' in data:
                for ticker in tickers:
                    if ticker in data['Close'].columns:
                        close = data['Close'][ticker].iloc[-1]
                        if not pd.isna(close):
                            prices[ticker] = float(close)
    except Exception as e:
        logger.warning(f"Error fetching prices: {e}")

    # Fallback: fetch individually for any missing
    for ticker in tickers:
        if ticker not in prices:
            try:
                stock = yf.Ticker(ticker)
                info = stock.info
                prices[ticker] = info.get('regularMarketPrice') or info.get('currentPrice', 0)
            except:
                pass

    return prices


def export_portfolios() -> dict:
    """Export portfolio data to JSON format."""
    portfolios_data = []
    all_tickers = set()

    # Get all portfolios
    portfolio_list = list_portfolios()

    for p_info in portfolio_list:
        if not p_info.get('is_active'):
            continue

        portfolio = Portfolio(p_info['id'])
        holdings = portfolio.get_holdings()

        # Collect tickers for price fetch
        for h in holdings:
            all_tickers.add(h['ticker'])

        portfolios_data.append({
            'id': p_info['id'],
            'name': portfolio.name,
            'style': portfolio.investment_style,
            'starting_cash': portfolio.starting_cash,
            'current_cash': portfolio.current_cash,
            'holdings_raw': holdings  # Will be enriched with prices
        })

    # Fetch all current prices at once
    prices = get_current_prices(list(all_tickers))

    # Calculate values and format output
    output_portfolios = []
    for p in portfolios_data:
        holdings = []
        holdings_value = 0

        for h in p['holdings_raw']:
            ticker = h['ticker']
            current_price = prices.get(ticker, h['avg_cost'])
            value = h['shares'] * current_price
            holdings_value += value

            holdings.append({
                'ticker': ticker,
                'shares': round(h['shares'], 2),
                'avgCost': round(h['avg_cost'], 2),
                'currentPrice': round(current_price, 2)
            })

        total_value = p['current_cash'] + holdings_value
        total_return = ((total_value - p['starting_cash']) / p['starting_cash']) * 100

        output_portfolios.append({
            'name': p['name'],
            'style': p['style'],
            'totalValue': round(total_value, 2),
            'startingCash': round(p['starting_cash'], 2),
            'totalReturn': round(total_return, 2),
            'holdings': holdings
        })

    return {
        'lastUpdate': datetime.utcnow().isoformat() + 'Z',
        'portfolios': output_portfolios
    }


def export_sentiment(sentiment_data: Optional[dict] = None) -> dict:
    """Export sentiment data to JSON format.

    Args:
        sentiment_data: Optional dict with ticker -> sentiment info.
                       If None, exports empty/placeholder data.
    """
    if sentiment_data:
        tickers = []
        for ticker, data in sentiment_data.items():
            tickers.append({
                'ticker': ticker if ticker.startswith('$') else f'${ticker}',
                'bullishPercent': data.get('bullish_percent', 50),
                'tweetCount': data.get('tweet_count', 0)
            })
        return {
            'lastUpdate': datetime.utcnow().isoformat() + 'Z',
            'tickers': tickers
        }

    # Return existing data if no new sentiment provided
    sentiment_path = os.path.join(DOCS_DATA_PATH, 'sentiment.json')
    if os.path.exists(sentiment_path):
        with open(sentiment_path, 'r') as f:
            return json.load(f)

    return {
        'lastUpdate': datetime.utcnow().isoformat() + 'Z',
        'tickers': []
    }


def export_metadata() -> dict:
    """Export metadata with timestamps."""
    now = datetime.now()

    # Format nice timestamp
    last_update = now.strftime("%B %d, %Y at %I:%M %p CT")

    # Next update time (next market hours)
    if now.hour < 9:
        next_update = now.replace(hour=9, minute=0).strftime("%B %d, %Y at %I:%M %p CT")
    elif now.hour < 16:
        next_update = now.replace(hour=16, minute=30).strftime("%B %d, %Y at %I:%M %p CT")
    else:
        # Tomorrow morning
        from datetime import timedelta
        tomorrow = now + timedelta(days=1)
        next_update = tomorrow.replace(hour=9, minute=0).strftime("%B %d, %Y at %I:%M %p CT")

    return {
        'lastUpdate': last_update,
        'nextUpdate': next_update,
        'version': '1.0.0'
    }


def save_json_files(portfolios: dict, sentiment: dict, metadata: dict):
    """Save all JSON files to docs/data folder."""
    os.makedirs(DOCS_DATA_PATH, exist_ok=True)

    files = {
        'portfolios.json': portfolios,
        'sentiment.json': sentiment,
        'metadata.json': metadata
    }

    for filename, data in files.items():
        filepath = os.path.join(DOCS_DATA_PATH, filename)
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info(f"Saved {filepath}")


def push_to_github():
    """Commit and push changes to GitHub."""
    try:
        # Change to repo directory
        os.chdir(REPO_ROOT)

        # Check if there are changes
        result = subprocess.run(
            ['git', 'status', '--porcelain', 'docs/data/'],
            capture_output=True, text=True
        )

        if not result.stdout.strip():
            logger.info("No changes to push")
            return True

        # Add changes
        subprocess.run(['git', 'add', 'docs/data/'], check=True)

        # Commit
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        commit_msg = f"Update dashboard data - {timestamp}"
        subprocess.run(
            ['git', 'commit', '-m', commit_msg],
            check=True
        )

        # Push
        subprocess.run(['git', 'push'], check=True)

        logger.info("Successfully pushed dashboard updates to GitHub")
        return True

    except subprocess.CalledProcessError as e:
        logger.error(f"Git operation failed: {e}")
        return False
    except Exception as e:
        logger.error(f"Error pushing to GitHub: {e}")
        return False


def export_dashboard(sentiment_data: Optional[dict] = None) -> bool:
    """Main export function - call this after reports.

    Args:
        sentiment_data: Optional dict of sentiment data from the latest analysis.

    Returns:
        True if export and push succeeded.
    """
    logger.info("Exporting dashboard data...")

    try:
        # Export all data
        portfolios = export_portfolios()
        sentiment = export_sentiment(sentiment_data)
        metadata = export_metadata()

        # Save files
        save_json_files(portfolios, sentiment, metadata)

        # Push to GitHub
        success = push_to_github()

        if success:
            logger.info("Dashboard export complete!")

        return success

    except Exception as e:
        logger.error(f"Dashboard export failed: {e}")
        return False


if __name__ == "__main__":
    # For testing - run standalone
    import sys
    logging.basicConfig(level=logging.INFO)

    success = export_dashboard()
    sys.exit(0 if success else 1)
