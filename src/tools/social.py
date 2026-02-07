"""Social sentiment tools for BigClaw AI - Stocktwits, Reddit, and X/Twitter."""

import logging
import os
import re
import time
from datetime import datetime
from typing import Optional
import requests

from .base import BaseTool

logger = logging.getLogger(__name__)

# X/Twitter API configuration
X_BEARER_TOKEN = os.environ.get("X_BEARER_TOKEN")

# Apify configuration (fallback)
APIFY_API_TOKEN = os.environ.get("APIFY_API_TOKEN")
APIFY_TWEET_ACTOR = "apidojo~tweet-scraper"


class StocktwitsSentimentTool(BaseTool):
    """Get sentiment and recent messages from Stocktwits."""

    @property
    def name(self) -> str:
        return "get_stocktwits_sentiment"

    @property
    def description(self) -> str:
        return """Get real-time social sentiment from Stocktwits for a stock.

Stocktwits is a social platform focused on stocks where traders share ideas.
Returns:
- Overall sentiment (bullish/bearish)
- Recent messages about the ticker
- Message volume

Use when users ask about:
- "What's the sentiment on TSLA?"
- "What are traders saying about AAPL?"
- "Is there buzz around NVDA?"
"""

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
                    "description": "Number of messages to return (default 10, max 30)"
                }
            },
            "required": ["ticker"]
        }

    def execute(self, ticker: str, limit: int = 10) -> str:
        ticker = ticker.upper().strip().replace("$", "")
        limit = min(max(5, limit), 30)

        logger.info(f"Fetching Stocktwits sentiment for {ticker}")

        # Try direct API first
        result = self._try_direct_api(ticker, limit)
        if result:
            return result

        # Fall back to Apify scraper if API blocked
        logger.info(f"Direct API blocked, trying Apify scraper for {ticker}")
        result = self._try_apify_scraper(ticker, limit)
        if result:
            return result

        return f"Stocktwits is currently unavailable for {ticker}. Use get_x_sentiment or search_reddit_stocks for social sentiment instead."

    def _try_direct_api(self, ticker: str, limit: int) -> Optional[str]:
        """Try the direct Stocktwits API."""
        try:
            url = f"https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Referer": "https://stocktwits.com/",
                "Origin": "https://stocktwits.com",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-site",
            }

            session = requests.Session()
            response = session.get(url, headers=headers, timeout=10)

            if response.status_code == 404:
                return f"Ticker '{ticker}' not found on Stocktwits."

            if response.status_code != 200:
                logger.warning(f"Stocktwits API returned HTTP {response.status_code}")
                return None  # Trigger fallback

            data = response.json()

            # Get symbol info
            symbol = data.get("symbol", {})
            symbol_title = symbol.get("title", ticker)
            watchlist_count = symbol.get("watchlist_count", 0)

            # Get messages
            messages = data.get("messages", [])[:limit]

            if not messages:
                return f"No recent messages found for {ticker} on Stocktwits."

            # Count sentiment
            bullish = 0
            bearish = 0
            neutral = 0

            output = f"**Stocktwits: {symbol_title} (${ticker})**\n"
            output += f"Watchlist Count: {watchlist_count:,}\n\n"

            output += "**Recent Messages:**\n\n"

            for msg in messages:
                # Sentiment
                sentiment = msg.get("entities", {}).get("sentiment", {})
                sentiment_label = sentiment.get("basic") if sentiment else None

                if sentiment_label == "Bullish":
                    bullish += 1
                    emoji = "🟢"
                elif sentiment_label == "Bearish":
                    bearish += 1
                    emoji = "🔴"
                else:
                    neutral += 1
                    emoji = "⚪"

                # Message details
                user = msg.get("user", {}).get("username", "unknown")
                body = msg.get("body", "")
                created = msg.get("created_at", "")

                # Clean up body (truncate if long)
                if len(body) > 200:
                    body = body[:200] + "..."

                # Remove excessive whitespace
                body = " ".join(body.split())

                output += f"{emoji} **@{user}**: {body}\n"
                output += f"   _{created}_\n\n"

            # Sentiment summary
            total_with_sentiment = bullish + bearish
            if total_with_sentiment > 0:
                bullish_pct = (bullish / total_with_sentiment) * 100
                sentiment_summary = f"**Sentiment:** {bullish_pct:.0f}% Bullish ({bullish} 🟢 / {bearish} 🔴)"
            else:
                sentiment_summary = "**Sentiment:** No sentiment data available"

            output = output.replace("**Recent Messages:**", f"{sentiment_summary}\n\n**Recent Messages ({len(messages)}):**")

            return output

        except requests.exceptions.Timeout:
            logger.warning("Stocktwits API timed out")
            return None  # Trigger fallback
        except Exception as e:
            logger.error(f"Stocktwits error: {e}")
            return None  # Trigger fallback

    def _try_apify_scraper(self, ticker: str, limit: int) -> Optional[str]:
        """Fall back to Apify web scraper for Stocktwits."""
        if not APIFY_API_TOKEN:
            logger.warning("APIFY_API_TOKEN not configured for Stocktwits fallback")
            return None

        try:
            # Use Apify's Website Content Crawler to get Stocktwits page
            url = "https://api.apify.com/v2/acts/apify~website-content-crawler/run-sync-get-dataset-items"

            params = {
                "token": APIFY_API_TOKEN,
            }

            payload = {
                "startUrls": [{"url": f"https://stocktwits.com/symbol/{ticker}"}],
                "maxCrawlPages": 1,
                "crawlerType": "cheerio",
            }

            logger.info(f"Calling Apify scraper for Stocktwits {ticker}")
            response = requests.post(url, params=params, json=payload, timeout=60)

            if response.status_code != 200:
                logger.warning(f"Apify scraper returned HTTP {response.status_code}")
                return None

            data = response.json()

            if not data or len(data) == 0:
                logger.warning("Apify returned no data for Stocktwits")
                return None

            # Extract text content from the scraped page
            page_text = data[0].get("text", "")

            if not page_text or len(page_text) < 100:
                logger.warning("Apify returned insufficient content")
                return None

            # Parse sentiment from the page content
            return self._parse_stocktwits_page(ticker, page_text, limit)

        except requests.exceptions.Timeout:
            logger.warning("Apify scraper timed out")
            return None
        except Exception as e:
            logger.error(f"Apify Stocktwits scraper error: {e}")
            return None

    def _parse_stocktwits_page(self, ticker: str, page_text: str, limit: int) -> Optional[str]:
        """Parse Stocktwits page content for sentiment data."""
        try:
            # Simple keyword-based sentiment analysis on the scraped content
            text_lower = page_text.lower()

            bullish_keywords = ["bullish", "buy", "long", "calls", "moon", "rocket", "up", "green", "bull"]
            bearish_keywords = ["bearish", "sell", "short", "puts", "dump", "crash", "down", "red", "bear"]

            bullish_count = sum(1 for word in bullish_keywords if word in text_lower)
            bearish_count = sum(1 for word in bearish_keywords if word in text_lower)

            total = bullish_count + bearish_count
            if total > 0:
                bullish_pct = (bullish_count / total) * 100
                if bullish_pct > 60:
                    sentiment_label = "Bullish"
                    emoji = "🟢"
                elif bullish_pct < 40:
                    sentiment_label = "Bearish"
                    emoji = "🔴"
                else:
                    sentiment_label = "Mixed"
                    emoji = "⚪"
                sentiment_summary = f"{emoji} **{sentiment_label}** ({bullish_pct:.0f}% bullish signals)"
            else:
                sentiment_summary = "⚪ **Neutral** (no clear sentiment signals)"

            # Extract a snippet of content (first ~500 chars of meaningful text)
            snippet = page_text[:500].strip()
            if len(page_text) > 500:
                snippet += "..."

            output = f"**Stocktwits: ${ticker}** (via web scraper)\n\n"
            output += f"**Sentiment:** {sentiment_summary}\n\n"
            output += f"**Page Content Preview:**\n{snippet}\n\n"
            output += "_Note: Data scraped from Stocktwits website. For real-time messages, check stocktwits.com directly._"

            return output

        except Exception as e:
            logger.error(f"Error parsing Stocktwits page: {e}")
            return None


