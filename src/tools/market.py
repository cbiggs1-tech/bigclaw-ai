"""Market data tools for BigClaw AI - Yahoo Finance integration."""

import logging
from typing import Optional
from .base import BaseTool

logger = logging.getLogger(__name__)


class GetStockQuoteTool(BaseTool):
    """Get real-time stock quote and key metrics."""

    @property
    def name(self) -> str:
        return "get_stock_quote"

    @property
    def description(self) -> str:
        return """Get the current stock price and key metrics for a ticker symbol.

Use this when users ask about:
- Current stock price ("What's AAPL trading at?")
- Basic stock info ("Tell me about MSFT stock")
- Quick price checks

Returns: Current price, day change, volume, market cap, P/E ratio, 52-week range."""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol (e.g., 'AAPL', 'MSFT', 'GOOGL')"
                }
            },
            "required": ["ticker"]
        }

    def execute(self, ticker: str) -> str:
        try:
            import yfinance as yf
        except ImportError:
            return "Error: yfinance not installed. Run: pip install yfinance"

        ticker = ticker.upper().strip()
        logger.info(f"Fetching quote for: {ticker}")

        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            # Check if valid ticker
            if not info or info.get('regularMarketPrice') is None:
                # Try fast_info as fallback
                try:
                    fast = stock.fast_info
                    if fast and hasattr(fast, 'last_price') and fast.last_price:
                        return self._format_fast_info(ticker, fast)
                except:
                    pass
                return f"Could not find data for ticker '{ticker}'. Please verify the symbol is correct."

            return self._format_quote(ticker, info)

        except Exception as e:
            logger.error(f"Error fetching quote for {ticker}: {e}")
            return f"Error fetching data for {ticker}: {str(e)}"

    def _format_quote(self, ticker: str, info: dict) -> str:
        """Format the stock quote response."""
        name = info.get('shortName', info.get('longName', ticker))
        price = info.get('regularMarketPrice', info.get('currentPrice', 'N/A'))
        prev_close = info.get('regularMarketPreviousClose', info.get('previousClose'))

        # Calculate change
        change_str = ""
        if price != 'N/A' and prev_close:
            change = price - prev_close
            change_pct = (change / prev_close) * 100
            direction = "+" if change >= 0 else ""
            change_str = f"{direction}{change:.2f} ({direction}{change_pct:.2f}%)"

        # Format large numbers
        def fmt_num(n):
            if n is None:
                return "N/A"
            if n >= 1e12:
                return f"${n/1e12:.2f}T"
            if n >= 1e9:
                return f"${n/1e9:.2f}B"
            if n >= 1e6:
                return f"${n/1e6:.2f}M"
            return f"${n:,.0f}"

        market_cap = fmt_num(info.get('marketCap'))
        volume = info.get('regularMarketVolume', info.get('volume', 'N/A'))
        if isinstance(volume, (int, float)):
            volume = f"{volume:,.0f}"

        pe_ratio = info.get('trailingPE', info.get('forwardPE', 'N/A'))
        if isinstance(pe_ratio, float):
            pe_ratio = f"{pe_ratio:.2f}"

        week_low = info.get('fiftyTwoWeekLow', 'N/A')
        week_high = info.get('fiftyTwoWeekHigh', 'N/A')

        output = f"""**{name}** (`{ticker}`)

**Price:** ${price:.2f} {change_str}
**Volume:** {volume}
**Market Cap:** {market_cap}
**P/E Ratio:** {pe_ratio}
**52-Week Range:** ${week_low:.2f} - ${week_high:.2f}

*Data from Yahoo Finance. Prices may be delayed.*"""

        return output

    def _format_fast_info(self, ticker: str, fast) -> str:
        """Format using fast_info as fallback."""
        price = getattr(fast, 'last_price', 'N/A')
        prev = getattr(fast, 'previous_close', None)

        change_str = ""
        if price != 'N/A' and prev:
            change = price - prev
            change_pct = (change / prev) * 100
            direction = "+" if change >= 0 else ""
            change_str = f"{direction}{change:.2f} ({direction}{change_pct:.2f}%)"

        market_cap = getattr(fast, 'market_cap', None)
        if market_cap and market_cap >= 1e9:
            market_cap = f"${market_cap/1e9:.2f}B"
        elif market_cap:
            market_cap = f"${market_cap/1e6:.2f}M"
        else:
            market_cap = "N/A"

        return f"""**{ticker}**

**Price:** ${price:.2f} {change_str}
**Market Cap:** {market_cap}

*Data from Yahoo Finance. Prices may be delayed.*"""


