"""Portfolio management tools for BigClaw AI - Paper trading."""

import logging
from typing import Optional

from .base import BaseTool

logger = logging.getLogger(__name__)


class CreatePortfolioTool(BaseTool):
    """Create a new paper trading portfolio."""

    @property
    def name(self) -> str:
        return "create_portfolio"

    @property
    def description(self) -> str:
        return """Create a new paper trading portfolio with a specific investment style.

Each portfolio:
- Starts with a cash balance (default $100,000)
- Follows a specific investment style (Buffett, Lynch, Dalio, etc.)
- Tracks all trades and performance

Use when users want to:
- "Create a Buffett-style portfolio"
- "Start a new portfolio with $50,000"
- "Set up paper trading for growth stocks"
"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Unique name for the portfolio (e.g., 'Buffett Value', 'Growth 2024')"
                },
                "investment_style": {
                    "type": "string",
                    "description": "Investment style to follow (e.g., 'Warren Buffett', 'Peter Lynch', 'Cathie Wood', 'Ray Dalio', 'Custom')"
                },
                "starting_cash": {
                    "type": "number",
                    "description": "Starting cash balance in USD (default 100000)"
                }
            },
            "required": ["name", "investment_style"]
        }

    def execute(self, name: str, investment_style: str, starting_cash: float = 100000) -> str:
        from portfolio import create_portfolio, get_portfolio

        # Check if portfolio already exists
        existing = get_portfolio(name)
        if existing:
            return f"Portfolio '{name}' already exists. Choose a different name."

        try:
            portfolio = create_portfolio(
                name=name,
                investment_style=investment_style,
                starting_cash=starting_cash
            )

            return f"""**Portfolio Created Successfully!**

**Name:** {portfolio.name}
**Style:** {portfolio.investment_style}
**Starting Cash:** ${portfolio.starting_cash:,.2f}

Ready for trading! Use the buy_stock and sell_stock tools to execute trades.
I'll apply the {investment_style} investment philosophy when analyzing opportunities."""

        except Exception as e:
            logger.error(f"Create portfolio error: {e}")
            return f"Error creating portfolio: {str(e)}"


class ListPortfoliosTool(BaseTool):
    """List all portfolios."""

    @property
    def name(self) -> str:
        return "list_portfolios"

    @property
    def description(self) -> str:
        return """List all paper trading portfolios.

Shows all portfolios with their investment styles and current cash balances.
Use to see what portfolios exist before trading.
"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {},
            "required": []
        }

    def execute(self) -> str:
        from portfolio import list_portfolios

        portfolios = list_portfolios()

        if not portfolios:
            return "No portfolios found. Create one with the create_portfolio tool."

        output = "**Your Portfolios:**\n\n"

        for p in portfolios:
            status = "✅ Active" if p["is_active"] else "⏸️ Paused"
            output += f"**{p['name']}** ({p['investment_style']})\n"
            output += f"   Cash: ${p['current_cash']:,.2f} | Started: ${p['starting_cash']:,.2f}\n"
            output += f"   Created: {p['created_at'][:10]} | {status}\n\n"

        return output


class ViewPortfolioTool(BaseTool):
    """View portfolio details and current holdings."""

    @property
    def name(self) -> str:
        return "view_portfolio"

    @property
    def description(self) -> str:
        return """View detailed portfolio information including holdings and performance.

Shows:
- Current cash balance
- All stock positions with gains/losses
- Total portfolio value and return

