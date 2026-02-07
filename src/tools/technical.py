"""Technical analysis chart tools for BigClaw AI."""

import logging
import os
import tempfile
from datetime import datetime
from typing import Optional
import numpy as np

# Use non-interactive backend for matplotlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from .base import BaseTool

logger = logging.getLogger(__name__)


class MACDChartTool(BaseTool):
    """Generate MACD (Moving Average Convergence Divergence) chart."""

    @property
    def name(self) -> str:
        return "generate_macd_chart"

    @property
    def description(self) -> str:
        return """Generate a MACD chart for technical analysis.

MACD shows the relationship between two moving averages and helps identify:
- Trend direction and momentum
- Buy/sell signals (when MACD crosses signal line)
- Divergences from price

Use when users ask about momentum, trend strength, or MACD specifically."""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol (e.g., 'AAPL')"
                },
                "period": {
                    "type": "string",
                    "enum": ["3mo", "6mo", "1y", "2y"],
                    "description": "Time period for the chart. Default is '6mo'"
                }
            },
            "required": ["ticker"]
        }

    def execute(self, ticker: str, period: str = "6mo") -> str:
        try:
            import yfinance as yf
        except ImportError:
            return "Error: yfinance not installed."

        ticker = ticker.upper().strip()
        logger.info(f"Generating MACD chart for {ticker}")

        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period=period)

            if hist.empty or len(hist) < 26:
                return f"Not enough data for {ticker} to calculate MACD."

            # Calculate MACD
            exp1 = hist['Close'].ewm(span=12, adjust=False).mean()
            exp2 = hist['Close'].ewm(span=26, adjust=False).mean()
            macd = exp1 - exp2
            signal = macd.ewm(span=9, adjust=False).mean()
            histogram = macd - signal

            # Create figure with two subplots
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8),
                                           gridspec_kw={'height_ratios': [2, 1]})

            # Price chart
            ax1.plot(hist.index, hist['Close'], linewidth=1.5, color='#2196F3', label='Price')
            ax1.set_title(f"{ticker} - MACD Analysis ({period})",
                         fontsize=14, fontweight='bold')
            ax1.set_ylabel("Price ($)")
            ax1.grid(True, alpha=0.3)
            ax1.legend(loc='upper left')

            # MACD chart
            ax2.plot(hist.index, macd, linewidth=1.5, color='#2196F3', label='MACD')
            ax2.plot(hist.index, signal, linewidth=1.5, color='#FF9800', label='Signal')

            # Histogram
            colors = ['#4CAF50' if v >= 0 else '#F44336' for v in histogram]
            ax2.bar(hist.index, histogram, color=colors, alpha=0.6, width=0.8)

            ax2.axhline(y=0, color='gray', linestyle='--', alpha=0.5)
            ax2.set_ylabel("MACD")
            ax2.set_xlabel("Date")
            ax2.legend(loc='upper left')
            ax2.grid(True, alpha=0.3)

            # Format dates
            for ax in [ax1, ax2]:
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))

            plt.tight_layout()

            # Save
            temp_dir = tempfile.gettempdir()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(temp_dir, f"bigclaw_macd_{ticker}_{timestamp}.png")
            plt.savefig(filepath, dpi=150, bbox_inches='tight', facecolor='white')
            plt.close(fig)

            # Current signals
            current_macd = macd.iloc[-1]
            current_signal = signal.iloc[-1]
            signal_type = "BULLISH" if current_macd > current_signal else "BEARISH"

            return f"__IMAGE__|||{filepath}|||{ticker} MACD Chart - Currently {signal_type}"

        except Exception as e:
            logger.error(f"Error generating MACD chart: {e}")
            return f"Error generating MACD chart: {str(e)}"


