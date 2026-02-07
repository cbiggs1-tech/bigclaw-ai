"""Order management tools for BigClaw AI.

Provides tools for:
- Stop loss orders (sell if price drops below threshold)
- Limit buy orders (buy if price drops to target)
- Limit sell orders (take profit when price rises)
- Viewing and canceling pending orders
"""

import logging
from .base import BaseTool

logger = logging.getLogger(__name__)


class SetStopLossTool(BaseTool):
    """Set a stop loss order on an existing position."""

    @property
    def name(self) -> str:
        return "set_stop_loss"

    @property
    def description(self) -> str:
        return """Set a stop loss order to automatically sell if price drops below a threshold.

Stop losses protect against large losses by automatically selling when a stock drops to a certain price.

Guidelines by investment style:
- Value (Buffett): Wider stops (15-20%) - trust your thesis unless fundamentals change
- Cathie Wood/ARK: DO NOT USE STOP LOSSES - ARK holds through volatility on high-conviction names. Only exit on thesis change, not price action. Use position sizing for risk management instead.
- Momentum: Tight stops (5-10%) - cut losers quickly

The order will be checked during scheduled trading analysis and executed if triggered.
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
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol"
                },
                "stop_price": {
                    "type": "number",
                    "description": "Price at which to trigger the sell (sell if price <= this)"
                },
                "shares": {
                    "type": "number",
                    "description": "Number of shares to sell (optional, defaults to entire position)"
                },
                "rationale": {
                    "type": "string",
                    "description": "Reason for this stop loss level"
                }
            },
            "required": ["portfolio_name", "ticker", "stop_price"]
        }

    def execute(self, portfolio_name: str, ticker: str, stop_price: float,
                shares: float = None, rationale: str = "") -> str:
        from portfolio import get_portfolio, create_pending_order

        ticker = ticker.upper().strip()

        portfolio = get_portfolio(portfolio_name)
        if not portfolio:
            return f"Portfolio '{portfolio_name}' not found."

        # Check if this is a Cathie Wood/ARK style portfolio
        style_lower = portfolio.investment_style.lower()
        if "cathie" in style_lower or "ark" in style_lower or "wood" in style_lower:
            return f"""**Stop Loss Not Recommended for {portfolio.investment_style} Style**

ARK/Cathie Wood investment philosophy does NOT use traditional stop losses:
- ARK holds through volatility on high-conviction disruptive innovation plays
- Only exit when the investment thesis changes, not based on price action
- Use position sizing for risk management instead

If you still want to set a stop loss, consider using a different investment style portfolio.
For this portfolio, consider:
- Reviewing the thesis for {ticker} instead
- Adjusting position size if concerned about risk
- Setting a price alert instead of an automatic sell"""

        # Check if we have this position
        holding = portfolio.get_holding(ticker)
        if not holding:
            return f"No position in {ticker} to set stop loss on."

        # If no shares specified, use entire position
        if shares is None:
            shares = holding["shares"]
        elif shares > holding["shares"]:
            return f"Cannot set stop loss for {shares} shares - only own {holding['shares']} shares."

        # Validate stop price
        if stop_price >= holding["avg_cost"]:
            logger.warning(f"Stop loss at ${stop_price} is above avg cost ${holding['avg_cost']}")

        # Calculate percentage from avg cost
        stop_pct = ((holding["avg_cost"] - stop_price) / holding["avg_cost"]) * 100

        # Create the order
        order_id = create_pending_order(
            portfolio_id=portfolio.id,
            ticker=ticker,
            order_type="stop_loss",
            trigger_price=stop_price,
            shares=shares,
            rationale=rationale or f"Stop loss at {stop_pct:.1f}% below cost"
        )

        return f"""**Stop Loss Set**

**Order ID:** #{order_id}
**Portfolio:** {portfolio_name}
**Stock:** {ticker}
**Stop Price:** ${stop_price:.2f}
**Shares:** {shares:.2f}
**Current Avg Cost:** ${holding['avg_cost']:.2f}
**Stop Level:** {stop_pct:.1f}% below cost

The position will be sold automatically when the price drops to ${stop_price:.2f} or below.

_Note: Stop loss will be checked during scheduled analysis or when you run analysis manually._"""


class SetLimitBuyTool(BaseTool):
    """Set a limit buy order to buy when price drops to target."""

    @property
    def name(self) -> str:
        return "set_limit_buy"

    @property
    def description(self) -> str:
        return """Set a limit buy order to automatically buy when a stock drops to your target price.

Use this to:
- Buy the dip on stocks you're watching
- Add to positions at better prices
- Scale into a position gradually

