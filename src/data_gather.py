"""Direct data gathering — calls tools as Python, no LLM loop needed.

This replaces the expensive pattern of using an LLM to orchestrate tool calls.
Instead, we call the tool functions directly and return raw data strings
that can be fed to a cheap model (Gemini Flash) for summarization or
to Sonnet for analytical decisions.
"""

import logging
import time
from datetime import datetime
from tools import TOOL_MAP

logger = logging.getLogger(__name__)

# Simple TTL cache to avoid redundant API calls across portfolios
_cache = {}
_CACHE_TTL = 300  # 5 minutes


def _call_tool(tool_name: str, **kwargs) -> str:
    """Safely call a tool by name, with 5-minute TTL cache."""
    cache_key = f"{tool_name}:{sorted(kwargs.items())}"
    now = time.time()

    if cache_key in _cache:
        result, ts = _cache[cache_key]
        if now - ts < _CACHE_TTL:
            logger.debug(f"Cache hit: {tool_name}")
            return result

    tool = TOOL_MAP.get(tool_name)
    if not tool:
        logger.warning(f"Tool not found: {tool_name}")
        return ""
    try:
        result = tool.execute(**kwargs)
        result = str(result) if result else ""
        _cache[cache_key] = (result, now)
        return result
    except Exception as e:
        logger.error(f"Tool {tool_name} failed: {e}")
        return f"[{tool_name} error: {e}]"


def gather_market_sentiment(tickers: list[str] = None) -> str:
    """Gather market sentiment data from all sources.

    Calls X sentiment, Motley Fool, WSB trending, and Polymarket directly.
    Returns raw concatenated data for LLM summarization.

    Args:
        tickers: Tickers to check X sentiment for (default: SPY, AAPL, NVDA, TSLA)

    Returns:
        Raw data string ready for LLM summarization
    """
    if tickers is None:
        tickers = ["$SPY", "$AAPL", "$NVDA", "$TSLA"]

    sections = []
    sections.append(f"# Market Sentiment Data — {datetime.now().strftime('%B %d, %Y')}\n")

    # 1. X/Twitter sentiment for key tickers
    logger.info("Gathering X sentiment...")
    x_data = []
    for ticker in tickers:
        result = _call_tool("get_x_sentiment", query=ticker, limit=10)
        if result and not result.startswith("["):
            x_data.append(result)
    if x_data:
        sections.append("## X/Twitter Sentiment\n" + "\n---\n".join(x_data))
    else:
        sections.append("## X/Twitter Sentiment\nNo data available.")

    # 2. Motley Fool institutional news
    logger.info("Gathering Motley Fool news...")
    mf_result = _call_tool("get_motley_fool_news", limit=5)
    if mf_result:
        sections.append("## Institutional News (Motley Fool)\n" + mf_result)

    # 3. WSB trending
    logger.info("Gathering WSB trending...")
    wsb_result = _call_tool("get_wsb_trending", limit=10)
    if wsb_result:
        sections.append("## Retail Sentiment (WallStreetBets)\n" + wsb_result)

    # 4. Polymarket predictions
    logger.info("Gathering Polymarket trends...")
    poly_result = _call_tool("get_polymarket_trending")
    if poly_result:
        sections.append("## Prediction Markets (Polymarket)\n" + poly_result)

    return "\n\n".join(sections)


def gather_portfolio_data(portfolio, holding_tickers: list[str] = None) -> str:
    """Gather all data needed for a portfolio trading decision.

    Calls sentiment and quote tools directly, returns raw data
    for Sonnet to make analytical trade decisions.

    Args:
        portfolio: Portfolio object
        holding_tickers: List of tickers currently held

    Returns:
        Raw data string ready for Sonnet analytical call
    """
    if holding_tickers is None:
        holding_tickers = []

    sections = []

    # Determine candidate stocks based on investment style (always included)
    style_lower = portfolio.investment_style.lower()
    if "cathie" in style_lower or "ark" in style_lower or "innovation" in style_lower:
        candidates = ["TSLA", "ROKU", "COIN", "PATH", "PLTR", "CRSP", "SHOP"]
    elif "value" in style_lower or "buffett" in style_lower:
        candidates = ["BRK-B", "AAPL", "BAC", "KO", "CVX", "JPM", "PG"]
    elif "momentum" in style_lower:
        candidates = ["NVDA", "AVGO", "GE", "LLY", "DECK", "META", "ANET"]
    elif "nuclear" in style_lower:
        candidates = ["CCJ", "GEV", "BWXT", "TLN", "CEG", "SMR", "LEU"]
    elif "defense" in style_lower or "ai defense" in style_lower:
        candidates = ["NOC", "RTX", "LMT", "PLTR", "KTOS", "AVAV", "LDOS"]
    elif "income" in style_lower or "dividend" in style_lower:
        candidates = ["VZ", "O", "XOM", "JNJ", "PG", "ABBV", "T"]
    else:
        candidates = ["SPY", "AAPL", "NVDA", "MSFT", "GOOGL", "AMZN"]

    # Separate holdings from new candidates (always research both)
    new_candidates = [t for t in candidates if t not in holding_tickers]
    all_tickers = list(dict.fromkeys(holding_tickers + new_candidates))[:12]

    # 1. X sentiment for holdings + top candidates
    sentiment_tickers = all_tickers[:6]
    logger.info(f"Gathering X sentiment for {sentiment_tickers}")
    x_data = []
    for ticker in sentiment_tickers:
        query = f"${ticker}" if not ticker.startswith("$") else ticker
        result = _call_tool("get_x_sentiment", query=query, limit=10)
        if result and not result.startswith("["):
            x_data.append(result)
    if x_data:
        sections.append("## X/Twitter Sentiment\n" + "\n---\n".join(x_data))

    # 2. Stocktwits for holdings + top candidates
    logger.info("Gathering Stocktwits sentiment...")
    st_data = []
    for ticker in all_tickers[:5]:
        result = _call_tool("get_stocktwits_sentiment", ticker=ticker, limit=5)
        if result and not result.startswith("[") and "unavailable" not in result.lower():
            st_data.append(result)
    if st_data:
        sections.append("## Stocktwits Sentiment\n" + "\n---\n".join(st_data))

    # 3. Stock quotes for ALL tickers (holdings + candidates)
    logger.info(f"Gathering quotes for {all_tickers}")
    quotes = []
    for ticker in all_tickers:
        result = _call_tool("get_stock_quote", ticker=ticker)
        if result and not result.startswith("["):
            quotes.append(result)
    if quotes:
        sections.append("## Current Quotes\n" + "\n---\n".join(quotes))

    # 4. Reddit mentions for top tickers
    logger.info("Gathering Reddit sentiment...")
    for ticker in all_tickers[:2]:
        result = _call_tool("search_reddit_stocks", query=ticker, limit=5)
        if result and "No recent" not in result:
            sections.append(f"## Reddit: {ticker}\n" + result)

    # Label which are current holdings vs candidates
    sections.insert(0, f"**Current holdings:** {', '.join(holding_tickers) or 'None'}\n"
                       f"**Candidate stocks:** {', '.join(new_candidates[:7])}")

    return "\n\n".join(sections)


def gather_stock_quotes(tickers: list[str]) -> dict[str, str]:
    """Get current quotes for a list of tickers.

    Args:
        tickers: List of ticker symbols

    Returns:
        Dict mapping ticker -> quote string
    """
    quotes = {}
    for ticker in tickers:
        result = _call_tool("get_stock_quote", ticker=ticker)
        if result:
            quotes[ticker] = result
    return quotes