Use when users ask:
- "Show me my portfolio"
- "How is my Buffett portfolio doing?"
- "What stocks do I own?"
"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "portfolio_name": {
                    "type": "string",
                    "description": "Name of the portfolio to view"
                }
            },
            "required": ["portfolio_name"]
        }

    def execute(self, portfolio_name: str) -> str:
        from portfolio import get_portfolio
        import yfinance as yf

        portfolio = get_portfolio(portfolio_name)
        if not portfolio:
            return f"Portfolio '{portfolio_name}' not found. Use list_portfolios to see available portfolios."

        holdings = portfolio.get_holdings()

        # Get current prices for all holdings
        current_prices = {}
        if holdings:
            tickers = [h["ticker"] for h in holdings]
            try:
                data = yf.download(tickers, period="1d", progress=False)
                if len(tickers) == 1:
                    current_prices[tickers[0]] = float(data["Close"].iloc[-1])
                else:
                    for ticker in tickers:
                        try:
                            current_prices[ticker] = float(data["Close"][ticker].iloc[-1])
                        except:
                            pass
            except Exception as e:
                logger.warning(f"Price fetch error: {e}")

        # Calculate portfolio value
        value_data = portfolio.calculate_total_value(current_prices)

        output = f"**📊 Portfolio: {portfolio.name}**\n"
        output += f"**Style:** {portfolio.investment_style}\n\n"

        output += f"**💰 Summary:**\n"
        output += f"   Cash: ${value_data['cash']:,.2f}\n"
        output += f"   Holdings Value: ${value_data['holdings_value']:,.2f}\n"
        output += f"   **Total Value: ${value_data['total_value']:,.2f}**\n"

        return_emoji = "📈" if value_data['total_return'] >= 0 else "📉"
        output += f"   {return_emoji} Total Return: ${value_data['total_return']:,.2f} ({value_data['total_return_pct']:.2f}%)\n\n"

        if value_data['positions']:
            output += "**📈 Holdings:**\n"
            for pos in value_data['positions']:
                gain_emoji = "🟢" if pos['gain'] >= 0 else "🔴"
                output += f"\n**{pos['ticker']}** - {pos['shares']:.2f} shares\n"
                output += f"   Avg Cost: ${pos['avg_cost']:.2f} | Current: ${pos['current_price']:.2f}\n"
                output += f"   Value: ${pos['value']:,.2f} | {gain_emoji} {pos['gain_pct']:+.2f}%\n"
        else:
            output += "_No holdings yet. Use buy_stock to start investing!_\n"

        return output


class BuyStockTool(BaseTool):
    """Buy stock in a portfolio."""

    @property
    def name(self) -> str:
        return "buy_stock"

    @property
    def description(self) -> str:
        return """Execute a paper trade to buy stock in a portfolio.

Buys shares at the current market price. Requires sufficient cash.
You can specify either:
- shares: exact number of shares to buy
- amount: dollar amount to invest (will calculate shares automatically)

Always include a rationale explaining why this fits the portfolio's investment style.
"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "portfolio_name": {
                    "type": "string",
                    "description": "Name of the portfolio to trade in"
                },
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol (e.g., 'AAPL')"
                },
                "shares": {
                    "type": "number",
                    "description": "Number of shares to buy (use this OR amount, not both)"
                },
                "amount": {
                    "type": "number",
                    "description": "Dollar amount to invest - shares will be calculated automatically (use this OR shares)"
                },
                "rationale": {
                    "type": "string",
                    "description": "Investment rationale - why this fits the portfolio's style"
                }
            },
            "required": ["portfolio_name", "ticker", "rationale"]
        }

    def execute(self, portfolio_name: str, ticker: str, rationale: str,
                shares: float = None, amount: float = None) -> str:
        from portfolio import get_portfolio
        import yfinance as yf

        ticker = ticker.upper().strip()

        if shares is None and amount is None:
            return "Error: Must specify either 'shares' or 'amount'"

        portfolio = get_portfolio(portfolio_name)
        if not portfolio:
            return f"Portfolio '{portfolio_name}' not found."

        # Get current price
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1d")
            if hist.empty:
                return f"Could not get price for {ticker}. Invalid ticker?"
            current_price = float(hist["Close"].iloc[-1])
        except Exception as e:
            return f"Error getting price for {ticker}: {str(e)}"

        # Calculate shares if amount was provided
        if amount is not None:
            shares = amount / current_price
            logger.info(f"Calculated {shares:.2f} shares from ${amount} at ${current_price:.2f}")

        # Execute buy
        result = portfolio.buy(ticker, shares, current_price, rationale)

        if result["success"]:
            return f"""**✅ BUY Order Executed**