class RedditSentimentTool(BaseTool):
    """Search Reddit for stock discussions."""

    @property
    def name(self) -> str:
        return "search_reddit_stocks"

    @property
    def description(self) -> str:
        return """Search Reddit for stock discussions and sentiment.

Searches popular investing subreddits:
- r/wallstreetbets (retail traders, meme stocks)
- r/stocks (general stock discussion)
- r/investing (long-term investing)
- r/options (options trading)

Use when users ask about:
- "What's Reddit saying about GME?"
- "Any wallstreetbets posts on NVDA?"
- "What do retail traders think about Tesla?"
"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Stock ticker or company name to search for"
                },
                "subreddit": {
                    "type": "string",
                    "enum": ["wallstreetbets", "stocks", "investing", "options", "all"],
                    "description": "Which subreddit to search. 'all' searches all investing subs. Default is 'all'"
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of posts to return (default 10, max 25)"
                }
            },
            "required": ["query"]
        }

    def execute(self, query: str, subreddit: str = "all", limit: int = 10) -> str:
        query = query.strip()
        limit = min(max(5, limit), 25)

        logger.info(f"Searching Reddit for '{query}' in r/{subreddit}")

        # Map subreddit choice
        if subreddit == "all":
            subreddit_param = "wallstreetbets+stocks+investing+options"
        else:
            subreddit_param = subreddit

        try:
            # Reddit JSON API (no auth required for public data)
            url = f"https://www.reddit.com/r/{subreddit_param}/search.json"
            params = {
                "q": query,
                "restrict_sr": "on",
                "sort": "relevance",
                "t": "week",  # Last week
                "limit": limit
            }
            headers = {
                "User-Agent": "BigClawBot/1.0"
            }

            response = requests.get(url, params=params, headers=headers, timeout=10)

            if response.status_code != 200:
                return f"Error searching Reddit: HTTP {response.status_code}"

            data = response.json()
            posts = data.get("data", {}).get("children", [])

            if not posts:
                return f"No recent Reddit posts found for '{query}' in the last week."

            output = f"**Reddit Search: '{query}'**\n"
            output += f"Subreddit(s): r/{subreddit_param.replace('+', ', r/')}\n"
            output += f"Found {len(posts)} posts from the last week\n\n"

            for i, post in enumerate(posts, 1):
                post_data = post.get("data", {})

                title = post_data.get("title", "No title")
                author = post_data.get("author", "deleted")
                sub = post_data.get("subreddit", "unknown")
                score = post_data.get("score", 0)
                num_comments = post_data.get("num_comments", 0)
                url = f"https://reddit.com{post_data.get('permalink', '')}"
                created_utc = post_data.get("created_utc", 0)

                # Format date
                if created_utc:
                    created = datetime.fromtimestamp(created_utc).strftime("%Y-%m-%d")
                else:
                    created = "unknown"

                # Truncate long titles
                if len(title) > 150:
                    title = title[:150] + "..."

                # Score indicator
                if score > 1000:
                    score_display = f"🔥 {score:,}"
                elif score > 100:
                    score_display = f"⬆️ {score:,}"
                else:
                    score_display = f"{score:,}"

                output += f"**{i}. {title}**\n"
                output += f"   r/{sub} | {score_display} points | {num_comments} comments | {created}\n"
                output += f"   u/{author} | {url}\n\n"

            return output

        except requests.exceptions.Timeout:
            return "Reddit request timed out. Try again."
        except Exception as e:
            logger.error(f"Reddit search error: {e}")
            return f"Error searching Reddit: {str(e)}"


class WallStreetBetsTrendingTool(BaseTool):
    """Get trending tickers from WallStreetBets."""

    @property
    def name(self) -> str:
        return "get_wsb_trending"

    @property
    def description(self) -> str:
        return """Get currently trending/hot posts from r/wallstreetbets.