class RSIChartTool(BaseTool):
    """Generate RSI (Relative Strength Index) chart."""

    @property
    def name(self) -> str:
        return "generate_rsi_chart"

    @property
    def description(self) -> str:
        return """Generate an RSI chart for technical analysis.

RSI measures momentum and identifies:
- Overbought conditions (RSI > 70)
- Oversold conditions (RSI < 30)
- Potential reversal points

Use when users ask about whether a stock is overbought/oversold."""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol"
                },
                "period": {
                    "type": "string",
                    "enum": ["3mo", "6mo", "1y"],
                    "description": "Time period. Default is '6mo'"
                }
            },
            "required": ["ticker"]
        }

    def execute(self, ticker: str, period: str = "6mo") -> str:
        try:
            import yfinance as yf
        except ImportError:
            return "Error: yfinance not installed."

        ticker = ticker.upper().strip()
        logger.info(f"Generating RSI chart for {ticker}")

        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period=period)

            if hist.empty or len(hist) < 14:
                return f"Not enough data for {ticker} to calculate RSI."

            # Calculate RSI
            delta = hist['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))

            # Create figure
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8),
                                           gridspec_kw={'height_ratios': [2, 1]})

            # Price chart
            ax1.plot(hist.index, hist['Close'], linewidth=1.5, color='#2196F3')
            ax1.set_title(f"{ticker} - RSI Analysis ({period})",
                         fontsize=14, fontweight='bold')
            ax1.set_ylabel("Price ($)")
            ax1.grid(True, alpha=0.3)

            # RSI chart
            ax2.plot(hist.index, rsi, linewidth=1.5, color='#9C27B0')
            ax2.axhline(y=70, color='#F44336', linestyle='--', alpha=0.7, label='Overbought (70)')
            ax2.axhline(y=30, color='#4CAF50', linestyle='--', alpha=0.7, label='Oversold (30)')
            ax2.axhline(y=50, color='gray', linestyle='--', alpha=0.3)

            # Fill overbought/oversold zones
            ax2.fill_between(hist.index, 70, 100, alpha=0.1, color='#F44336')
            ax2.fill_between(hist.index, 0, 30, alpha=0.1, color='#4CAF50')

            ax2.set_ylabel("RSI")
            ax2.set_xlabel("Date")
            ax2.set_ylim(0, 100)
            ax2.legend(loc='upper left')
            ax2.grid(True, alpha=0.3)

            for ax in [ax1, ax2]:
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))

            plt.tight_layout()

            # Save
            temp_dir = tempfile.gettempdir()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(temp_dir, f"bigclaw_rsi_{ticker}_{timestamp}.png")
            plt.savefig(filepath, dpi=150, bbox_inches='tight', facecolor='white')
            plt.close(fig)

            # Current RSI
            current_rsi = rsi.iloc[-1]
            if current_rsi > 70:
                status = "OVERBOUGHT"
            elif current_rsi < 30:
                status = "OVERSOLD"
            else:
                status = "NEUTRAL"

            return f"__IMAGE__|||{filepath}|||{ticker} RSI Chart - RSI: {current_rsi:.1f} ({status})"

        except Exception as e:
            logger.error(f"Error generating RSI chart: {e}")
            return f"Error generating RSI chart: {str(e)}"


class BollingerBandsChartTool(BaseTool):
    """Generate Bollinger Bands chart."""

    @property
    def name(self) -> str:
        return "generate_bollinger_chart"

    @property
    def description(self) -> str:
        return """Generate a Bollinger Bands chart for technical analysis.

Bollinger Bands show:
- Volatility (band width)
- Potential support/resistance (upper/lower bands)
- Mean reversion opportunities
- Squeeze patterns (low volatility before breakout)

Use when users ask about volatility, support/resistance, or Bollinger Bands."""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol"
                },
                "period": {
                    "type": "string",
                    "enum": ["3mo", "6mo", "1y"],
                    "description": "Time period. Default is '6mo'"
                }
            },
            "required": ["ticker"]
        }

    def execute(self, ticker: str, period: str = "6mo") -> str:
        try:
            import yfinance as yf
        except ImportError:
            return "Error: yfinance not installed."

        ticker = ticker.upper().strip()
        logger.info(f"Generating Bollinger Bands chart for {ticker}")

        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period=period)

            if hist.empty or len(hist) < 20:
                return f"Not enough data for {ticker}."

            # Calculate Bollinger Bands
            sma = hist['Close'].rolling(window=20).mean()
            std = hist['Close'].rolling(window=20).std()
            upper_band = sma + (std * 2)
            lower_band = sma - (std * 2)

            # Create figure
            fig, ax = plt.subplots(figsize=(12, 6))

            # Price and bands
            ax.plot(hist.index, hist['Close'], linewidth=1.5, color='#2196F3', label='Price')
            ax.plot(hist.index, sma, linewidth=1, color='#FF9800', label='SMA(20)')
            ax.plot(hist.index, upper_band, linewidth=1, color='#F44336', linestyle='--', label='Upper Band')
            ax.plot(hist.index, lower_band, linewidth=1, color='#4CAF50', linestyle='--', label='Lower Band')

            # Fill between bands
            ax.fill_between(hist.index, lower_band, upper_band, alpha=0.1, color='#9C27B0')

            ax.set_title(f"{ticker} - Bollinger Bands ({period})",
                        fontsize=14, fontweight='bold')
            ax.set_xlabel("Date")
            ax.set_ylabel("Price ($)")
            ax.legend(loc='upper left')
            ax.grid(True, alpha=0.3)
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))

            plt.tight_layout()

            # Save
            temp_dir = tempfile.gettempdir()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(temp_dir, f"bigclaw_bollinger_{ticker}_{timestamp}.png")
            plt.savefig(filepath, dpi=150, bbox_inches='tight', facecolor='white')
            plt.close(fig)

            # Current position
            current_price = hist['Close'].iloc[-1]
            current_upper = upper_band.iloc[-1]
            current_lower = lower_band.iloc[-1]

            if current_price > current_upper:
                position = "ABOVE upper band"
            elif current_price < current_lower:
                position = "BELOW lower band"
            else:
                pct_position = (current_price - current_lower) / (current_upper - current_lower) * 100
                position = f"{pct_position:.0f}% within bands"

            return f"__IMAGE__|||{filepath}|||{ticker} Bollinger Bands - {position}"

        except Exception as e:
            logger.error(f"Error generating Bollinger chart: {e}")
            return f"Error generating Bollinger chart: {str(e)}"


