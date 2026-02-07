"""Prediction market tools for BigClaw AI - Polymarket integration."""

import logging
import requests
from datetime import datetime
from typing import Optional

from .base import BaseTool

logger = logging.getLogger(__name__)


class PolymarketSearchTool(BaseTool):
    """Search Polymarket prediction markets."""

    @property
    def name(self) -> str:
        return "search_polymarket"

    @property
    def description(self) -> str:
        return """Search Polymarket for prediction markets on real-world events.

Polymarket is a prediction market where users bet on outcomes of events.
The prices represent crowd-sourced probabilities (e.g., 65 cents = 65% probability).

Great for:
- Federal Reserve decisions (rate hikes, cuts)
- Elections and political outcomes
- Economic indicators (recession, inflation)
- Crypto prices and events
- Geopolitical events that impact markets

Use when users ask about:
- "What are the odds of a rate cut?"
- "What does Polymarket say about the election?"
- "Prediction market on recession?"
- "What events are people betting on?"
"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term (e.g., 'fed rate', 'bitcoin', 'recession', 'election')"
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of markets to return (default 10, max 20)"
                }
            },
            "required": ["query"]
        }

    def execute(self, query: str, limit: int = 10) -> str:
        query = query.strip()
        limit = min(max(3, limit), 20)

        logger.info(f"Searching Polymarket for: {query}")

        try:
            # Polymarket Gamma API for market discovery
            url = "https://gamma-api.polymarket.com/markets"
            params = {
                "closed": "false",
                "limit": limit * 2,  # Get extra to filter
            }

            response = requests.get(url, params=params, timeout=15)

            if response.status_code != 200:
                return f"Error fetching Polymarket data: HTTP {response.status_code}"

            markets = response.json()

            # Filter markets by query (case-insensitive)
            query_lower = query.lower()
            filtered = []
            for market in markets:
                question = market.get("question", "").lower()
                description = market.get("description", "").lower()
                if query_lower in question or query_lower in description:
                    filtered.append(market)
                    if len(filtered) >= limit:
                        break

            if not filtered:
                # If no matches, return top active markets
                return f"No markets found matching '{query}'. Try broader terms like 'fed', 'election', 'bitcoin', or 'recession'."

            output = f"**Polymarket: '{query}'**\n"
            output += f"Found {len(filtered)} prediction markets\n\n"

            for i, market in enumerate(filtered, 1):
                question = market.get("question", "Unknown")
                outcome_prices = market.get("outcomePrices", "")
                outcomes = market.get("outcomes", "")
                volume = market.get("volume", 0)
                liquidity = market.get("liquidity", 0)
                end_date = market.get("endDate", "")

                # Parse outcome prices
                try:
                    if outcome_prices and outcomes:
                        # outcomePrices is a JSON string like "[\"0.65\",\"0.35\"]"
                        import json
                        prices = json.loads(outcome_prices) if isinstance(outcome_prices, str) else outcome_prices
                        outcome_list = json.loads(outcomes) if isinstance(outcomes, str) else outcomes

                        price_display = []
                        for outcome, price in zip(outcome_list, prices):
                            pct = float(price) * 100
                            price_display.append(f"{outcome}: {pct:.0f}%")
                        odds_str = " | ".join(price_display)
                    else:
                        odds_str = "No odds available"
                except Exception:
                    odds_str = "Odds parsing error"

                # Format volume
                try:
                    vol_num = float(volume) if volume else 0
                    if vol_num >= 1_000_000:
                        vol_str = f"${vol_num/1_000_000:.1f}M"
                    elif vol_num >= 1000:
                        vol_str = f"${vol_num/1000:.0f}K"
                    else:
                        vol_str = f"${vol_num:.0f}"
                except Exception:
                    vol_str = "N/A"

                # Format end date
                if end_date:
                    try:
                        end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                        end_str = end_dt.strftime("%b %d, %Y")
                    except Exception:
                        end_str = end_date[:10] if len(end_date) >= 10 else "Unknown"
                else:
                    end_str = "Ongoing"

                output += f"**{i}. {question}**\n"
                output += f"   📊 {odds_str}\n"
                output += f"   💰 Volume: {vol_str} | Ends: {end_str}\n\n"

            output += "_Prices represent crowd-sourced probabilities (65¢ = 65% chance)_"

            return output

        except requests.exceptions.Timeout:
            return "Polymarket request timed out. Try again."
        except Exception as e:
            logger.error(f"Polymarket error: {e}")
            return f"Error fetching Polymarket data: {str(e)}"


class PolymarketTrendingTool(BaseTool):
    """Get trending/high-volume Polymarket markets."""

    @property
    def name(self) -> str:
        return "get_polymarket_trending"

    @property
    def description(self) -> str:
        return """Get trending prediction markets from Polymarket.

