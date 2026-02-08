"""Scheduler for autonomous trading and daily reports.

Handles:
- Daily market analysis using portfolio investment styles
- Autonomous trade execution
- Daily performance reports to Slack AND Discord
"""

import os
import logging
import threading
import asyncio
from datetime import datetime, time
from typing import Optional, Callable
import schedule

from export_dashboard import export_dashboard, save_analysis_report

logger = logging.getLogger(__name__)

# Default trading schedule (Eastern Time approximations)
DEFAULT_ANALYSIS_TIME = "09:00"  # Before market open
DEFAULT_REPORT_TIME = "16:30"    # After market close

# Discord channel ID for reports (set via environment or config)
DISCORD_REPORT_CHANNEL = os.environ.get("DISCORD_REPORT_CHANNEL")


class TradingScheduler:
    """Manages scheduled trading activities."""

    def __init__(self, anthropic_client, slack_app):
        """Initialize the scheduler.

        Args:
            anthropic_client: Anthropic API client for Claude
            slack_app: Slack Bolt app for sending messages
        """
        self.anthropic_client = anthropic_client
        self.slack_app = slack_app
        self.model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")
        self._running = False
        self._thread = None

        # Check if Discord webhook is configured
        if os.environ.get("DISCORD_WEBHOOK_URL"):
            logger.info("Discord webhook configured - reports will sync to Discord")

    def start(self, analysis_time: str = DEFAULT_ANALYSIS_TIME,
              report_time: str = DEFAULT_REPORT_TIME):
        """Start the scheduler.

        Args:
            analysis_time: Time to run daily analysis (HH:MM format)
            report_time: Time to send daily reports (HH:MM format)
        """
        # Schedule daily tasks
        schedule.every().monday.at(analysis_time).do(self._run_daily_analysis)
        schedule.every().tuesday.at(analysis_time).do(self._run_daily_analysis)
        schedule.every().wednesday.at(analysis_time).do(self._run_daily_analysis)
        schedule.every().thursday.at(analysis_time).do(self._run_daily_analysis)
        schedule.every().friday.at(analysis_time).do(self._run_daily_analysis)

        schedule.every().monday.at(report_time).do(self._send_daily_reports)
        schedule.every().tuesday.at(report_time).do(self._send_daily_reports)
        schedule.every().wednesday.at(report_time).do(self._send_daily_reports)
        schedule.every().thursday.at(report_time).do(self._send_daily_reports)
        schedule.every().friday.at(report_time).do(self._send_daily_reports)

        # Start background thread
        self._running = True
        self._thread = threading.Thread(target=self._run_schedule_loop, daemon=True)
        self._thread.start()

        logger.info(f"Trading scheduler started. Analysis at {analysis_time}, Reports at {report_time}")

    def stop(self):
        """Stop the scheduler."""
        self._running = False
        schedule.clear()
        logger.info("Trading scheduler stopped")

    def _run_schedule_loop(self):
        """Background loop that runs scheduled tasks."""
        import time as time_module
        while self._running:
            schedule.run_pending()
            time_module.sleep(60)  # Check every minute

    def _run_daily_analysis(self):
        """Run daily market analysis and trading for all active portfolios."""
        from portfolio import get_active_portfolios
        import yfinance as yf

        logger.info("Starting daily autonomous trading analysis")

        # First, check and execute any pending orders
        self._check_pending_orders()

        portfolios = get_active_portfolios()
        if not portfolios:
            logger.info("No active portfolios for autonomous trading")
            return

        for portfolio in portfolios:
            try:
                self._analyze_and_trade(portfolio)
            except Exception as e:
                logger.error(f"Error analyzing portfolio {portfolio.name}: {e}")

        # Export dashboard data to GitHub Pages
        try:
            export_dashboard()
            logger.info("Dashboard exported after morning analysis")
        except Exception as e:
            logger.error(f"Dashboard export failed: {e}")

    def _check_pending_orders(self):
        """Check all pending orders and execute any that have been triggered."""
        from portfolio import get_pending_orders, get_portfolio_by_id, mark_order_triggered
        import yfinance as yf

        logger.info("Checking pending orders")

        orders = get_pending_orders(status="active")
        if not orders:
            logger.info("No pending orders to check")
            return

        # Get current prices for all tickers with orders
        tickers = list(set(o["ticker"] for o in orders))
        current_prices = {}

        try:
            data = yf.download(tickers, period="1d", progress=False)
            if len(tickers) == 1:
                current_prices[tickers[0]] = float(data["Close"].iloc[-1])
            else:
                for ticker in tickers:
                    try:
                        current_prices[ticker] = float(data["Close"][ticker].iloc[-1])
                    except:
                        logger.warning(f"Could not get price for {ticker}")
        except Exception as e:
            logger.error(f"Error fetching prices for order check: {e}")
            return

        # Check each order
        executed_orders = []
        for order in orders:
            ticker = order["ticker"]
            current_price = current_prices.get(ticker)

            if not current_price:
                continue

            triggered = False
            portfolio = get_portfolio_by_id(order["portfolio_id"])

            if not portfolio:
                logger.warning(f"Portfolio {order['portfolio_id']} not found for order #{order['id']}")
                continue

            # Check if order should trigger
            if order["order_type"] == "stop_loss":
                # Trigger if price <= stop price
                if current_price <= order["trigger_price"]:
                    triggered = True
                    shares = order["shares"]
                    result = portfolio.sell(ticker, shares, current_price,
                                           f"STOP LOSS triggered at ${current_price:.2f} (trigger: ${order['trigger_price']:.2f})")
                    if result["success"]:
                        executed_orders.append({
                            "order": order,
                            "type": "stop_loss",
                            "price": current_price,
                            "result": result
                        })
                        mark_order_triggered(order["id"])
                        logger.info(f"Stop loss #{order['id']} triggered: sold {shares} {ticker} at ${current_price:.2f}")

            elif order["order_type"] == "limit_buy":
                # Trigger if price <= limit price
                if current_price <= order["trigger_price"]:
                    triggered = True
                    amount = order["amount"]
                    shares = amount / current_price
                    result = portfolio.buy(ticker, shares, current_price,
                                          f"LIMIT BUY triggered at ${current_price:.2f} (limit: ${order['trigger_price']:.2f})")
                    if result["success"]:
                        executed_orders.append({
                            "order": order,
                            "type": "limit_buy",
                            "price": current_price,
                            "shares": shares,
                            "result": result
                        })
                        mark_order_triggered(order["id"])
                        logger.info(f"Limit buy #{order['id']} triggered: bought {shares:.2f} {ticker} at ${current_price:.2f}")

            elif order["order_type"] == "limit_sell":
                # Trigger if price >= target price
                if current_price >= order["trigger_price"]:
                    triggered = True
                    shares = order["shares"]
                    result = portfolio.sell(ticker, shares, current_price,
                                           f"TAKE PROFIT triggered at ${current_price:.2f} (target: ${order['trigger_price']:.2f})")
                    if result["success"]:
                        executed_orders.append({
                            "order": order,
                            "type": "limit_sell",
                            "price": current_price,
                            "result": result
                        })
                        mark_order_triggered(order["id"])
                        logger.info(f"Take profit #{order['id']} triggered: sold {shares} {ticker} at ${current_price:.2f}")

        # Send notifications for executed orders
        if executed_orders:
            self._notify_executed_orders(executed_orders)

        logger.info(f"Order check complete. Executed {len(executed_orders)} orders.")

    def _notify_executed_orders(self, executed_orders: list):
        """Send Slack notifications for executed orders."""
        for exec_order in executed_orders:
            order = exec_order["order"]
            portfolio_channel = None

            # Get portfolio's report channel
            from portfolio import get_portfolio_by_id
            portfolio = get_portfolio_by_id(order["portfolio_id"])
            if portfolio and portfolio.report_channel:
                portfolio_channel = portfolio.report_channel

            if portfolio_channel:
                order_type_emoji = {
                    "stop_loss": "🛑",
                    "limit_buy": "📥",
                    "limit_sell": "📤"
                }
                emoji = order_type_emoji.get(exec_order["type"], "📋")
                order_type_name = exec_order["type"].replace("_", " ").title()

                result = exec_order["result"]
                message = f"{emoji} **Order Executed: {order_type_name}**\n\n"
                message += f"**Portfolio:** {order['portfolio_name']}\n"
                message += f"**Ticker:** {order['ticker']}\n"
                message += f"**Price:** ${exec_order['price']:.2f}\n"

                if exec_order["type"] in ["stop_loss", "limit_sell"]:
                    message += f"**Shares Sold:** {order['shares']:.2f}\n"
                    message += f"**Total Value:** ${result.get('total_value', 0):,.2f}\n"
                    if "profit" in result:
                        profit_emoji = "+" if result["profit"] >= 0 else ""
                        message += f"**Profit/Loss:** {profit_emoji}${result['profit']:,.2f}\n"
                else:
                    message += f"**Shares Bought:** {exec_order.get('shares', 0):.2f}\n"
                    message += f"**Total Cost:** ${result.get('total_cost', 0):,.2f}\n"

                self._send_message(portfolio_channel, message)

    def _analyze_and_trade(self, portfolio) -> str:
        """Analyze market and execute trades for a portfolio.

        Args:
            portfolio: Portfolio object to trade

        Returns:
            The agent's response describing actions taken
        """
        from agent import BigClawAgent

        logger.info(f"Analyzing portfolio: {portfolio.name} ({portfolio.investment_style})")

        # Get current holdings for context
        holdings = portfolio.get_holdings()
        holdings_str = ""
        if holdings:
            holdings_str = "\n".join([
                f"- {h['ticker']}: {h['shares']} shares @ ${h['avg_cost']:.2f}"
                for h in holdings
            ])
        else:
            holdings_str = "No current holdings"

        # Build tickers list for sentiment analysis
        holding_tickers = [h['ticker'] for h in holdings] if holdings else []

        # Style-specific risk management guidance
        style_lower = portfolio.investment_style.lower()
        if "cathie" in style_lower or "ark" in style_lower or "wood" in style_lower:
            risk_guidance = """**Risk Management (Cathie Wood/ARK Style):**
- DO NOT use stop losses - ARK holds through volatility on high-conviction disruptive innovation plays
- Only exit positions when the investment thesis changes, NOT based on price action
- Accept volatility as the price of innovation exposure
- Use position sizing (not stops) for risk management - no single position > 10% of portfolio
- Consider adding to positions on significant pullbacks if thesis remains intact
- Focus on 5-year time horizons for disruptive technology themes"""
        elif "buffett" in style_lower or "value" in style_lower:
            risk_guidance = """**Risk Management (Value/Buffett Style):**
- Use wide stop losses (15-20% below cost) only as a safety net
- Primary exit signal is thesis change, not price movement
- Look for margin of safety in all positions
- Consider using set_stop_loss for catastrophic protection only
- Be patient - value takes time to be recognized by the market"""
        elif "momentum" in style_lower:
            risk_guidance = """**Risk Management (Momentum Style):**
- Use tight stop losses (5-10% below entry)
- Cut losers quickly, let winners run
- Use set_stop_loss on all new positions
- Consider trailing stops to protect gains
- Exit when momentum indicators turn negative"""
        else:
            risk_guidance = """**Risk Management:**
- Consider appropriate stop losses based on position volatility
- Use set_stop_loss for downside protection
- Use set_limit_sell for profit targets"""

        # Build analysis prompt with sentiment tools
        analysis_prompt = f"""You are managing the "{portfolio.name}" portfolio with a {portfolio.investment_style} investment style.

**Current Portfolio Status:**
- Portfolio Name: {portfolio.name}
- Cash Available: ${portfolio.current_cash:,.2f}
- Starting Capital: ${portfolio.starting_cash:,.2f}

**Current Holdings:**
{holdings_str}

**Your Analysis Process:**

**Step 1 - X/Twitter Sentiment (CRITICAL - DO THIS FIRST):**
X sentiment is the PRIMARY indicator for market mood. For EACH stock you're considering:
- Use get_x_sentiment with the ticker (e.g., "$AAPL", "$NVDA", "$TSLA")
- Check at least 3-4 key tickers relevant to this portfolio style
- This data drives your trading decisions

**Step 2 - Additional Sentiment Sources:**
- Use get_stocktwits_sentiment for real-time trader sentiment
- Use search_reddit_stocks to see retail investor discussion

**Step 3 - Price Data:**
- Use get_stock_quote for current prices on stocks you're considering

**Step 4 - Make Trading Decisions:**
Based primarily on X sentiment:
- Strongly bullish X sentiment + solid fundamentals = consider buying
- Strongly bearish X sentiment on a holding = consider reducing/selling
- Mixed sentiment = hold current position
- Aim for 2-3 positions to start if no holdings

**Step 5 - EXECUTE Trades:**
Use buy_stock or sell_stock to execute your decisions.

**How to buy stocks:**
Call buy_stock with these exact parameters:
- portfolio_name: "{portfolio.name}"
- ticker: the stock symbol (e.g., "AAPL")
- amount: dollar amount to invest (e.g., 10000 for $10,000)

Example: buy_stock(portfolio_name="{portfolio.name}", ticker="AAPL", amount=15000)

**Guidelines for {portfolio.investment_style} style:**
- Apply the principles of this investment philosophy
- With ${portfolio.current_cash:,.0f} available, consider 3-5 positions of $15,000-$25,000 each
- Diversify across different sectors
- Include sentiment findings in your rationale for each trade

{risk_guidance}

**IMPORTANT:**
- ALWAYS start with get_x_sentiment - this is your PRIMARY data source
- Check X sentiment for at least 3-4 tickers before doing anything else
- Include X sentiment percentages in your trading rationale
- Execute buy_stock/sell_stock calls based on your analysis
- Provide a clear summary of X sentiment findings in your response

Begin your analysis now."""

        # Run the agent
        agent = BigClawAgent(self.anthropic_client)
        try:
            response = agent.run(analysis_prompt)
            logger.info(f"Trading analysis complete for {portfolio.name}")
            logger.info(f"Response: {response[:500]}...")

            # Send summary to Slack if report channel is set
            if portfolio.report_channel:
                self._send_message(
                    portfolio.report_channel,
                    f"**🤖 Autonomous Trading: {portfolio.name}**\n\n{response[:2000]}"
                )

            # Save analysis report to JSON for dashboard
            try:
                save_analysis_report(response, portfolio.name)
                logger.info(f"Saved analysis report for {portfolio.name}")
            except Exception as e:
                logger.error(f"Failed to save analysis report: {e}")

            return response

        except Exception as e:
            error_msg = f"Agent error for {portfolio.name}: {e}"
            logger.error(error_msg)
            import traceback
            logger.error(traceback.format_exc())
            return f"Error during analysis: {str(e)}"

    def _send_daily_reports(self):
        """Send daily performance reports for all portfolios."""
        from portfolio import get_active_portfolios
        import yfinance as yf

        logger.info("Generating daily reports")

        portfolios = get_active_portfolios()
        if not portfolios:
            return

        for portfolio in portfolios:
            if not portfolio.report_channel:
                continue

            try:
                report = self._generate_report(portfolio)
                self._send_message(portfolio.report_channel, report)

                # Save report to JSON for dashboard
                try:
                    save_analysis_report(report, portfolio.name)
                    logger.info(f"Saved evening report for {portfolio.name}")
                except Exception as e:
                    logger.error(f"Failed to save evening report: {e}")
            except Exception as e:
                logger.error(f"Error generating report for {portfolio.name}: {e}")

        # Export dashboard data to GitHub Pages
        try:
            export_dashboard()
            logger.info("Dashboard exported after evening reports")
        except Exception as e:
            logger.error(f"Dashboard export failed: {e}")

    def _generate_report(self, portfolio) -> str:
        """Generate a daily performance report for a portfolio."""
        import yfinance as yf

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
            except Exception as e:
                logger.warning(f"Price fetch error: {e}")

        # Calculate values
        value_data = portfolio.calculate_total_value(current_prices)

        # Save daily snapshot
        portfolio.save_daily_snapshot(
            value_data["total_value"],
            value_data["holdings_value"]
        )

        # Get today's transactions
        transactions = portfolio.get_transactions(limit=10)
        today = datetime.now().strftime("%Y-%m-%d")
        today_txns = [t for t in transactions if t["executed_at"].startswith(today)]

        # Build report
        return_emoji = "📈" if value_data['total_return'] >= 0 else "📉"

        report = f"""**📊 Daily Report: {portfolio.name}**
_{datetime.now().strftime("%B %d, %Y")}_

**Investment Style:** {portfolio.investment_style}

**Portfolio Value:**
• Cash: ${value_data['cash']:,.2f}
• Holdings: ${value_data['holdings_value']:,.2f}
• **Total: ${value_data['total_value']:,.2f}**
• {return_emoji} Return: {value_data['total_return_pct']:+.2f}% (${value_data['total_return']:+,.2f})

"""

        if value_data['positions']:
            report += "**Holdings:**\n"
            for pos in sorted(value_data['positions'], key=lambda x: x['value'], reverse=True):
                emoji = "🟢" if pos['gain'] >= 0 else "🔴"
                report += f"• {pos['ticker']}: {pos['shares']:.0f} shares | ${pos['value']:,.0f} ({emoji}{pos['gain_pct']:+.1f}%)\n"
            report += "\n"

        if today_txns:
            report += "**Today's Trades:**\n"
            for t in today_txns:
                action_emoji = "🟢" if t["action"] == "BUY" else "🔴"
                report += f"• {action_emoji} {t['action']} {t['shares']:.0f} {t['ticker']} @ ${t['price']:.2f}\n"
        else:
            report += "_No trades today_\n"

        return report

    def _send_message(self, channel: str, message: str):
        """Send a message to Slack and Discord (if configured)."""
        # Send to Slack
        try:
            self.slack_app.client.chat_postMessage(
                channel=channel,
                text=message
            )
            logger.info(f"Sent Slack message to {channel}")
        except Exception as e:
            logger.error(f"Failed to send Slack message to {channel}: {e}")

        # Also send to Discord if configured
        self._send_discord_message(message)

    def _send_discord_message(self, message: str):
        """Send a message to Discord via webhook."""
        import requests

        webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
        if not webhook_url:
            logger.debug("No Discord webhook configured - skipping Discord notification")
            return

        try:
            # Discord has 2000 char limit - split if needed
            if len(message) > 2000:
                chunks = [message[i:i+1990] for i in range(0, len(message), 1990)]
                for chunk in chunks:
                    requests.post(webhook_url, json={"content": chunk}, timeout=10)
            else:
                requests.post(webhook_url, json={"content": message}, timeout=10)

            logger.info("Sent Discord webhook message")
        except Exception as e:
            logger.error(f"Failed to send Discord webhook message: {e}")

    def run_now(self, portfolio_name: str = None) -> str:
        """Manually trigger analysis and trading.

        Args:
            portfolio_name: Specific portfolio to analyze, or None for all

        Returns:
            The analysis result/response
        """
        from portfolio import get_portfolio, get_active_portfolios

        if portfolio_name:
            portfolio = get_portfolio(portfolio_name)
            if portfolio:
                return self._analyze_and_trade(portfolio)
            else:
                logger.warning(f"Portfolio '{portfolio_name}' not found")
                return f"Portfolio '{portfolio_name}' not found."
        else:
            self._run_daily_analysis()
            return "Daily analysis triggered for all active portfolios."

    def report_now(self, portfolio_name: str = None):
        """Manually trigger reports.

        Args:
            portfolio_name: Specific portfolio to report, or None for all
        """
        from portfolio import get_portfolio, get_active_portfolios

        if portfolio_name:
            portfolio = get_portfolio(portfolio_name)
            if portfolio and portfolio.report_channel:
                report = self._generate_report(portfolio)
                self._send_message(portfolio.report_channel, report)
        else:
            self._send_daily_reports()


# Global scheduler instance
_scheduler: Optional[TradingScheduler] = None


def get_scheduler() -> Optional[TradingScheduler]:
    """Get the global scheduler instance."""
    return _scheduler


def init_scheduler(anthropic_client, slack_app) -> TradingScheduler:
    """Initialize and return the global scheduler."""
    global _scheduler
    _scheduler = TradingScheduler(anthropic_client, slack_app)
    return _scheduler