class MonteCarloChartTool(BaseTool):
    """Generate Monte Carlo simulation for price projection."""

    @property
    def name(self) -> str:
        return "generate_monte_carlo_chart"

    @property
    def description(self) -> str:
        return """Generate a Monte Carlo simulation chart for price projection.

Monte Carlo simulation:
- Projects possible future price paths
- Shows probability distribution of outcomes
- Helps assess risk and potential returns
- Based on historical volatility and returns

Use when users ask about price predictions, risk analysis, or future scenarios."""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol"
                },
                "days_forward": {
                    "type": "integer",
                    "description": "Number of trading days to project (default 60, ~3 months)"
                },
                "simulations": {
                    "type": "integer",
                    "description": "Number of simulations to run (default 500)"
                }
            },
            "required": ["ticker"]
        }

    def execute(self, ticker: str, days_forward: int = 60, simulations: int = 500) -> str:
        try:
            import yfinance as yf
        except ImportError:
            return "Error: yfinance not installed."

        ticker = ticker.upper().strip()
        days_forward = min(max(20, days_forward), 252)  # Between 20 days and 1 year
        simulations = min(max(100, simulations), 1000)  # Between 100 and 1000

        logger.info(f"Generating Monte Carlo for {ticker}: {days_forward} days, {simulations} sims")

        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1y")

            if hist.empty or len(hist) < 100:
                return f"Not enough historical data for {ticker}."

            # Calculate daily returns
            returns = hist['Close'].pct_change().dropna()
            mu = returns.mean()
            sigma = returns.std()

            # Current price
            current_price = hist['Close'].iloc[-1]

            # Run simulations
            np.random.seed(42)  # For reproducibility
            simulation_results = np.zeros((simulations, days_forward))

            for i in range(simulations):
                prices = [current_price]
                for _ in range(days_forward - 1):
                    # Geometric Brownian Motion
                    shock = np.random.normal(mu, sigma)
                    prices.append(prices[-1] * (1 + shock))
                simulation_results[i] = prices

            # Calculate percentiles
            percentile_5 = np.percentile(simulation_results, 5, axis=0)
            percentile_25 = np.percentile(simulation_results, 25, axis=0)
            percentile_50 = np.percentile(simulation_results, 50, axis=0)
            percentile_75 = np.percentile(simulation_results, 75, axis=0)
            percentile_95 = np.percentile(simulation_results, 95, axis=0)

            # Create figure
            fig, ax = plt.subplots(figsize=(12, 7))

            days = range(days_forward)

            # Plot simulation paths (sample)
            for i in range(min(100, simulations)):
                ax.plot(days, simulation_results[i], alpha=0.05, color='blue', linewidth=0.5)

            # Plot percentile bands
            ax.fill_between(days, percentile_5, percentile_95, alpha=0.2, color='#2196F3', label='90% CI')
            ax.fill_between(days, percentile_25, percentile_75, alpha=0.3, color='#2196F3', label='50% CI')
            ax.plot(days, percentile_50, color='#F44336', linewidth=2, label='Median')
            ax.axhline(y=current_price, color='#4CAF50', linestyle='--', label=f'Current: ${current_price:.2f}')

            ax.set_title(f"{ticker} - Monte Carlo Simulation ({days_forward} Trading Days)\n"
                        f"{simulations} simulations based on 1-year historical volatility",
                        fontsize=12, fontweight='bold')
            ax.set_xlabel("Trading Days Forward")
            ax.set_ylabel("Price ($)")
            ax.legend(loc='upper left')
            ax.grid(True, alpha=0.3)

            # Add annotations for final prices
            final_5 = percentile_5[-1]
            final_50 = percentile_50[-1]
            final_95 = percentile_95[-1]

            ax.annotate(f'95th: ${final_95:.2f}', xy=(days_forward-1, final_95),
                       xytext=(5, 0), textcoords='offset points', fontsize=9)
            ax.annotate(f'Median: ${final_50:.2f}', xy=(days_forward-1, final_50),
                       xytext=(5, 0), textcoords='offset points', fontsize=9)
            ax.annotate(f'5th: ${final_5:.2f}', xy=(days_forward-1, final_5),
                       xytext=(5, 0), textcoords='offset points', fontsize=9)

            plt.tight_layout()

            # Save
            temp_dir = tempfile.gettempdir()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(temp_dir, f"bigclaw_montecarlo_{ticker}_{timestamp}.png")
            plt.savefig(filepath, dpi=150, bbox_inches='tight', facecolor='white')
            plt.close(fig)

            # Summary stats
            median_return = (final_50 - current_price) / current_price * 100
            summary = f"Median: ${final_50:.2f} ({median_return:+.1f}%), Range: ${final_5:.2f}-${final_95:.2f}"

            return f"__IMAGE__|||{filepath}|||{ticker} Monte Carlo {days_forward}-Day Projection - {summary}"

        except Exception as e:
            logger.error(f"Error generating Monte Carlo: {e}")
            return f"Error generating Monte Carlo simulation: {str(e)}"


