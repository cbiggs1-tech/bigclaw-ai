"""Export BigClaw data to GitHub Pages dashboard.

This script reads portfolio data from the SQLite database,
fetches current prices, and exports JSON files for the web dashboard.
It then commits and pushes changes to GitHub.
"""

import os
import json
import logging
import subprocess
import re
from datetime import datetime, date
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
    """Fetch current prices for a list of tickers.

    Uses Alpaca for extended hours data when available,
    falls back to yfinance for regular hours.
    """
    prices = {}
    if not tickers:
        return prices

    # Try Alpaca first for extended hours data
    try:
        from alpaca_data import get_extended_hours_prices
        alpaca_prices = get_extended_hours_prices(tickers)
        for ticker, data in alpaca_prices.items():
            if data.get('price'):
                prices[ticker] = data['price']
                logger.debug(f"Got {ticker} price from Alpaca: ${data['price']:.2f}")
    except ImportError:
        logger.debug("Alpaca module not available")
    except Exception as e:
        logger.warning(f"Alpaca price fetch failed: {e}")

    # Get remaining tickers from yfinance
    missing_tickers = [t for t in tickers if t not in prices]
    if missing_tickers:
        try:
            # Batch fetch for efficiency
            data = yf.download(missing_tickers, period="1d", progress=False)
            if len(missing_tickers) == 1:
                # Single ticker returns Series, not DataFrame
                ticker = missing_tickers[0]
                if 'Close' in data and len(data['Close']) > 0:
                    prices[ticker] = float(data['Close'].iloc[-1])
            else:
                # Multiple tickers
                if 'Close' in data:
                    for ticker in missing_tickers:
                        if ticker in data['Close'].columns:
                            close = data['Close'][ticker].iloc[-1]
                            if not pd.isna(close):
                                prices[ticker] = float(close)
        except Exception as e:
            logger.warning(f"Error fetching prices from yfinance: {e}")

        # Fallback: fetch individually for any still missing
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
            'created_at': portfolio.created_at,
            'purchase_status': p_info.get('purchase_status', 'active'),
            'holdings_raw': holdings  # Will be enriched with prices
        })

    # Auto-detect pending→active: if cash < 10% of starting, portfolio is deployed
    import sqlite3 as _sql
    _db = _sql.connect(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'portfolios.db'))
    for p in portfolios_data:
        if p['purchase_status'] == 'pending' and p['holdings_raw']:
            cash_pct = (p['current_cash'] / p['starting_cash'] * 100) if p['starting_cash'] > 0 else 100
            if cash_pct < 10:
                _db.execute("UPDATE portfolios SET purchase_status='active' WHERE id=?", (p['id'],))
                p['purchase_status'] = 'active'
                logger.info(f"Auto-activated portfolio {p['name']} ({cash_pct:.1f}% cash)")
    _db.commit()
    _db.close()

    # Fetch all current prices at once
    prices = get_current_prices(list(all_tickers))

    # Fetch previous close prices for daily return
    prev_closes = {}
    try:
        import yfinance as _yf
        _data = _yf.download(list(all_tickers), period="5d", progress=False, threads=True)
        if 'Close' in _data.columns or len(all_tickers) == 1:
            _close = _data['Close'] if len(all_tickers) > 1 else _data[['Close']]
            if hasattr(_close, 'iloc') and len(_close) >= 2:
                _row = _close.iloc[-2]
                for _t in all_tickers:
                    _col = _t if _t in _row.index else None
                    if _col and not (_row[_col] != _row[_col]):
                        prev_closes[_t] = float(_row[_col])
    except Exception:
        pass

    # Calculate values and format output
    output_portfolios = []
    for p in portfolios_data:
        holdings = []
        holdings_value = 0
        prev_holdings_value = 0

        for h in p['holdings_raw']:
            ticker = h['ticker']
            current_price = prices.get(ticker, h['avg_cost'])
            prev_price = prev_closes.get(ticker, current_price)
            value = h['shares'] * current_price
            prev_value = h['shares'] * prev_price
            holdings_value += value
            prev_holdings_value += prev_value

            # Format purchase date
            purchased_at = h.get('first_bought_at', '')
            if purchased_at:
                # Parse and format the date nicely
                try:
                    dt = datetime.fromisoformat(purchased_at.replace('Z', '+00:00'))
                    purchased_at = dt.strftime('%b %d, %Y')
                except:
                    purchased_at = purchased_at[:10] if len(purchased_at) >= 10 else purchased_at

            holdings.append({
                'ticker': ticker,
                'shares': round(h['shares'], 2),
                'avgCost': round(h['avg_cost'], 2),
                'currentPrice': round(current_price, 2),
                'purchasedAt': purchased_at
            })

        total_value = p['current_cash'] + holdings_value
        prev_total_value = p['current_cash'] + prev_holdings_value
        total_return = ((total_value - p['starting_cash']) / p['starting_cash']) * 100
        daily_return = ((total_value - prev_total_value) / prev_total_value * 100) if prev_total_value > 0 else 0

        output_portfolios.append({
            'name': p['name'],
            'style': p['style'],
            'totalValue': round(total_value, 2),
            'prevTotalValue': round(prev_total_value, 2),
            'startingCash': round(p['starting_cash'], 2),
            'totalReturn': round(total_return, 2),
            'dailyReturn': round(daily_return, 2),
            'createdAt': p['created_at'],
            'purchaseStatus': p.get('purchase_status', 'active'),
            'holdings': holdings
        })

    return {
        'lastUpdate': datetime.utcnow().isoformat() + 'Z',
        'portfolios': output_portfolios
    }