The order will be checked during scheduled trading analysis and executed if triggered.
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
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol"
                },
                "limit_price": {
                    "type": "number",
                    "description": "Price at which to trigger the buy (buy if price <= this)"
                },
                "amount": {
                    "type": "number",
                    "description": "Dollar amount to invest when triggered"
                },
                "rationale": {
                    "type": "string",
                    "description": "Investment thesis for this buy"
                }
            },
            "required": ["portfolio_name", "ticker", "limit_price", "amount", "rationale"]
        }

    def execute(self, portfolio_name: str, ticker: str, limit_price: float,
                amount: float, rationale: str) -> str:
        from portfolio import get_portfolio, create_pending_order
        import yfinance as yf

        ticker = ticker.upper().strip()

        portfolio = get_portfolio(portfolio_name)
        if not portfolio:
            return f"Portfolio '{portfolio_name}' not found."

        # Check if enough cash will be available
        if amount > portfolio.current_cash:
            return f"Insufficient cash. Order for ${amount:,.2f} but only ${portfolio.current_cash:,.2f} available."

        # Get current price for context
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1d")
            current_price = float(hist["Close"].iloc[-1]) if not hist.empty else None
        except:
            current_price = None

        # Calculate discount from current
        discount_pct = None
        if current_price and current_price > limit_price:
            discount_pct = ((current_price - limit_price) / current_price) * 100

        # Create the order
        order_id = create_pending_order(
            portfolio_id=portfolio.id,
            ticker=ticker,
            order_type="limit_buy",
            trigger_price=limit_price,
            amount=amount,
            rationale=rationale
        )

        response = f"""**Limit Buy Order Set**

**Order ID:** #{order_id}
**Portfolio:** {portfolio_name}
**Stock:** {ticker}
**Limit Price:** ${limit_price:.2f}
**Amount:** ${amount:,.2f}"""

        if current_price:
            response += f"\n**Current Price:** ${current_price:.2f}"
        if discount_pct:
            response += f"\n**Discount:** {discount_pct:.1f}% below current"

        response += f"""

**Rationale:** {rationale}

The buy order will execute when {ticker} drops to ${limit_price:.2f} or below.

_Note: Limit buy will be checked during scheduled analysis or when you run analysis manually._"""

        return response


class SetLimitSellTool(BaseTool):
    """Set a limit sell (take profit) order."""

    @property
    def name(self) -> str:
        return "set_limit_sell"

    @property
    def description(self) -> str:
        return """Set a limit sell (take profit) order to automatically sell when price reaches target.

Use this to:
- Lock in gains at your target price
- Scale out of a position as it rises
- Maintain discipline on profit targets

Guidelines by investment style:
- Value (Buffett): Higher targets (30-50%+) - let winners run if thesis intact
- Growth (Cathie Wood): Variable - trim on strength, hold long-term winners
- Momentum: Take profits at technical resistance levels

The order will be checked during scheduled trading analysis and executed if triggered.
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
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol"
                },
                "target_price": {
                    "type": "number",
                    "description": "Price at which to trigger the sell (sell if price >= this)"
                },
                "shares": {
                    "type": "number",
                    "description": "Number of shares to sell (optional, defaults to entire position)"
                },
                "rationale": {
                    "type": "string",
                    "description": "Reason for this profit target"
                }
            },
            "required": ["portfolio_name", "ticker", "target_price"]
        }

    def execute(self, portfolio_name: str, ticker: str, target_price: float,
                shares: float = None, rationale: str = "") -> str:
        from portfolio import get_portfolio, create_pending_order

        ticker = ticker.upper().strip()

        portfolio = get_portfolio(portfolio_name)
        if not portfolio:
            return f"Portfolio '{portfolio_name}' not found."

        # Check if we have this position
        holding = portfolio.get_holding(ticker)
        if not holding:
            return f"No position in {ticker} to set take profit on."

        # If no shares specified, use entire position
        if shares is None:
            shares = holding["shares"]
        elif shares > holding["shares"]:
            return f"Cannot set limit sell for {shares} shares - only own {holding['shares']} shares."

        # Validate target price
        if target_price <= holding["avg_cost"]:
            logger.warning(f"Take profit at ${target_price} is below avg cost ${holding['avg_cost']}")

        # Calculate gain percentage
        gain_pct = ((target_price - holding["avg_cost"]) / holding["avg_cost"]) * 100
        potential_profit = (target_price - holding["avg_cost"]) * shares

        # Create the order
        order_id = create_pending_order(
            portfolio_id=portfolio.id,
            ticker=ticker,
            order_type="limit_sell",
            trigger_price=target_price,
            shares=shares,
            rationale=rationale or f"Take profit at {gain_pct:.1f}% gain"
        )

        return f"""**Take Profit Order Set**

