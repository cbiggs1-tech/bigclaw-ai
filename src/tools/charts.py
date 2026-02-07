"""Chart generation tools for BigClaw AI."""

import logging
import os
import tempfile
from datetime import datetime, timedelta
from typing import Optional

# Use non-interactive backend for matplotlib (required for threading)
import matplotlib
matplotlib.use('Agg')

from .base import BaseTool

logger = logging.getLogger(__name__)


class StockChartTool(BaseTool):
    """Generate stock price charts."""

    @property
    def name(self) -> str:
        return "generate_stock_chart"

    @property
    def description(self) -> str:
        return """Generate a stock price chart for visual analysis.

Use this when users ask to:
- See a stock chart ("Show me a chart of AAPL")
- Visualize price movement ("Graph TSLA over the last 6 months")
- Compare price trends visually

Returns a chart image that will be uploaded to Slack."""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol (e.g., 'AAPL', 'MSFT')"
                },
                "period": {
                    "type": "string",
                    "enum": ["1mo", "3mo", "6mo", "1y", "2y", "5y"],
                    "description": "Time period for the chart. Default is '6mo' (6 months)"
                },
                "chart_type": {
                    "type": "string",
                    "enum": ["line", "candle"],
                    "description": "Chart type: 'line' for simple line chart, 'candle' for candlestick. Default is 'line'"
                }
            },
            "required": ["ticker"]
        }

    def execute(
        self,
        ticker: str,
        period: str = "6mo",
        chart_type: str = "line"
    ) -> str:
        try:
            import yfinance as yf
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates
        except ImportError as e:
            return f"Error: Missing package. Run: pip install yfinance matplotlib. Details: {e}"

        ticker = ticker.upper().strip()
        logger.info(f"Generating {chart_type} chart for {ticker}, period: {period}")

        try:
            # Fetch historical data
            stock = yf.Ticker(ticker)
            hist = stock.history(period=period)

            if hist.empty:
                return f"No historical data found for {ticker}. Please verify the ticker symbol."

            # Get company name
            try:
                info = stock.info
                company_name = info.get('shortName', ticker)
            except:
                company_name = ticker

            # Create the chart
            fig, ax = plt.subplots(figsize=(12, 6))

            if chart_type == "candle":
                # Candlestick chart
                self._plot_candlestick(ax, hist)
            else:
                # Line chart
                ax.plot(hist.index, hist['Close'], linewidth=2, color='#2196F3')
                ax.fill_between(hist.index, hist['Close'], alpha=0.1, color='#2196F3')

            # Formatting
            ax.set_title(f"{company_name} ({ticker}) - {self._period_label(period)}",
                        fontsize=14, fontweight='bold', pad=20)
            ax.set_xlabel("Date", fontsize=10)
            ax.set_ylabel("Price ($)", fontsize=10)

            # Format x-axis dates
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=max(1, len(hist)//180)))
            plt.xticks(rotation=45)

            # Add grid
            ax.grid(True, alpha=0.3)
            ax.set_axisbelow(True)

            # Add current price annotation
            current_price = hist['Close'].iloc[-1]
            start_price = hist['Close'].iloc[0]
            change_pct = ((current_price - start_price) / start_price) * 100
            change_color = '#4CAF50' if change_pct >= 0 else '#F44336'
            change_sign = '+' if change_pct >= 0 else ''

            ax.annotate(
                f"${current_price:.2f} ({change_sign}{change_pct:.1f}%)",
                xy=(hist.index[-1], current_price),
                xytext=(10, 0),
                textcoords='offset points',
                fontsize=11,
                fontweight='bold',
                color=change_color,
                va='center'
            )

            # Add volume subplot
            ax2 = ax.twinx()
            ax2.bar(hist.index, hist['Volume'], alpha=0.3, color='gray', width=0.8)
            ax2.set_ylabel('Volume', fontsize=10, color='gray')
            ax2.tick_params(axis='y', labelcolor='gray')
            ax2.set_ylim(0, hist['Volume'].max() * 4)  # Scale down volume bars

            plt.tight_layout()

            # Save to temp file
            temp_dir = tempfile.gettempdir()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(temp_dir, f"bigclaw_chart_{ticker}_{timestamp}.png")

            plt.savefig(filepath, dpi=150, bbox_inches='tight',
                       facecolor='white', edgecolor='none')
            plt.close(fig)

            logger.info(f"Chart saved to: {filepath}")

            # Return special format that bot.py will recognize as an image
            # Use ||| as delimiter to avoid issues with : in Windows paths
            return f"__IMAGE__|||{filepath}|||{ticker} {self._period_label(period)} Chart"

        except Exception as e:
            logger.error(f"Error generating chart for {ticker}: {e}")
            return f"Error generating chart for {ticker}: {str(e)}"

    def _period_label(self, period: str) -> str:
        """Convert period code to human-readable label."""
        labels = {
            "1mo": "1 Month",
            "3mo": "3 Months",
            "6mo": "6 Months",
            "1y": "1 Year",
            "2y": "2 Years",
            "5y": "5 Years"
        }
        return labels.get(period, period)

    def _plot_candlestick(self, ax, hist):
        """Plot a candlestick chart."""
        # Simplified candlestick using bar charts
        up = hist[hist['Close'] >= hist['Open']]
        down = hist[hist['Close'] < hist['Open']]

        # Plot up days (green)
        ax.bar(up.index, up['Close'] - up['Open'], bottom=up['Open'],
               color='#4CAF50', width=0.8)
        ax.bar(up.index, up['High'] - up['Close'], bottom=up['Close'],
               color='#4CAF50', width=0.1)
        ax.bar(up.index, up['Low'] - up['Open'], bottom=up['Open'],
               color='#4CAF50', width=0.1)

        # Plot down days (red)
        ax.bar(down.index, down['Close'] - down['Open'], bottom=down['Open'],
               color='#F44336', width=0.8)
        ax.bar(down.index, down['High'] - down['Open'], bottom=down['Open'],
               color='#F44336', width=0.1)
        ax.bar(down.index, down['Low'] - down['Close'], bottom=down['Close'],
               color='#F44336', width=0.1)


class CompareStocksTool(BaseTool):
    """Generate comparison chart for multiple stocks."""

    @property
    def name(self) -> str:
        return "compare_stocks_chart"

    @property
    def description(self) -> str:
        return """Generate a comparison chart showing multiple stocks on the same graph.

Use this when users want to:
- Compare two or more stocks ("Compare AAPL vs MSFT")
- See relative performance ("How has NVDA done vs AMD?")
- Visualize multiple tickers together

Shows normalized percentage change so stocks of different prices can be compared."""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "tickers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of ticker symbols to compare (2-5 tickers)"
                },
                "period": {
                    "type": "string",
                    "enum": ["1mo", "3mo", "6mo", "1y", "2y"],
                    "description": "Time period for comparison. Default is '6mo'"
                }
            },
            "required": ["tickers"]
        }

    def execute(self, tickers: list, period: str = "6mo") -> str:
        try:
            import yfinance as yf
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates
        except ImportError as e:
            return f"Error: Missing package. Run: pip install yfinance matplotlib. Details: {e}"

        # Validate tickers
        if len(tickers) < 2:
            return "Please provide at least 2 tickers to compare."
        if len(tickers) > 5:
            tickers = tickers[:5]  # Limit to 5

        tickers = [t.upper().strip() for t in tickers]
        logger.info(f"Generating comparison chart for {tickers}, period: {period}")

        try:
            fig, ax = plt.subplots(figsize=(12, 6))

            colors = ['#2196F3', '#F44336', '#4CAF50', '#FF9800', '#9C27B0']
            results = []

            for i, ticker in enumerate(tickers):
                stock = yf.Ticker(ticker)
                hist = stock.history(period=period)

                if hist.empty:
                    logger.warning(f"No data for {ticker}")
                    continue

                # Normalize to percentage change from start
                normalized = ((hist['Close'] / hist['Close'].iloc[0]) - 1) * 100

                ax.plot(hist.index, normalized, linewidth=2,
                       color=colors[i % len(colors)], label=ticker)

                # Track results for summary
                final_change = normalized.iloc[-1]
                results.append(f"{ticker}: {'+' if final_change >= 0 else ''}{final_change:.1f}%")

            if not results:
                return "Could not fetch data for any of the specified tickers."

            # Formatting
            period_label = {"1mo": "1 Month", "3mo": "3 Months", "6mo": "6 Months",
                           "1y": "1 Year", "2y": "2 Years"}.get(period, period)

            ax.set_title(f"Stock Comparison - {period_label}",
                        fontsize=14, fontweight='bold', pad=20)
            ax.set_xlabel("Date", fontsize=10)
            ax.set_ylabel("Change (%)", fontsize=10)

            # Add horizontal line at 0%
            ax.axhline(y=0, color='gray', linestyle='--', alpha=0.5)

            # Format x-axis
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
            plt.xticks(rotation=45)

            ax.grid(True, alpha=0.3)
            ax.legend(loc='upper left', fontsize=10)

            plt.tight_layout()

            # Save to temp file
            temp_dir = tempfile.gettempdir()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            ticker_str = "_".join(tickers[:3])
            filepath = os.path.join(temp_dir, f"bigclaw_compare_{ticker_str}_{timestamp}.png")

            plt.savefig(filepath, dpi=150, bbox_inches='tight',
                       facecolor='white', edgecolor='none')
            plt.close(fig)

            logger.info(f"Comparison chart saved to: {filepath}")

            summary = ", ".join(results)
            # Use ||| as delimiter to avoid issues with : in Windows paths
            return f"__IMAGE__|||{filepath}|||Comparison of {', '.join(tickers)} ({period_label}) - {summary}"

        except Exception as e:
            logger.error(f"Error generating comparison chart: {e}")
            return f"Error generating comparison chart: {str(e)}"