def export_analysis(analysis_text: str, portfolio_name: str = None) -> dict:
    """Export BigClaw analysis report to JSON format.

    Args:
        analysis_text: The analysis text from the trading agent.
        portfolio_name: Optional name of the portfolio analyzed.

    Returns:
        Dict with the analysis data.
    """
    now = datetime.now()
    hour = now.hour

    # Determine if this is morning or evening report
    if hour < 12:
        report_type = "Morning Analysis"
    else:
        report_type = "Evening Analysis"

    return {
        'lastUpdate': now.isoformat() + 'Z',
        'timestamp': now.strftime("%B %d, %Y at %I:%M %p ET"),
        'reportType': report_type,
        'portfolioName': portfolio_name or "All Portfolios",
        'content': analysis_text
    }


def save_analysis_report(analysis_text: str, portfolio_name: str = None):
    """Save analysis report to JSON file.

    Args:
        analysis_text: The analysis text from the trading agent.
        portfolio_name: Optional name of the portfolio analyzed.
    """
    os.makedirs(DOCS_DATA_PATH, exist_ok=True)

    analysis = export_analysis(analysis_text, portfolio_name)

    filepath = os.path.join(DOCS_DATA_PATH, 'analysis.json')
    with open(filepath, 'w') as f:
        json.dump(analysis, f, indent=2)

    logger.info(f"Saved analysis report to {filepath}")


def save_portfolio_analysis(analysis_text: str, portfolio_name: str = None):
    """Save portfolio analysis report to JSON file.

    This is separate from the market sentiment report - this contains
    analysis of the model portfolios (holdings, performance, recommendations).

    Args:
        analysis_text: The portfolio analysis text from the trading agent.
        portfolio_name: Optional name of the portfolio analyzed.
    """
    os.makedirs(DOCS_DATA_PATH, exist_ok=True)

    now = datetime.now()

    data = {
        'lastUpdate': now.isoformat() + 'Z',
        'timestamp': now.strftime("%B %d, %Y at %I:%M %p ET"),
        'reportType': "Portfolio Analysis",
        'portfolioName': portfolio_name or "All Portfolios",
        'content': analysis_text
    }

    filepath = os.path.join(DOCS_DATA_PATH, 'portfolio_analysis.json')
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

    logger.info(f"Saved portfolio analysis to {filepath}")


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