**Portfolio:** {portfolio_name}
**Stock:** {ticker}
**Shares:** {shares:.2f}
**Price:** ${current_price:.2f}
**Total Cost:** ${result['total_cost']:,.2f}
**Remaining Cash:** ${result['remaining_cash']:,.2f}

**Rationale:** {rationale}"""
        else:
            return f"**❌ Buy Failed:** {result['error']}"


class SellStockTool(BaseTool):
    """Sell stock from a portfolio."""

    @property
    def name(self) -> str:
        return "sell_stock"

    @property
    def description(self) -> str:
        return """Execute a paper trade to sell stock from a portfolio.

Sells shares at the current market price. Must have sufficient shares.
Always include a rationale explaining why selling fits the strategy.

Use when:
- Taking profits or cutting losses
- Rebalancing the portfolio
- User requests a sale
- Autonomous trading decisions
"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "portfolio_name": {
                    "type": "string",
                    "description": "Name of the portfolio to trade in"
                },
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol (e.g., 'AAPL')"
                },
                "shares": {
                    "type": "number",
                    "description": "Number of shares to sell (use 'all' logic by getting holding first)"
                },
                "rationale": {
                    "type": "string",
                    "description": "Rationale for selling - why this fits the strategy"
                }
            },
            "required": ["portfolio_name", "ticker", "shares", "rationale"]
        }

    def execute(self, portfolio_name: str, ticker: str, shares: float, rationale: str) -> str:
        from portfolio import get_portfolio
        import yfinance as yf

        ticker = ticker.upper().strip()

        portfolio = get_portfolio(portfolio_name)
        if not portfolio:
            return f"Portfolio '{portfolio_name}' not found."

        # Check holding
        holding = portfolio.get_holding(ticker)
        if not holding:
            return f"No position in {ticker} to sell."

        # Get current price
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1d")
            if hist.empty:
                return f"Could not get price for {ticker}."
            current_price = float(hist["Close"].iloc[-1])
        except Exception as e:
            return f"Error getting price for {ticker}: {str(e)}"

        # Execute sell
        result = portfolio.sell(ticker, shares, current_price, rationale)

        if result["success"]:
            profit_emoji = "📈" if result['profit'] >= 0 else "📉"
            return f"""**✅ SELL Order Executed**

**Portfolio:** {portfolio_name}
**Stock:** {ticker}
**Shares:** {shares}
**Price:** ${current_price:.2f}
**Total Proceeds:** ${result['total_value']:,.2f}
{profit_emoji} **Profit/Loss:** ${result['profit']:,.2f}
**Cash Balance:** ${result['remaining_cash']:,.2f}

**Rationale:** {rationale}"""
        else:
            return f"**❌ Sell Failed:** {result['error']}"


