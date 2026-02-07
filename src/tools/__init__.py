"""Tool registry for BigClaw AI.

This module provides:
- TOOLS: List of all available tool instances
- TOOL_MAP: Name -> tool instance mapping for execution
- get_claude_tools(): Returns tools in Claude's expected format
"""

from .base import BaseTool
from .demo import EchoTool, GetCurrentTimeTool
from .news import MotleyFoolNewsTool, SearchFinancialNewsTool
from .market import GetStockQuoteTool, GetStockDetailsTool, GetYahooNewsTool
from .charts import StockChartTool, CompareStocksTool
from .technical import (
    MACDChartTool,
    RSIChartTool,
    BollingerBandsChartTool,
    MonteCarloChartTool,
    MovingAveragesChartTool,
)
from .social import (
    StocktwitsSentimentTool,
    RedditSentimentTool,
    WallStreetBetsTrendingTool,
    XSentimentTool,
)
from .predictions import (
    PolymarketSearchTool,
    PolymarketTrendingTool,
)
from .portfolio import (
    CreatePortfolioTool,
    ListPortfoliosTool,
    ViewPortfolioTool,
    BuyStockTool,
    SellStockTool,
    GetTransactionsTool,
    DeletePortfolioTool,
    SetReportChannelTool,
    ActivateAutonomousTradingTool,
    RunAnalysisNowTool,
    ComparePortfoliosTool,
)
from .orders import (
    SetStopLossTool,
    SetLimitBuyTool,
    SetLimitSellTool,
    ViewPendingOrdersTool,
    CancelOrderTool,
)

# Register all available tools here
TOOLS: list[BaseTool] = [
    EchoTool(),
    GetCurrentTimeTool(),
    MotleyFoolNewsTool(),
    SearchFinancialNewsTool(),
    GetStockQuoteTool(),
    GetStockDetailsTool(),
    GetYahooNewsTool(),
    StockChartTool(),
    CompareStocksTool(),
    # Technical Analysis
    MACDChartTool(),
    RSIChartTool(),
    BollingerBandsChartTool(),
    MonteCarloChartTool(),
    MovingAveragesChartTool(),
    # Social Sentiment
    StocktwitsSentimentTool(),
    RedditSentimentTool(),
    WallStreetBetsTrendingTool(),
    XSentimentTool(),
    # Prediction Markets
    PolymarketSearchTool(),
    PolymarketTrendingTool(),
    # Portfolio Management
    CreatePortfolioTool(),
    ListPortfoliosTool(),
    ViewPortfolioTool(),
    BuyStockTool(),
    SellStockTool(),
    GetTransactionsTool(),
    DeletePortfolioTool(),
    SetReportChannelTool(),
    ActivateAutonomousTradingTool(),
    RunAnalysisNowTool(),
    ComparePortfoliosTool(),
    # Order Management
    SetStopLossTool(),
    SetLimitBuyTool(),
    SetLimitSellTool(),
    ViewPendingOrdersTool(),
    CancelOrderTool(),
]

# Build name -> tool mapping for execution
TOOL_MAP: dict[str, BaseTool] = {tool.name: tool for tool in TOOLS}


def get_claude_tools() -> list[dict]:
    """Get all tools in Claude's expected format."""
    return [tool.to_claude_tool() for tool in TOOLS]


def execute_tool(name: str, params: dict) -> str:
    """Execute a tool by name with the given parameters.

    Args:
        name: The tool name
        params: Dictionary of parameters to pass to the tool

    Returns:
        The tool's result as a string

    Raises:
        ValueError: If tool name is not found
    """
    if name not in TOOL_MAP:
        raise ValueError(f"Unknown tool: {name}")

    tool = TOOL_MAP[name]
    result = tool.execute(**params)

    # Ensure result is a string
    if not isinstance(result, str):
        result = str(result)

    return result