def export_news() -> dict:
    """Fetch and export news from Motley Fool RSS feeds."""
    try:
        import feedparser
    except ImportError:
        logger.warning("feedparser not installed - skipping news export")
        return {'lastUpdate': datetime.utcnow().isoformat() + 'Z', 'articles': []}

    # Motley Fool RSS feeds
    feeds = {
        "main": "https://www.fool.com/feeds/index.aspx",
        "investing": "https://www.fool.com/feeds/investing-news.aspx",
    }

    all_articles = []
    seen_links = set()

    for category, url in feeds.items():
        try:
            feed = feedparser.parse(url)

            for entry in feed.entries[:10]:  # Limit per feed
                link = entry.get("link", "")

                # Skip duplicates
                if link in seen_links:
                    continue
                seen_links.add(link)

                title = entry.get("title", "No title")
                summary = entry.get("summary", "")
                published = entry.get("published", "")

                # Clean HTML from summary
                if summary:
                    summary = re.sub(r'<[^>]+>', '', summary)
                    summary = summary[:200] + "..." if len(summary) > 200 else summary

                all_articles.append({
                    "title": title,
                    "link": link,
                    "summary": summary,
                    "published": published,
                    "source": "Motley Fool"
                })

        except Exception as e:
            logger.warning(f"Error fetching {category} feed: {e}")
            continue

    # Limit to 10 most recent articles
    articles = all_articles[:10]

    logger.info(f"Exported {len(articles)} news articles")

    return {
        'lastUpdate': datetime.utcnow().isoformat() + 'Z',
        'articles': articles
    }


def export_market() -> dict:
    """Export market indices data (S&P 500, Dow, Nasdaq)."""
    indices = {
        'spy': 'SPY',      # S&P 500 ETF
        'dji': 'DIA',      # Dow Jones ETF
        'nasdaq': 'QQQ'    # Nasdaq ETF
    }

    result = {
        'lastUpdate': datetime.utcnow().isoformat() + 'Z'
    }

    for key, ticker in indices.items():
        try:
            stock = yf.Ticker(ticker)
            # Get today's data
            hist = stock.history(period='2d')
            if len(hist) >= 2:
                prev_close = hist['Close'].iloc[-2]
                current = hist['Close'].iloc[-1]
                change_pct = ((current - prev_close) / prev_close) * 100
                result[key] = {
                    'price': round(current, 2),
                    'change': round(change_pct, 2)
                }
            elif len(hist) == 1:
                # Only today's data available
                info = stock.info
                prev_close = info.get('previousClose', hist['Close'].iloc[-1])
                current = hist['Close'].iloc[-1]
                change_pct = ((current - prev_close) / prev_close) * 100
                result[key] = {
                    'price': round(current, 2),
                    'change': round(change_pct, 2)
                }
        except Exception as e:
            logger.warning(f"Error fetching {ticker}: {e}")
            result[key] = {'price': 0, 'change': 0}

    # ── Sector Rotation Heatmap (1-month returns via sector ETFs) ──
    sector_etfs = {
        'Technology': 'XLK',
        'Healthcare': 'XLV',
        'Financials': 'XLF',
        'Energy': 'XLE',
        'Consumer Disc.': 'XLY',
        'Industrials': 'XLI',
        'Utilities': 'XLU',
        'Real Estate': 'XLRE',
        'Materials': 'XLB',
        'Comm. Services': 'XLC',
        'Consumer Staples': 'XLP',
    }
    sectors = []
    try:
        tickers_str = ' '.join(sector_etfs.values())
        hist = yf.download(tickers_str, period='1mo', progress=False)['Close']
        for sector_name, etf in sector_etfs.items():
            try:
                col = etf if etf in hist.columns else None
                if col is None:
                    continue
                start = hist[col].dropna().iloc[0]
                end = hist[col].dropna().iloc[-1]
                ret_1mo = round(((end - start) / start) * 100, 2)
                sectors.append({'sector': sector_name, 'etf': etf, '1mo': ret_1mo})
            except Exception:
                pass
        sectors.sort(key=lambda x: x['1mo'], reverse=True)
    except Exception as e:
        logger.warning(f"Sector fetch failed: {e}")
    result['sectors'] = sectors

    logger.info(f"Exported market data: SPY {result.get('spy', {}).get('change', 0):+.2f}%, {len(sectors)} sectors")
    return result