WallStreetBets (WSB) is known for:
- Meme stocks (GME, AMC, etc.)
- YOLO trades and options plays
- Retail investor sentiment

Use when users ask about:
- "What's hot on WSB?"
- "What are retail traders buying?"
- "Any meme stocks trending?"
"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of posts to return (default 10, max 25)"
                }
            },
            "required": []
        }

    def execute(self, limit: int = 10) -> str:
        limit = min(max(5, limit), 25)

        logger.info(f"Fetching trending from r/wallstreetbets")

        try:
            # Get hot posts from WSB
            url = "https://www.reddit.com/r/wallstreetbets/hot.json"
            params = {"limit": limit + 2}  # Extra to skip stickied
            headers = {"User-Agent": "BigClawBot/1.0"}

            response = requests.get(url, params=params, headers=headers, timeout=10)

            if response.status_code != 200:
                return f"Error fetching WSB: HTTP {response.status_code}"

            data = response.json()
            posts = data.get("data", {}).get("children", [])

            # Filter out stickied posts
            posts = [p for p in posts if not p.get("data", {}).get("stickied", False)][:limit]

            if not posts:
                return "No posts found on r/wallstreetbets."

            # Extract ticker mentions
            ticker_pattern = r'\$([A-Z]{1,5})\b|\b([A-Z]{2,5})\b'
            ticker_counts = {}

            output = "**🚀 r/wallstreetbets - Hot Posts**\n\n"

            for i, post in enumerate(posts, 1):
                post_data = post.get("data", {})

                title = post_data.get("title", "No title")
                score = post_data.get("score", 0)
                num_comments = post_data.get("num_comments", 0)
                flair = post_data.get("link_flair_text", "")
                url = f"https://reddit.com{post_data.get('permalink', '')}"

                # Find ticker mentions in title
                matches = re.findall(ticker_pattern, title)
                tickers_found = []
                for match in matches:
                    ticker = match[0] or match[1]
                    if ticker and len(ticker) >= 2 and ticker not in ["THE", "AND", "FOR", "ARE", "NOT", "YOU", "ALL", "CAN", "HAD", "HER", "WAS", "ONE", "OUR", "OUT", "HAS", "HIS", "HOW", "MAN", "NEW", "NOW", "OLD", "SEE", "WAY", "WHO", "BOY", "DID", "GET", "HIM", "LET", "PUT", "SAY", "SHE", "TOO", "USE"]:
                        tickers_found.append(ticker)
                        ticker_counts[ticker] = ticker_counts.get(ticker, 0) + 1

                # Score indicator
                if score > 5000:
                    score_display = f"🔥🔥 {score:,}"
                elif score > 1000:
                    score_display = f"🔥 {score:,}"
                else:
                    score_display = f"⬆️ {score:,}"

                # Truncate title
                if len(title) > 120:
                    title = title[:120] + "..."

                flair_display = f"[{flair}] " if flair else ""

                output += f"**{i}. {flair_display}{title}**\n"
                output += f"   {score_display} | {num_comments} comments"
                if tickers_found:
                    output += f" | Tickers: {', '.join(set(tickers_found))}"
                output += f"\n   {url}\n\n"

            # Add trending tickers summary
            if ticker_counts:
                sorted_tickers = sorted(ticker_counts.items(), key=lambda x: x[1], reverse=True)[:5]
                trending = ", ".join([f"${t[0]} ({t[1]})" for t in sorted_tickers])
                output = output.replace("**🚀 r/wallstreetbets - Hot Posts**\n\n",
                                       f"**🚀 r/wallstreetbets - Hot Posts**\n\n**Trending Tickers:** {trending}\n\n")

            return output

        except requests.exceptions.Timeout:
            return "Reddit request timed out. Try again."
        except Exception as e:
            logger.error(f"WSB error: {e}")
            return f"Error fetching WSB data: {str(e)}"