class GetTransactionsTool(BaseTool):
    """Get portfolio transaction history."""

    @property
    def name(self) -> str:
        return "get_transactions"

    @property
    def description(self) -> str:
        return """Get recent transaction history for a portfolio.

Shows all buys and sells with dates, prices, and rationales.
Useful for reviewing trading decisions and patterns.
"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "portfolio_name": {
                    "type": "string",
                    "description": "Name of the portfolio"
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of transactions to show (default 20)"
                }
            },
            "required": ["portfolio_name"]
        }

    def execute(self, portfolio_name: str, limit: int = 20) -> str:
        from portfolio import get_portfolio

        portfolio = get_portfolio(portfolio_name)
        if not portfolio:
            return f"Portfolio '{portfolio_name}' not found."

        transactions = portfolio.get_transactions(limit)

        if not transactions:
            return f"No transactions yet in '{portfolio_name}'."

        output = f"**📜 Transaction History: {portfolio_name}**\n\n"

        for t in transactions:
            action_emoji = "🟢 BUY" if t["action"] == "BUY" else "🔴 SELL"
            output += f"**{action_emoji}** {t['ticker']} - {t['shares']} @ ${t['price']:.2f}\n"
            output += f"   Total: ${t['total_value']:,.2f} | {t['executed_at'][:16]}\n"
            if t['rationale']:
                output += f"   _{t['rationale'][:100]}{'...' if len(t['rationale']) > 100 else ''}_\n"
            output += "\n"

        return output


class DeletePortfolioTool(BaseTool):
    """Delete a portfolio."""

    @property
    def name(self) -> str:
        return "delete_portfolio"

    @property
    def description(self) -> str:
        return """Delete a portfolio and all its data.

WARNING: This permanently deletes:
- All holdings
- All transaction history
- All performance data

Use with caution. Confirm with user before deleting.
"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "portfolio_name": {
                    "type": "string",
                    "description": "Name of the portfolio to delete"
                }
            },
            "required": ["portfolio_name"]
        }

    def execute(self, portfolio_name: str) -> str:
        from portfolio import delete_portfolio

        success = delete_portfolio(portfolio_name)

        if success:
            return f"**🗑️ Portfolio '{portfolio_name}' deleted.**\nAll holdings and transaction history have been removed."
        else:
            return f"Portfolio '{portfolio_name}' not found."


class SetReportChannelTool(BaseTool):
    """Set the Slack channel for daily reports."""

    @property
    def name(self) -> str:
        return "set_report_channel"

    @property
    def description(self) -> str:
        return """Set the Slack channel where daily portfolio reports will be sent.

Once set, the portfolio will send:
- Daily performance summaries
- Trade notifications from autonomous trading
- End-of-day reports

IMPORTANT: The current channel ID is provided at the start of each message in brackets like [Current channel: C07XXXXXX].
When the user says "this channel" or "here", use that channel ID from the message context.
"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "portfolio_name": {
                    "type": "string",
                    "description": "Name of the portfolio"
                },
                "channel_id": {
                    "type": "string",
                    "description": "Slack channel ID for reports (usually starts with C)"
                }
            },
            "required": ["portfolio_name", "channel_id"]
        }

    def execute(self, portfolio_name: str, channel_id: str) -> str:
        from portfolio import get_portfolio, get_db_connection

        portfolio = get_portfolio(portfolio_name)
        if not portfolio:
            return f"Portfolio '{portfolio_name}' not found."

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE portfolios SET report_channel = ? WHERE name = ?",
            (channel_id, portfolio_name)
        )
        conn.commit()
        conn.close()

        return f"""**✅ Report channel set for {portfolio_name}**

Daily reports will be sent to this channel including:
- Portfolio performance summary
- Today's trades (if any)
- Position updates

Reports are sent after market close (4:30 PM ET)."""


class ActivateAutonomousTradingTool(BaseTool):
    """Enable or disable autonomous trading for a portfolio."""

    @property
    def name(self) -> str:
        return "set_autonomous_trading"

    @property
    def description(self) -> str:
        return """Enable or disable autonomous trading for a portfolio.

When enabled:
- Daily market analysis before market open (9 AM ET)
- Automatic trade execution based on investment style
- Daily reports after market close