class GetStockDetailsTool(BaseTool):
    """Get detailed company information and fundamentals."""

    @property
    def name(self) -> str:
        return "get_stock_details"

    @property
    def description(self) -> str:
        return """Get detailed company information and fundamental data for deeper analysis.

Use this when users want:
- Company overview and business description
- Fundamental analysis data (margins, growth, debt)
- Dividend information
- More detailed metrics for investment analysis

This provides more data than get_stock_quote for thorough analysis."""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol (e.g., 'AAPL', 'MSFT')"
                }
            },
            "required": ["ticker"]
        }

    def execute(self, ticker: str) -> str:
        try:
            import yfinance as yf
        except ImportError:
            return "Error: yfinance not installed. Run: pip install yfinance"

        ticker = ticker.upper().strip()
        logger.info(f"Fetching details for: {ticker}")

        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            if not info or not info.get('shortName'):
                return f"Could not find detailed data for '{ticker}'."

            return self._format_details(ticker, info)

        except Exception as e:
            logger.error(f"Error fetching details for {ticker}: {e}")
            return f"Error fetching data for {ticker}: {str(e)}"

    def _format_details(self, ticker: str, info: dict) -> str:
        """Format detailed company information."""
        name = info.get('shortName', ticker)
        sector = info.get('sector', 'N/A')
        industry = info.get('industry', 'N/A')

        # Business summary (truncate if too long)
        summary = info.get('longBusinessSummary', 'No description available.')
        if len(summary) > 500:
            summary = summary[:500] + "..."

        # Valuation metrics
        pe = info.get('trailingPE', 'N/A')
        forward_pe = info.get('forwardPE', 'N/A')
        peg = info.get('pegRatio', 'N/A')
        pb = info.get('priceToBook', 'N/A')

        def fmt_pct(val):
            if val is None:
                return "N/A"
            return f"{val*100:.2f}%"

        def fmt_ratio(val):
            if val is None or val == 'N/A':
                return "N/A"
            return f"{val:.2f}"

        # Profitability
        profit_margin = fmt_pct(info.get('profitMargins'))
        operating_margin = fmt_pct(info.get('operatingMargins'))
        roe = fmt_pct(info.get('returnOnEquity'))
        roa = fmt_pct(info.get('returnOnAssets'))

        # Growth
        revenue_growth = fmt_pct(info.get('revenueGrowth'))
        earnings_growth = fmt_pct(info.get('earningsGrowth'))

        # Dividends
        div_yield = info.get('dividendYield')
        div_yield_str = fmt_pct(div_yield) if div_yield else "None"
        payout_ratio = fmt_pct(info.get('payoutRatio'))

        # Debt
        debt_to_equity = info.get('debtToEquity', 'N/A')
        if isinstance(debt_to_equity, (int, float)):
            debt_to_equity = f"{debt_to_equity:.2f}"

        output = f"""**{name}** (`{ticker}`)
**Sector:** {sector} | **Industry:** {industry}

**Business Summary:**
{summary}

**Valuation Metrics:**
- P/E (TTM): {fmt_ratio(pe)} | Forward P/E: {fmt_ratio(forward_pe)}
- PEG Ratio: {fmt_ratio(peg)} | P/B: {fmt_ratio(pb)}

**Profitability:**
- Profit Margin: {profit_margin} | Operating Margin: {operating_margin}
- ROE: {roe} | ROA: {roa}

**Growth:**
- Revenue Growth: {revenue_growth} | Earnings Growth: {earnings_growth}

**Dividends:**
- Yield: {div_yield_str} | Payout Ratio: {payout_ratio}

**Financial Health:**
- Debt/Equity: {debt_to_equity}

*Data from Yahoo Finance.*"""

        return output


class GetYahooNewsTool(BaseTool):
    """Get recent news for a stock from Yahoo Finance."""

    @property
    def name(self) -> str:
        return "get_yahoo_news"

    @property
    def description(self) -> str:
        return """Get recent news articles for a stock ticker from Yahoo Finance.

Use this for company-specific news that might not appear in general financial news feeds.
Good for recent headlines about earnings, announcements, analyst ratings, etc."""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol (e.g., 'AAPL', 'TSLA')"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of articles (default 5, max 10)"
                }
            },
            "required": ["ticker"]
        }

    def execute(self, ticker: str, limit: int = 5) -> str:
        try:
            import yfinance as yf
        except ImportError:
            return "Error: yfinance not installed. Run: pip install yfinance"

        ticker = ticker.upper().strip()
        limit = min(max(1, limit), 10)
        logger.info(f"Fetching Yahoo news for: {ticker}")

        try:
            stock = yf.Ticker(ticker)
            news = stock.news

            if not news:
                return f"No recent news found for {ticker} on Yahoo Finance."

            articles = news[:limit]

            output = f"**Yahoo Finance News for {ticker}**\n\n"

            for i, article in enumerate(articles, 1):
                title = article.get('title', 'No title')
                publisher = article.get('publisher', 'Unknown')
                link = article.get('link', '')

                # Format timestamp if available
                timestamp = article.get('providerPublishTime')
                date_str = ""
                if timestamp:
                    from datetime import datetime
                    dt = datetime.fromtimestamp(timestamp)
                    date_str = dt.strftime("%Y-%m-%d %H:%M")

                output += f"**{i}. {title}**\n"
                output += f"   Source: {publisher}"
                if date_str:
                    output += f" | {date_str}"
                output += f"\n"
                if link:
                    output += f"   Link: {link}\n"
                output += "\n"

            return output

        except Exception as e:
            logger.error(f"Error fetching news for {ticker}: {e}")
            return f"Error fetching news for {ticker}: {str(e)}"