def export_earnings(tickers: list) -> list:
    """Fetch upcoming earnings dates for a list of tickers.

    Returns a list of dicts with upcoming earnings only (dates >= today).
    """
    import re
    from datetime import date as _date
    today = _date.today()
    results = []
    seen = set()

    for ticker in tickers:
        try:
            result = subprocess.run(
                ['python3', os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 '../../.openclaw/workspace/scripts/economic_calendar.py'), '--earnings', ticker],
                capture_output=True, text=True, timeout=15
            )
            output = result.stdout
            # Parse: "📊 **NVDA** — 2026-05-20 | EPS est: $1.78 | Rev est: ..."
            match = re.search(r'\*\*(\w[\w.-]*)\*\*\s*[—-]\s*(\d{4}-\d{2}-\d{2})', output)
            if match:
                t = match.group(1)
                d_str = match.group(2)
                d = _date.fromisoformat(d_str)
                if d >= today and t not in seen:
                    seen.add(t)
                    eps_match = re.search(r'EPS est:\s*\$?([\d.]+)', output)
                    days_away = (d - today).days
                    results.append({
                        'ticker': t,
                        'date': d_str,
                        'days_away': days_away,
                        'eps_est': float(eps_match.group(1)) if eps_match else None,
                    })
        except Exception as e:
            logger.warning(f"Earnings fetch failed for {ticker}: {e}")

    results.sort(key=lambda x: x['date'])
    return results


def export_calendar(days_ahead: int = 14) -> list:
    """Generate upcoming non-earnings macro events for the next N days.

    Returns list of {name, date, icon, days_away, category} dicts, sorted by date.
    """
    from datetime import timedelta

    today = date.today()
    cutoff = today + timedelta(days=days_ahead)
    events = []

    def add(event_date, name, icon, category):
        if today <= event_date <= cutoff:
            events.append({
                "name": name,
                "date": event_date.isoformat(),
                "icon": icon,
                "days_away": (event_date - today).days,
                "category": category,
            })

    # ── FOMC Meeting dates (hardcoded schedule) ──
    fomc_dates = [
        date(2026, 3, 18),  # end of March meeting
        date(2026, 5, 6),
        date(2026, 6, 17),
        date(2026, 7, 29),
        date(2026, 9, 16),
        date(2026, 11, 4),
        date(2026, 12, 16),
    ]
    for d in fomc_dates:
        add(d, "FOMC Rate Decision", "🏦", "fed")

    # ── Nonfarm Payrolls — 1st Friday of each month ──
    def first_friday(y, m):
        d = date(y, m, 1)
        while d.weekday() != 4:  # 4 = Friday
            d += timedelta(days=1)
        return d

    # ── CPI Report — typically released ~10th-15th of the month ──
    # Use 12th as a reasonable default
    def cpi_date(y, m):
        return date(y, m, 12)

    # ── GDP Advance — last Wednesday of Jan, Apr, Jul, Oct ──
    def gdp_date(y, m):
        # Last business day of month, roughly
        import calendar
        last_day = calendar.monthrange(y, m)[1]
        d = date(y, m, last_day)
        while d.weekday() != 2:  # Wednesday
            d -= timedelta(days=1)
        return d

    for offset_m in range(3):  # current + next 2 months
        m = today.month + offset_m
        y = today.year + (m - 1) // 12
        m = ((m - 1) % 12) + 1
        add(first_friday(y, m), f"Nonfarm Payrolls ({date(y, m, 1).strftime('%b')})", "💼", "macro")
        add(cpi_date(y, m), f"CPI Inflation Report ({date(y, m, 1).strftime('%b')})", "📈", "macro")

    # ── Known catalyst dates ──
    known = [
        (date(2026, 3, 4),  "Trump Tariff Deadline", "🚨", "policy"),
        (date(2026, 3, 31), "Q1 End / Rebalancing Window", "📊", "market"),
    ]
    for d, name, icon, cat in known:
        add(d, name, icon, cat)

    events.sort(key=lambda e: e["date"])
    return events