The AI will make trading decisions following the portfolio's investment style.
"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "portfolio_name": {
                    "type": "string",
                    "description": "Name of the portfolio"
                },
                "active": {
                    "type": "boolean",
                    "description": "True to enable autonomous trading, False to disable"
                }
            },
            "required": ["portfolio_name", "active"]
        }

    def execute(self, portfolio_name: str, active: bool) -> str:
        from portfolio import get_portfolio, get_db_connection

        portfolio = get_portfolio(portfolio_name)
        if not portfolio:
            return f"Portfolio '{portfolio_name}' not found."

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE portfolios SET is_active = ? WHERE name = ?",
            (1 if active else 0, portfolio_name)
        )
        conn.commit()
        conn.close()

        if active:
            return f"""**✅ Autonomous trading ENABLED for {portfolio_name}**

The AI will now:
- Analyze markets daily at 9 AM ET (weekdays)
- Make trades following the {portfolio.investment_style} style
- Send reports at 4:30 PM ET

Make sure a report channel is set to receive notifications."""
        else:
            return f"""**⏸️ Autonomous trading DISABLED for {portfolio_name}**

The portfolio is now in manual mode. You can still use buy_stock and sell_stock to trade manually."""


class RunAnalysisNowTool(BaseTool):
    """Manually trigger market analysis and trading."""

    @property
    def name(self) -> str:
        return "run_analysis_now"

    @property
    def description(self) -> str:
        return """Manually trigger market analysis and autonomous trading for a portfolio.

Use this to:
- Test autonomous trading without waiting for scheduled time
- Run analysis on-demand when market conditions change
- Kick off trading for a newly created portfolio
"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "portfolio_name": {
                    "type": "string",
                    "description": "Name of the portfolio to analyze"
                }
            },
            "required": ["portfolio_name"]
        }

    def execute(self, portfolio_name: str) -> str:
        from scheduler import get_scheduler

        scheduler = get_scheduler()
        if not scheduler:
            return "Scheduler not initialized. The bot may need to be restarted."

        # Run analysis and return the actual result
        result = scheduler.run_now(portfolio_name)
        return f"**🔄 Analysis Complete for {portfolio_name}**\n\n{result}"


class ComparePortfoliosTool(BaseTool):
    """Generate a performance comparison chart for multiple portfolios."""

    @property
    def name(self) -> str:
        return "compare_portfolios"

    @property
    def description(self) -> str:
        return """Generate a chart comparing performance of multiple portfolios over time.

Creates a line chart showing:
- Cumulative returns for each portfolio
- Performance comparison between investment styles
- Visual representation of which strategy is winning