class MovingAveragesChartTool(BaseTool):
    """Generate Moving Averages chart with SMA and EMA."""

    @property
    def name(self) -> str:
        return "generate_moving_averages_chart"

    @property
    def description(self) -> str:
        return """Generate a chart with multiple moving averages.

Shows SMA (Simple) and EMA (Exponential) moving averages:
- 20-day (short-term trend)
- 50-day (medium-term trend)
- 200-day (long-term trend)

Golden Cross: 50 crosses above 200 (bullish)
Death Cross: 50 crosses below 200 (bearish)

Use for trend analysis and identifying support/resistance levels."""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol"
                },
                "period": {
                    "type": "string",
                    "enum": ["6mo", "1y", "2y"],
                    "description": "Time period. Default is '1y'"
                }
            },
            "required": ["ticker"]
        }

    def execute(self, ticker: str, period: str = "1y") -> str:
        try:
            import yfinance as yf
        except ImportError:
            return "Error: yfinance not installed."

        ticker = ticker.upper().strip()
        logger.info(f"Generating Moving Averages chart for {ticker}")

        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period=period)

            if hist.empty or len(hist) < 200:
                return f"Not enough data for {ticker} (need at least 200 days)."

            # Calculate moving averages
            sma_20 = hist['Close'].rolling(window=20).mean()
            sma_50 = hist['Close'].rolling(window=50).mean()
            sma_200 = hist['Close'].rolling(window=200).mean()
            ema_20 = hist['Close'].ewm(span=20, adjust=False).mean()

            # Create figure
            fig, ax = plt.subplots(figsize=(12, 6))

            ax.plot(hist.index, hist['Close'], linewidth=1.5, color='#2196F3', label='Price', alpha=0.8)
            ax.plot(hist.index, sma_20, linewidth=1, color='#4CAF50', label='SMA 20', alpha=0.8)
            ax.plot(hist.index, sma_50, linewidth=1.5, color='#FF9800', label='SMA 50')
            ax.plot(hist.index, sma_200, linewidth=2, color='#F44336', label='SMA 200')
            ax.plot(hist.index, ema_20, linewidth=1, color='#9C27B0', label='EMA 20', linestyle='--', alpha=0.7)

            ax.set_title(f"{ticker} - Moving Averages ({period})",
                        fontsize=14, fontweight='bold')
            ax.set_xlabel("Date")
            ax.set_ylabel("Price ($)")
            ax.legend(loc='upper left')
            ax.grid(True, alpha=0.3)
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))

            plt.tight_layout()

            # Save
            temp_dir = tempfile.gettempdir()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(temp_dir, f"bigclaw_ma_{ticker}_{timestamp}.png")
            plt.savefig(filepath, dpi=150, bbox_inches='tight', facecolor='white')
            plt.close(fig)

            # Trend analysis
            current_price = hist['Close'].iloc[-1]
            current_50 = sma_50.iloc[-1]
            current_200 = sma_200.iloc[-1]

            if current_50 > current_200:
                trend = "BULLISH (50 > 200)"
            else:
                trend = "BEARISH (50 < 200)"

            return f"__IMAGE__|||{filepath}|||{ticker} Moving Averages - {trend}"

        except Exception as e:
            logger.error(f"Error generating MA chart: {e}")
            return f"Error generating Moving Averages chart: {str(e)}"