def save_json_files(portfolios: dict, sentiment: dict, metadata: dict, news: dict, market: dict):
    """Save all JSON files to docs/data folder."""
    os.makedirs(DOCS_DATA_PATH, exist_ok=True)

    files = {
        'portfolios.json': portfolios,
        'sentiment.json': sentiment,
        'metadata.json': metadata,
        'news.json': news,
        'market.json': market
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


def generate_performance_chart():
    """Generate the portfolio performance comparison chart."""
    try:
        from generate_chart import main as generate_chart_main
        generate_chart_main()
        logger.info("Performance chart generated")
    except Exception as e:
        logger.warning(f"Failed to generate performance chart: {e}")


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
        news = export_news()
        market = export_market()

        # Export earnings and inject into signals.json (dashboard reads earnings from there)
        all_tickers = list({
            h['ticker']
            for p in portfolios.get('portfolios', [])
            for h in p.get('holdings', [])
        })
        earnings = export_earnings(all_tickers)

        # Save files
        save_json_files(portfolios, sentiment, metadata, news, market)

        # Patch earnings into signals.json
        signals_path = os.path.join(DOCS_DATA_PATH, 'signals.json')
        try:
            with open(signals_path, 'r') as f:
                signals_data = json.load(f)
            signals_data['earnings'] = earnings
            with open(signals_path, 'w') as f:
                json.dump(signals_data, f, indent=2)
            logger.info(f"Patched {len(earnings)} earnings into signals.json")
        except Exception as e:
            logger.warning(f"Could not patch signals.json with earnings: {e}")

        # Refresh live bond yields in macro.json and signals.json
        try:
            tnx = yf.download('^TNX ^FVX', period='5d', progress=False)['Close']
            ten = round(float(tnx['^TNX'].dropna().iloc[-1]), 3)
            two = round(float(tnx['^FVX'].dropna().iloc[-1]), 3)
            ten_prev = round(float(tnx['^TNX'].dropna().iloc[-5]), 3) if len(tnx['^TNX'].dropna()) >= 5 else ten
            spread = round(ten - two, 3)
            today_str = date.today().isoformat()
            bond_signals = {
                'yield_curve': {'two_year': two, 'ten_year': ten, 'spread': spread,
                                'date': today_str,
                                'assessment': 'Inverted — bearish' if spread < 0 else 'Normal & steepening — bullish' if spread > 0.3 else 'Flat — caution'},
                'credit_spreads': {'current_bps': 292.0, 'date': today_str, 'assessment': 'Tight (292bps) — bullish'},
                'ten_year': {'current': ten, 'prev': ten_prev, 'change_bps': round((ten - ten_prev) * 100, 1),
                             'date': today_str,
                             'assessment': 'Low — bullish' if ten < 3.8 else 'Stable — neutral' if ten < 4.2 else 'Elevated — bearish'},
                'scores': {'yield_curve': 1, 'credit_spreads': 1, 'ten_year_level': (2 if ten < 3.8 else 0 if ten < 4.2 else -1)},
                'combined_score': (4 if ten < 3.8 else 2 if ten < 4.2 else 1)
            }
            rates = {'fed_funds': '4.25–4.50%', 'ten_year': ten, 'two_year': two, 'yield_spread': spread, 'inverted': spread < 0}
            for fname in ['macro.json', 'signals.json']:
                fpath = os.path.join(DOCS_DATA_PATH, fname)
                if os.path.exists(fpath):
                    with open(fpath) as f:
                        d = json.load(f)
                    d['bond_signals'] = bond_signals
                    d['rates'] = rates
                    with open(fpath, 'w') as f:
                        json.dump(d, f, indent=2)
            logger.info(f"Refreshed bond yields: 10Y={ten}% 5Y={two}%")
        except Exception as e:
            logger.warning(f"Bond yield refresh failed: {e}")

        # Export calendar events (non-earnings macro events, next 14 days)
        calendar_events = export_calendar(days_ahead=14)
        calendar_path = os.path.join(DOCS_DATA_PATH, 'calendar.json')
        with open(calendar_path, 'w') as f:
            json.dump({"events": calendar_events, "lastUpdate": datetime.utcnow().isoformat() + 'Z'}, f, indent=2)
        logger.info(f"Wrote {len(calendar_events)} calendar events to calendar.json")

        # Update analysis.json timestamp (preserve existing content)
        analysis_path = os.path.join(DOCS_DATA_PATH, 'analysis.json')
        try:
            with open(analysis_path, 'r') as f:
                existing_analysis = json.load(f)
            existing_analysis['lastUpdate'] = datetime.utcnow().isoformat() + 'Z'
            with open(analysis_path, 'w') as f:
                json.dump(existing_analysis, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not update analysis.json timestamp: {e}")

        # Generate performance chart
        generate_performance_chart()

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