class XSentimentTool(BaseTool):
    """Get sentiment from X/Twitter using Apify scraper."""

    @property
    def name(self) -> str:
        return "get_x_sentiment"

    @property
    def description(self) -> str:
        return """Get real-time sentiment from X (Twitter) for a stock or topic.

Searches X/Twitter for recent posts about a stock ticker or company.
Returns:
- Recent tweets mentioning the stock
- Engagement metrics (likes, retweets, replies)
- Influential accounts discussing the stock

Use when users ask about:
- "What's Twitter saying about TSLA?"
- "X sentiment on Apple?"
- "What are people tweeting about NVDA?"
- "Social media buzz on GameStop?"

Note: Uses Apify API for scraping (may take 15-30 seconds).
"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query - use $TICKER for stocks (e.g., '$AAPL', '$TSLA') or company name"
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of tweets to return (default 15, max 50)"
                }
            },
            "required": ["query"]
        }

    def execute(self, query: str, limit: int = 15) -> str:
        if not X_BEARER_TOKEN:
            return "X/Twitter sentiment unavailable: X_BEARER_TOKEN not configured."

        limit = min(max(10, limit), 100)  # X API allows 10-100
        query = query.strip()

        # If it looks like a ticker without $, add it
        if query.upper() == query and len(query) <= 5 and not query.startswith("$"):
            query = f"${query}"

        logger.info(f"Fetching X sentiment for '{query}' via official API")

        try:
            # X API v2 Recent Search endpoint
            url = "https://api.twitter.com/2/tweets/search/recent"

            headers = {
                "Authorization": f"Bearer {X_BEARER_TOKEN}",
            }

            # Build query - exclude retweets for cleaner results
            search_query = f"{query} -is:retweet lang:en"

            params = {
                "query": search_query,
                "max_results": limit,
                "tweet.fields": "created_at,public_metrics,author_id",
                "expansions": "author_id",
                "user.fields": "username,name,public_metrics"
            }

            response = requests.get(url, headers=headers, params=params, timeout=15)

            if response.status_code == 401:
                logger.error("X API authentication failed")
                return "X/Twitter API authentication failed. Check your Bearer Token."

            if response.status_code == 429:
                logger.warning("X API rate limit hit")
                return "X/Twitter API rate limit reached. Try again later or use Stocktwits/Reddit for sentiment."

            if response.status_code != 200:
                logger.error(f"X API error: {response.status_code} - {response.text}")
                return f"X/Twitter API error: HTTP {response.status_code}"

            data = response.json()

            tweets = data.get("data", [])
            users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}

            logger.info(f"Received {len(tweets)} tweets from X API")

            if not tweets:
                return f"No recent tweets found for '{query}' in the last 7 days."

            # Enrich tweets with user data
            enriched_tweets = []
            for tweet in tweets:
                author_id = tweet.get("author_id")
                user = users.get(author_id, {})
                enriched_tweets.append({
                    "text": tweet.get("text", ""),
                    "created_at": tweet.get("created_at", ""),
                    "metrics": tweet.get("public_metrics", {}),
                    "username": user.get("username", "unknown"),
                    "name": user.get("name", ""),
                    "followers": user.get("public_metrics", {}).get("followers_count", 0)
                })

            return self._format_results_v2(query, enriched_tweets)

        except requests.exceptions.Timeout:
            return "X search request timed out. Try again."
        except Exception as e:
            logger.error(f"X sentiment error: {e}")
            return f"Error fetching X sentiment: {str(e)}"

    def _format_results_v2(self, query: str, tweets: list) -> str:
        """Format tweet results from official API into readable output."""

        output = f"**𝕏 (Twitter) Sentiment: {query}**\n"
        output += f"Found {len(tweets)} recent tweets\n\n"

        # Sentiment tracking
        bullish_keywords = ["buy", "bullish", "moon", "rocket", "calls", "long", "undervalued", "breakout", "pump", "up", "green", "bull"]
        bearish_keywords = ["sell", "bearish", "dump", "puts", "short", "overvalued", "crash", "drop", "down", "red", "bear"]

        bullish_count = 0
        bearish_count = 0
        total_likes = 0
        total_retweets = 0
        total_replies = 0

        output += "**Recent Tweets:**\n\n"

        for i, tweet in enumerate(tweets[:15], 1):  # Show max 15 in output
            text = tweet.get("text", "")
            username = tweet.get("username", "unknown")
            name = tweet.get("name", username)
            followers = tweet.get("followers", 0)
            created = tweet.get("created_at", "")

            metrics = tweet.get("metrics", {})
            likes = metrics.get("like_count", 0)
            retweets = metrics.get("retweet_count", 0)
            replies = metrics.get("reply_count", 0)

            # Track engagement
            total_likes += likes
            total_retweets += retweets
            total_replies += replies

            # Simple sentiment detection
            text_lower = text.lower()
            if any(word in text_lower for word in bullish_keywords):
                bullish_count += 1
                sentiment_emoji = "🟢"
            elif any(word in text_lower for word in bearish_keywords):
                bearish_count += 1
                sentiment_emoji = "🔴"
            else:
                sentiment_emoji = "⚪"

            # Truncate long tweets
            if len(text) > 250:
                text = text[:250] + "..."

            # Clean up text (remove excessive newlines)
            text = " ".join(text.split())

            # Influence indicator
            if followers > 100000:
                influence = "🔷"  # High influence
            elif followers > 10000:
                influence = "🔹"  # Medium influence
            else:
                influence = ""

            output += f"{sentiment_emoji} **@{username}** {influence}\n"
            output += f"{text}\n"
            output += f"❤️ {likes:,} | 🔄 {retweets:,} | 💬 {replies:,}"
            if created:
                try:
                    dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    output += f" | {dt.strftime('%m/%d %H:%M')}"
                except:
                    pass
            output += "\n\n"

        # Add summary at the top
        total_sentiment = bullish_count + bearish_count
        if total_sentiment > 0:
            bullish_pct = (bullish_count / total_sentiment) * 100
            if bullish_pct > 60:
                sentiment_label = "🟢 Bullish"
            elif bullish_pct < 40:
                sentiment_label = "🔴 Bearish"
            else:
                sentiment_label = "⚪ Mixed"
            sentiment_summary = f"**Sentiment:** {sentiment_label} ({bullish_pct:.0f}% bullish)"
        else:
            sentiment_summary = "**Sentiment:** Neutral/Unclear"

        engagement_summary = f"**Engagement:** {total_likes:,} likes | {total_retweets:,} retweets | {total_replies:,} replies"

        output = output.replace(
            f"Found {len(tweets)} recent tweets\n\n",
            f"Found {len(tweets)} recent tweets\n\n{sentiment_summary}\n{engagement_summary}\n\n"
        )

        return output

    def _format_results(self, query: str, tweets: list) -> str:
        """Format tweet results into readable output."""

        output = f"**𝕏 (Twitter) Sentiment: {query}**\n"
        output += f"Found {len(tweets)} recent tweets\n\n"

        # Sentiment tracking
        bullish_keywords = ["buy", "bullish", "moon", "rocket", "calls", "long", "undervalued", "breakout", "pump"]
        bearish_keywords = ["sell", "bearish", "dump", "puts", "short", "overvalued", "crash", "drop"]

        bullish_count = 0
        bearish_count = 0
        total_likes = 0
        total_retweets = 0
        total_replies = 0

        output += "**Recent Tweets:**\n\n"

        for i, tweet in enumerate(tweets[:15], 1):  # Show max 15 in output
            # Extract fields (field names vary by actor version)
            text = tweet.get("text") or tweet.get("full_text") or tweet.get("tweet", "")
            author = tweet.get("author", {})
            username = author.get("userName") or tweet.get("user", {}).get("screen_name") or "unknown"
            display_name = author.get("name") or tweet.get("user", {}).get("name") or username

            likes = tweet.get("likeCount") or tweet.get("favorite_count") or 0
            retweets = tweet.get("retweetCount") or tweet.get("retweet_count") or 0
            replies = tweet.get("replyCount") or 0

            followers = author.get("followers") or tweet.get("user", {}).get("followers_count") or 0

            created = tweet.get("createdAt") or tweet.get("created_at") or ""

            # Track engagement
            total_likes += likes
            total_retweets += retweets
            total_replies += replies

            # Simple sentiment detection
            text_lower = text.lower()
            if any(word in text_lower for word in bullish_keywords):
                bullish_count += 1
                sentiment_emoji = "🟢"
            elif any(word in text_lower for word in bearish_keywords):
                bearish_count += 1
                sentiment_emoji = "🔴"
            else:
                sentiment_emoji = "⚪"

            # Truncate long tweets
            if len(text) > 250:
                text = text[:250] + "..."

            # Clean up text (remove excessive newlines)
            text = " ".join(text.split())

            # Influence indicator
            if followers > 100000:
                influence = "🔷"  # High influence
            elif followers > 10000:
                influence = "🔹"  # Medium influence
            else:
                influence = ""

            output += f"{sentiment_emoji} **@{username}** {influence}\n"
            output += f"{text}\n"
            output += f"❤️ {likes:,} | 🔄 {retweets:,} | 💬 {replies:,}"
            if created:
                # Try to parse and format date
                try:
                    if "T" in str(created):
                        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                        output += f" | {dt.strftime('%m/%d %H:%M')}"
                except:
                    pass
            output += "\n\n"

        # Add summary at the top
        total_sentiment = bullish_count + bearish_count
        if total_sentiment > 0:
            bullish_pct = (bullish_count / total_sentiment) * 100
            if bullish_pct > 60:
                sentiment_label = "🟢 Bullish"
            elif bullish_pct < 40:
                sentiment_label = "🔴 Bearish"
            else:
                sentiment_label = "⚪ Mixed"
            sentiment_summary = f"**Sentiment:** {sentiment_label} ({bullish_pct:.0f}% bullish)"
        else:
            sentiment_summary = "**Sentiment:** Neutral/Unclear"

        engagement_summary = f"**Engagement:** {total_likes:,} likes | {total_retweets:,} retweets | {total_replies:,} replies"

        output = output.replace(
            f"Found {len(tweets)} recent tweets\n\n",
            f"Found {len(tweets)} recent tweets\n\n{sentiment_summary}\n{engagement_summary}\n\n"
        )

        return output
