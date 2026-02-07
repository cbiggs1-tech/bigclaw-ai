"""News tools for BigClaw AI - Motley Fool and financial news."""

import logging
from datetime import datetime
from typing import Optional
from .base import BaseTool

logger = logging.getLogger(__name__)

# Motley Fool RSS feed URLs
MOTLEY_FOOL_FEEDS = {
    "main": "https://www.fool.com/feeds/index.aspx",
    "investing": "https://www.fool.com/feeds/investing-news.aspx",
    "retirement": "https://www.fool.com/feeds/retirement-news.aspx",
    "personal_finance": "https://www.fool.com/feeds/personal-finance-news.aspx",
}


class MotleyFoolNewsTool(BaseTool):
    """Fetch recent news articles from The Motley Fool."""

    @property
    def name(self) -> str:
        return "get_motley_fool_news"

    @property
    def description(self) -> str:
        return """Fetch recent investment news and analysis from The Motley Fool.

Use this tool when users ask about:
- Recent market news or trends
- Stock analysis and recommendations
- Investment insights and education
- What's happening in the market today

You can optionally filter by category (investing, retirement, personal_finance) or search for a specific ticker/keyword."""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["main", "investing", "retirement", "personal_finance"],
                    "description": "News category to fetch. Default is 'main' for general news."
                },
                "search_term": {
                    "type": "string",
                    "description": "Optional: Filter articles containing this term (e.g., a stock ticker like 'AAPL' or topic like 'dividend')"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of articles to return (default 5, max 10)"
                }
            },
            "required": []
        }

    def execute(
        self,
        category: str = "main",
        search_term: Optional[str] = None,
        limit: int = 5
    ) -> str:
        """Fetch news from Motley Fool RSS feeds."""
        try:
            import feedparser
        except ImportError:
            return "Error: feedparser not installed. Run: pip install feedparser"

        # Validate and get feed URL
        if category not in MOTLEY_FOOL_FEEDS:
            category = "main"

        feed_url = MOTLEY_FOOL_FEEDS[category]
        limit = min(max(1, limit), 10)  # Clamp between 1 and 10

        logger.info(f"Fetching Motley Fool {category} feed, search: {search_term}, limit: {limit}")

        try:
            feed = feedparser.parse(feed_url)

            if feed.bozo and not feed.entries:
                return f"Error fetching news: Could not parse feed from {feed_url}"

            articles = []
            for entry in feed.entries:
                title = entry.get("title", "No title")
                link = entry.get("link", "")
                summary = entry.get("summary", "")
                published = entry.get("published", "")

                # Clean up summary (remove HTML tags)
                if summary:
                    import re
                    summary = re.sub(r'<[^>]+>', '', summary)
                    summary = summary[:300] + "..." if len(summary) > 300 else summary

                # Filter by search term if provided
                if search_term:
                    search_lower = search_term.lower()
                    if (search_lower not in title.lower() and
                        search_lower not in summary.lower()):
                        continue

                articles.append({
                    "title": title,
                    "link": link,
                    "summary": summary,
                    "published": published
                })

                if len(articles) >= limit:
                    break

            if not articles:
                if search_term:
                    return f"No recent Motley Fool articles found matching '{search_term}'. Try a different search term or check the general news."
                return "No articles found in the feed."

            # Format output
            output = f"**Motley Fool News** ({category})\n"
            output += f"Retrieved {len(articles)} articles"
            if search_term:
                output += f" matching '{search_term}'"
            output += f"\n\n"

            for i, article in enumerate(articles, 1):
                output += f"**{i}. {article['title']}**\n"
                if article['published']:
                    output += f"   Published: {article['published']}\n"
                if article['summary']:
                    output += f"   {article['summary']}\n"
                output += f"   Link: {article['link']}\n\n"

            return output

        except Exception as e:
            logger.error(f"Error fetching Motley Fool news: {e}")
            return f"Error fetching news: {str(e)}"


class SearchFinancialNewsTool(BaseTool):
    """Search across multiple financial news RSS feeds."""

    @property
    def name(self) -> str:
        return "search_financial_news"

    @property
    def description(self) -> str:
        return """Search for financial news about a specific stock ticker or topic.

Use this when users ask about news for a specific company or ticker symbol.
This searches Motley Fool feeds for relevant articles."""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The stock ticker (e.g., 'AAPL', 'MSFT') or topic to search for"
                }
            },
            "required": ["query"]
        }

    def execute(self, query: str) -> str:
        """Search for news matching the query across feeds."""
        try:
            import feedparser
        except ImportError:
            return "Error: feedparser not installed. Run: pip install feedparser"

        logger.info(f"Searching financial news for: {query}")

        all_articles = []

        # Search across main feeds
        for category, url in MOTLEY_FOOL_FEEDS.items():
            try:
                feed = feedparser.parse(url)

                for entry in feed.entries:
                    title = entry.get("title", "")
                    summary = entry.get("summary", "")

                    # Check if query matches
                    query_lower = query.lower()
                    if (query_lower in title.lower() or
                        query_lower in summary.lower()):

                        # Clean summary
                        if summary:
                            import re
                            summary = re.sub(r'<[^>]+>', '', summary)
                            summary = summary[:250] + "..." if len(summary) > 250 else summary

                        all_articles.append({
                            "title": title,
                            "link": entry.get("link", ""),
                            "summary": summary,
                            "published": entry.get("published", ""),
                            "source": f"Motley Fool ({category})"
                        })
            except Exception as e:
                logger.warning(f"Error parsing {category} feed: {e}")
                continue

        # Remove duplicates by link
        seen_links = set()
        unique_articles = []
        for article in all_articles:
            if article["link"] not in seen_links:
                seen_links.add(article["link"])
                unique_articles.append(article)

        # Limit results
        unique_articles = unique_articles[:8]

        if not unique_articles:
            return f"No recent news found for '{query}'. This could mean:\n- The ticker/topic hasn't been in recent headlines\n- Try searching for the full company name instead of just the ticker\n- Check if the ticker symbol is correct"

        # Format output
        output = f"**Financial News Search: '{query}'**\n"
        output += f"Found {len(unique_articles)} relevant articles\n\n"

        for i, article in enumerate(unique_articles, 1):
            output += f"**{i}. {article['title']}**\n"
            output += f"   Source: {article['source']}\n"
            if article['published']:
                output += f"   Published: {article['published']}\n"
            if article['summary']:
                output += f"   {article['summary']}\n"
            output += f"   Link: {article['link']}\n\n"

        return output