**Order ID:** #{order_id}
**Portfolio:** {portfolio_name}
**Stock:** {ticker}
**Target Price:** ${target_price:.2f}
**Shares:** {shares:.2f}
**Current Avg Cost:** ${holding['avg_cost']:.2f}
**Target Gain:** {gain_pct:.1f}%
**Potential Profit:** ${potential_profit:,.2f}

The position will be sold automatically when the price rises to ${target_price:.2f} or above.

_Note: Take profit will be checked during scheduled analysis or when you run analysis manually._"""


class ViewPendingOrdersTool(BaseTool):
    """View all pending orders for a portfolio."""

    @property
    def name(self) -> str:
        return "view_pending_orders"

    @property
    def description(self) -> str:
        return """View all active pending orders (stop losses, limit buys, limit sells) for a portfolio.

Shows order details including trigger prices and current status.
"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "portfolio_name": {
                    "type": "string",
                    "description": "Name of the portfolio (optional - shows all if not specified)"
                }
            },
            "required": []
        }

    def execute(self, portfolio_name: str = None) -> str:
        from portfolio import get_portfolio, get_pending_orders
        import yfinance as yf

        portfolio_id = None
        if portfolio_name:
            portfolio = get_portfolio(portfolio_name)
            if not portfolio:
                return f"Portfolio '{portfolio_name}' not found."
            portfolio_id = portfolio.id

        orders = get_pending_orders(portfolio_id=portfolio_id)

        if not orders:
            if portfolio_name:
                return f"No pending orders for portfolio '{portfolio_name}'."
            return "No pending orders across any portfolio."

        # Get current prices for all tickers
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
                        pass
        except:
            pass

        output = "**Pending Orders**\n\n"

        order_type_emoji = {
            "stop_loss": "🛑",
            "limit_buy": "📥",
            "limit_sell": "📤"
        }

        for order in orders:
            emoji = order_type_emoji.get(order["order_type"], "📋")
            ticker = order["ticker"]
            current = current_prices.get(ticker)

            output += f"{emoji} **#{order['id']} - {order['order_type'].replace('_', ' ').title()}**\n"
            output += f"   Portfolio: {order['portfolio_name']}\n"
            output += f"   Ticker: {ticker}\n"
            output += f"   Trigger: ${order['trigger_price']:.2f}"

            if current:
                output += f" (Current: ${current:.2f})"
                # Show how close to trigger
                if order["order_type"] == "stop_loss":
                    pct_away = ((current - order["trigger_price"]) / current) * 100
                    output += f" - {pct_away:.1f}% above stop"
                elif order["order_type"] == "limit_buy":
                    pct_away = ((current - order["trigger_price"]) / current) * 100
                    output += f" - {pct_away:.1f}% above limit"
                elif order["order_type"] == "limit_sell":
                    pct_away = ((order["trigger_price"] - current) / current) * 100
                    output += f" - {pct_away:.1f}% to target"

            output += "\n"

            if order["shares"]:
                output += f"   Shares: {order['shares']:.2f}\n"
            if order["amount"]:
                output += f"   Amount: ${order['amount']:,.2f}\n"
            if order["rationale"]:
                output += f"   Rationale: {order['rationale']}\n"

            output += f"   Created: {order['created_at']}\n\n"

        return output


class CancelOrderTool(BaseTool):
    """Cancel a pending order."""

    @property
    def name(self) -> str:
        return "cancel_order"

    @property
    def description(self) -> str:
        return """Cancel a pending order by its order ID.

Use view_pending_orders first to see order IDs.
"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "integer",
                    "description": "The order ID to cancel"
                }
            },
            "required": ["order_id"]
        }

    def execute(self, order_id: int) -> str:
        from portfolio import get_order_by_id, cancel_pending_order

        order = get_order_by_id(order_id)
        if not order:
            return f"Order #{order_id} not found."

        if order["status"] != "active":
            return f"Order #{order_id} is already {order['status']} and cannot be cancelled."

        success = cancel_pending_order(order_id)

        if success:
            order_type = order["order_type"].replace("_", " ").title()
            return f"""**Order Cancelled**

**Order ID:** #{order_id}
**Type:** {order_type}
**Portfolio:** {order['portfolio_name']}
**Ticker:** {order['ticker']}
**Trigger Price:** ${order['trigger_price']:.2f}

The order has been cancelled and will not execute."""
        else:
            return f"Failed to cancel order #{order_id}."
