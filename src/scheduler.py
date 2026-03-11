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

from export_dashboard import export_dashboard, save_analysis_report, save_portfolio_analysis

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

        # First, generate and save the market sentiment report for the website
        try:
            self._generate_market_sentiment_report()
        except Exception as e:
            logger.error(f"Error generating market sentiment report: {e}")

        # Check and execute any pending orders
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

    def _generate_market_sentiment_report(self):
        """Generate market sentiment report — data gathered directly, summarized with Gemini Flash.

        Token optimization: No LLM tool-use loop. Tools are called as Python functions,
        then raw data is sent to Gemini Flash (via OpenRouter) for cheap summarization.
        """
        from data_gather import gather_market_sentiment
        from llm_router import summarize_with_flash

        logger.info("Generating market sentiment report (Gemini Flash)")

        # Step 1: Gather all data directly (no LLM needed)
        raw_data = gather_market_sentiment(
            tickers=["$SPY", "$AAPL", "$NVDA", "$TSLA"]
        )
        logger.info(f"Raw sentiment data gathered: {len(raw_data)} chars")

        # Step 2: Summarize with Gemini Flash (cheap)
        instruction = """Synthesize the raw market data below into a concise **Market Sentiment Report**.

Use this exact format:

# **Market Sentiment Report** - [Today's Date]

Let me pinch together the current market vibes from across the trading ecosystem:

## 𝕏 X/Twitter Sentiment
[Include bullish/bearish percentages for key tickers]

## 🏛️ Institutional Sentiment (Motley Fool)
[Summarize key themes, stocks being discussed]

## 🎰 Retail Trader Sentiment (WSB)
[Summarize hot tickers, mood, key catalysts]

## 🔮 Macro Prediction Markets (Polymarket)
[Summarize what traders are betting on]

## 🦀 BigClaw's Take
[Your synthesis: overall market mood, what to watch, crab wisdom]

---
This is for educational purposes only, not financial advice.

IMPORTANT: Only use data provided below. Do not make up information."""

        try:
            response = summarize_with_flash(raw_data, instruction, max_tokens=2048)

            if response.startswith("ERROR:"):
                logger.error(f"Gemini Flash failed: {response}")
                # Fallback: return truncated raw data
                response = f"# Market Sentiment Report - {datetime.now().strftime('%B %d, %Y')}\n\n{raw_data[:3000]}"

            logger.info("Market sentiment report generated via Gemini Flash")

            # Save to analysis.json for the website
            save_analysis_report(response, "Market Overview")

            # Send to report channel
            from portfolio import get_active_portfolios
            portfolios = get_active_portfolios()
            if portfolios and portfolios[0].report_channel:
                self._send_message(
                    portfolios[0].report_channel,
                    f"**🦀 Morning Market Sentiment Report**\n\n{response[:2000]}"
                )

            return response

        except Exception as e:
            logger.error(f"Market sentiment report error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return f"Error generating report: {str(e)}"

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

        Token optimization: Data is gathered directly via Python tool calls (free).
        Only the trade DECISION uses Sonnet — a single API call with pre-gathered
        data, no tool-use loop. Cuts ~90% of token usage per portfolio.

        Args:
            portfolio: Portfolio object to trade

        Returns:
            The agent's response describing actions taken
        """
        from data_gather import gather_portfolio_data
        from tools import TOOL_MAP

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

        holding_tickers = [h['ticker'] for h in holdings] if holdings else []

        # Style-specific risk management guidance
        style_lower = portfolio.investment_style.lower()
        if "cathie" in style_lower or "ark" in style_lower or "wood" in style_lower:
            risk_guidance = """**Risk Management (Cathie Wood/ARK Style):**
- DO NOT use stop losses - ARK holds through volatility
- Only exit when investment thesis changes, NOT based on price action
- Use position sizing for risk management - no single position > 10%
- Consider adding on significant pullbacks if thesis intact
- 5-year time horizons for disruptive technology themes"""
        elif "buffett" in style_lower or "value" in style_lower:
            risk_guidance = """**Risk Management (Value/Buffett Style):**
- Wide stop losses (15-20%) only as safety net
- Primary exit signal is thesis change, not price
- Look for margin of safety in all positions"""
        elif "momentum" in style_lower:
            risk_guidance = """**Risk Management (Momentum Style):**
- Tight stop losses (5-10% below entry)
- Cut losers quickly, let winners run
- Exit when momentum indicators turn negative"""
        else:
            risk_guidance = """**Risk Management:**
- Appropriate stop losses based on volatility
- set_stop_loss for downside protection
- set_limit_sell for profit targets"""

        # Step 1: Gather all sentiment/quote data directly (NO LLM, NO TOKENS)
        logger.info(f"Gathering data for {portfolio.name} (direct tool calls)...")
        raw_data = gather_portfolio_data(portfolio, holding_tickers)
        logger.info(f"Data gathered for {portfolio.name}: {len(raw_data)} chars")

        # Step 2: Single Sonnet call for trade decision (no tool loop)
        analysis_prompt = f"""You are managing the "{portfolio.name}" portfolio with a {portfolio.investment_style} investment style.

**Current Portfolio Status:**
- Cash Available: ${portfolio.current_cash:,.2f}
- Starting Capital: ${portfolio.starting_cash:,.2f}

**Current Holdings:**
{holdings_str}

{risk_guidance}

**MARKET DATA (pre-gathered):**
{raw_data[:6000]}

**YOUR TASK:**
Based on the sentiment and price data above:
1. Assess each holding's sentiment (bullish/bearish/mixed)
2. Identify any new opportunities matching {portfolio.investment_style} style
3. Make specific trade recommendations with rationale

For each trade decision, output EXACTLY one line per trade in this format:
TRADE: BUY <ticker> <dollar_amount>
TRADE: SELL <ticker> <shares>

After the trade lines, provide a brief summary of your reasoning.

Guidelines:
- With ${portfolio.current_cash:,.0f} available, consider positions of $15,000-$25,000
- Include X sentiment percentages in your rationale
- Only trade when sentiment strongly supports it
- If no strong signals, output: TRADE: NONE

Begin your analysis now."""

        try:
            # Single Sonnet API call — no tool loop, no iterations
            response = self.anthropic_client.messages.create(
                model=self.model,
                max_tokens=2048,
                system="You are BigClaw AI, an autonomous trading assistant. Analyze the pre-gathered market data and make trading decisions. Be concise and decisive.",
                messages=[{"role": "user", "content": analysis_prompt}]
            )

            # Extract text response
            response_text = ""
            for block in response.content:
                if block.type == "text":
                    response_text = block.text
                    break

            logger.info(f"Trading analysis complete for {portfolio.name}")

            # Step 3: Execute any trades from the response
            self._execute_trades_from_response(portfolio, response_text)

            # Send summary to Slack if report channel is set
            if portfolio.report_channel:
                self._send_message(
                    portfolio.report_channel,
                    f"**🤖 Autonomous Trading: {portfolio.name}**\n\n{response_text[:2000]}"
                )

            return response_text

        except Exception as e:
            error_msg = f"Agent error for {portfolio.name}: {e}"
            logger.error(error_msg)
            import traceback
            logger.error(traceback.format_exc())
            return f"Error during analysis: {str(e)}"

    def _execute_trades_from_response(self, portfolio, response_text: str):
        """Parse and execute TRADE: lines from Sonnet's response.

        Args:
            portfolio: Portfolio to execute trades on
            response_text: Sonnet's response containing TRADE: lines
        """
        import re
        from tools import TOOL_MAP

        buy_tool = TOOL_MAP.get("buy_stock")
        sell_tool = TOOL_MAP.get("sell_stock")

        for line in response_text.split("\n"):
            line = line.strip()
            if not line.startswith("TRADE:"):
                continue

            parts = line.replace("TRADE:", "").strip().split()
            if len(parts) < 2:
                continue

            action = parts[0].upper()
            if action == "NONE":
                logger.info(f"No trades for {portfolio.name}")
                continue

            ticker = parts[1].upper().replace("$", "")

            try:
                if action == "BUY" and len(parts) >= 3 and buy_tool:
                    amount = float(parts[2].replace(",", "").replace("$", ""))
                    result = buy_tool.execute(
                        portfolio_name=portfolio.name,
                        ticker=ticker,
                        amount=amount
                    )
                    logger.info(f"Executed BUY {ticker} ${amount:,.0f}: {result[:200]}")

                elif action == "SELL" and len(parts) >= 3 and sell_tool:
                    shares = float(parts[2].replace(",", ""))
                    result = sell_tool.execute(
                        portfolio_name=portfolio.name,
                        ticker=ticker,
                        shares=shares
                    )
                    logger.info(f"Executed SELL {ticker} {shares} shares: {result[:200]}")

            except Exception as e:
                logger.error(f"Trade execution error ({action} {ticker}): {e}")

    def _send_daily_reports(self):
        """Send daily performance reports for all portfolios."""
        from portfolio import get_active_portfolios
        import yfinance as yf

        logger.info("Generating daily reports")

        portfolios = get_active_portfolios()
        if not portfolios:
            return

        # Collect all reports for the website
        all_reports = []

        for portfolio in portfolios:
            try:
                report = self._generate_report(portfolio)
                all_reports.append(report)

                # Send to Slack/Discord if channel is set
                if portfolio.report_channel:
                    self._send_message(portfolio.report_channel, report)
            except Exception as e:
                logger.error(f"Error generating report for {portfolio.name}: {e}")

        # Save combined portfolio analysis to website
        if all_reports:
            try:
                combined_report = "\n\n---\n\n".join(all_reports)
                combined_report += "\n\n---\n_This is for educational purposes only, not financial advice._"
                save_portfolio_analysis(combined_report, "All Portfolios")
                logger.info("Portfolio analysis saved to website")
            except Exception as e:
                logger.error(f"Failed to save portfolio analysis: {e}")

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