Use when users want to:
- "Compare my Buffett and Cathie Wood portfolios"
- "Which investment style is performing better?"
- "Chart portfolio performance against each other"
- "Show me a performance comparison"
"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "portfolio_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of portfolio names to compare (2-5 portfolios)"
                },
                "days": {
                    "type": "integer",
                    "description": "Number of days of history to show (default 30, max 365)"
                }
            },
            "required": ["portfolio_names"]
        }

    def execute(self, portfolio_names: list, days: int = 30) -> str:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        from datetime import datetime, timedelta
        import tempfile
        import os
        from portfolio import get_portfolio, get_db_connection

        if len(portfolio_names) < 2:
            return "Please provide at least 2 portfolios to compare."
        if len(portfolio_names) > 5:
            return "Maximum 5 portfolios for comparison. Please select fewer."

        days = min(max(7, days), 365)

        # Fetch data for each portfolio
        portfolios_data = []
        for name in portfolio_names:
            portfolio = get_portfolio(name)
            if not portfolio:
                return f"Portfolio '{name}' not found."

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT snapshot_date, total_return
                FROM daily_snapshots
                WHERE portfolio_id = ?
                AND snapshot_date >= DATE('now', ?)
                ORDER BY snapshot_date ASC
            """, (portfolio.id, f'-{days} days'))
            snapshots = cursor.fetchall()
            conn.close()

            portfolios_data.append({
                'name': portfolio.name,
                'style': portfolio.investment_style,
                'snapshots': [(row['snapshot_date'], row['total_return']) for row in snapshots],
                'starting_cash': portfolio.starting_cash
            })

        # Check if we have enough data
        has_data = any(len(p['snapshots']) > 0 for p in portfolios_data)
        if not has_data:
            # No historical data yet - show current values instead
            return self._generate_current_comparison(portfolios_data, portfolio_names)

        try:
            # Create the chart
            fig, ax = plt.subplots(figsize=(12, 6))

            colors = ['#2E86AB', '#A23B72', '#F18F01', '#C73E1D', '#3B1F2B']

            for i, pdata in enumerate(portfolios_data):
                if pdata['snapshots']:
                    dates = [datetime.strptime(s[0], '%Y-%m-%d') for s in pdata['snapshots']]
                    returns = [s[1] for s in pdata['snapshots']]
                    label = f"{pdata['name']} ({pdata['style']})"
                    ax.plot(dates, returns, label=label, color=colors[i % len(colors)], linewidth=2)

            ax.axhline(y=0, color='gray', linestyle='--', alpha=0.5)
            ax.set_xlabel('Date', fontsize=11)
            ax.set_ylabel('Total Return (%)', fontsize=11)
            ax.set_title('Portfolio Performance Comparison', fontsize=14, fontweight='bold')
            ax.legend(loc='best', fontsize=9)
            ax.grid(True, alpha=0.3)

            # Format x-axis dates
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
            ax.xaxis.set_major_locator(mdates.AutoDateLocator())
            fig.autofmt_xdate()

            plt.tight_layout()

            # Save to temp file
            filepath = os.path.join(tempfile.gettempdir(), f"portfolio_comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
            plt.savefig(filepath, dpi=150, bbox_inches='tight', facecolor='white', edgecolor='none')
            plt.close(fig)

            logger.info(f"Portfolio comparison chart saved to: {filepath}")

            # Build summary
            summary_parts = []
            for pdata in portfolios_data:
                if pdata['snapshots']:
                    latest_return = pdata['snapshots'][-1][1]
                    summary_parts.append(f"{pdata['name']}: {latest_return:+.2f}%")

            title = f"Portfolio Comparison - {', '.join(summary_parts)}"
            return f"__IMAGE__|||{filepath}|||{title}"

        except Exception as e:
            logger.error(f"Error generating comparison chart: {e}")
            return f"Error generating comparison chart: {str(e)}"

    def _generate_current_comparison(self, portfolios_data: list, portfolio_names: list) -> str:
        """Generate a text comparison when no historical data exists."""
        import yfinance as yf
        from portfolio import get_portfolio

        output = "**📊 Portfolio Comparison**\n"
        output += "_No historical snapshots yet. Here's current status:_\n\n"

        comparison = []

        for name in portfolio_names:
            portfolio = get_portfolio(name)
            if not portfolio:
                continue

            holdings = portfolio.get_holdings()

            # Get current prices
            current_prices = {}
            if holdings:
                tickers = [h["ticker"] for h in holdings]
                try:
                    data = yf.download(tickers, period="1d", progress=False)
                    if len(tickers) == 1:
                        current_prices[tickers[0]] = float(data["Close"].iloc[-1])
                    else:
                        for ticker in tickers:
                            try:
                                current_prices[ticker] = float(data["Close"][ticker].iloc[-1])
                            except:
                                pass
                except:
                    pass

            value_data = portfolio.calculate_total_value(current_prices)
            comparison.append({
                'name': portfolio.name,
                'style': portfolio.investment_style,
                'total_value': value_data['total_value'],
                'return_pct': value_data['total_return_pct'],
                'return_amt': value_data['total_return'],
                'positions': len(holdings)
            })

        # Sort by return
        comparison.sort(key=lambda x: x['return_pct'], reverse=True)

        for i, p in enumerate(comparison, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            emoji = "📈" if p['return_pct'] >= 0 else "📉"
            output += f"{medal} **{p['name']}** ({p['style']})\n"
            output += f"   Value: ${p['total_value']:,.2f} | {emoji} {p['return_pct']:+.2f}%\n"
            output += f"   Positions: {p['positions']}\n\n"

        output += "_Charts will be available once daily snapshots accumulate._"
        return output