Returns the most active markets by trading volume - shows what events
traders are betting on most heavily right now.

Use when users ask about:
- "What's trending on prediction markets?"
- "What events are traders betting on?"
- "Show me hot Polymarket markets"
- "What macro events should I watch?"
"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["all", "politics", "crypto", "sports", "business"],
                    "description": "Filter by category (default: all)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of markets to return (default 10, max 15)"
                }
            },
            "required": []
        }

    def execute(self, category: str = "all", limit: int = 10) -> str:
        limit = min(max(5, limit), 15)

        logger.info(f"Fetching trending Polymarket markets, category: {category}")

        try:
            # Polymarket Gamma API - get markets sorted by volume
            url = "https://gamma-api.polymarket.com/markets"
            params = {
                "closed": "false",
                "limit": 50,  # Get more to sort/filter
            }

            response = requests.get(url, params=params, timeout=15)

            if response.status_code != 200:
                return f"Error fetching Polymarket data: HTTP {response.status_code}"

            markets = response.json()

            # Sort by volume (descending)
            def get_volume(m):
                try:
                    return float(m.get("volume", 0))
                except (ValueError, TypeError):
                    return 0

            markets_sorted = sorted(markets, key=get_volume, reverse=True)

            # Filter by category if specified
            if category != "all":
                category_keywords = {
                    "politics": ["election", "trump", "biden", "president", "congress", "senate", "vote", "political"],
                    "crypto": ["bitcoin", "btc", "ethereum", "eth", "crypto", "solana", "coin"],
                    "sports": ["nfl", "nba", "mlb", "super bowl", "championship", "world series", "playoffs"],
                    "business": ["fed", "rate", "inflation", "recession", "gdp", "stock", "market", "economy", "earnings"]
                }
                keywords = category_keywords.get(category, [])
                if keywords:
                    filtered = []
                    for m in markets_sorted:
                        q = m.get("question", "").lower()
                        if any(kw in q for kw in keywords):
                            filtered.append(m)
                    markets_sorted = filtered

            markets_sorted = markets_sorted[:limit]

            if not markets_sorted:
                return f"No active markets found for category '{category}'."

            output = f"**🔥 Trending Polymarket Markets"
            if category != "all":
                output += f" ({category.title()})"
            output += "**\n\n"

            for i, market in enumerate(markets_sorted, 1):
                question = market.get("question", "Unknown")
                outcome_prices = market.get("outcomePrices", "")
                outcomes = market.get("outcomes", "")
                volume = market.get("volume", 0)

                # Parse leading outcome probability
                try:
                    import json
                    if outcome_prices and outcomes:
                        prices = json.loads(outcome_prices) if isinstance(outcome_prices, str) else outcome_prices
                        outcome_list = json.loads(outcomes) if isinstance(outcomes, str) else outcomes

                        # Find highest probability outcome
                        max_idx = 0
                        max_price = 0
                        for idx, price in enumerate(prices):
                            p = float(price)
                            if p > max_price:
                                max_price = p
                                max_idx = idx

                        leading = outcome_list[max_idx] if max_idx < len(outcome_list) else "Yes"
                        pct = max_price * 100
                        odds_str = f"**{leading}: {pct:.0f}%**"
                    else:
                        odds_str = "No odds"
                except Exception:
                    odds_str = "N/A"

                # Format volume
                try:
                    vol_num = float(volume) if volume else 0
                    if vol_num >= 1_000_000:
                        vol_str = f"${vol_num/1_000_000:.1f}M"
                    elif vol_num >= 1000:
                        vol_str = f"${vol_num/1000:.0f}K"
                    else:
                        vol_str = f"${vol_num:.0f}"
                except Exception:
                    vol_str = "N/A"

                # Truncate long questions
                if len(question) > 100:
                    question = question[:100] + "..."

                output += f"{i}. {question}\n"
                output += f"   {odds_str} | Volume: {vol_str}\n\n"

            output += "_Prices = probability. Higher volume = more trader interest._"

            return output

        except requests.exceptions.Timeout:
            return "Polymarket request timed out. Try again."
        except Exception as e:
            logger.error(f"Polymarket trending error: {e}")
            return f"Error fetching Polymarket data: {str(e)}"
