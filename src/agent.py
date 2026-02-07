"""BigClaw AI Agent - Tool-using Claude integration.

This module handles the Claude conversation loop with tool use:
1. Send user message to Claude with available tools
2. If Claude wants to use a tool, execute it and send results back
3. Repeat until Claude provides a final text response
"""

import os
import logging
from typing import Optional

from prompts import get_system_prompt
from tools import get_claude_tools, execute_tool, TOOL_MAP
from tools.strategy_analyzer import (
    detect_strategy_request,
    get_strategy_name,
    get_strategy_analysis_prompt,
)

logger = logging.getLogger(__name__)

# Maximum tool use iterations to prevent infinite loops
# Scheduler morning analysis needs many iterations for multiple portfolios
MAX_TOOL_ITERATIONS = 25

# Model configuration
DEFAULT_MODEL = "claude-sonnet-4-20250514"
OPUS_MODEL = "claude-opus-4-6"  # Updated to Opus 4.6 (released Feb 5, 2026)


class BigClawAgent:
    """Agent that handles Claude interactions with tool use."""

    def __init__(self, anthropic_client):
        """Initialize the agent with an Anthropic client.

        Args:
            anthropic_client: An initialized anthropic.Anthropic client
        """
        self.client = anthropic_client
        self.model = os.environ.get("CLAUDE_MODEL", DEFAULT_MODEL)
        self._pending_images = []  # Track images to be uploaded

    def _run_strategy_analysis(self, ticker: str, strategy: str) -> str:
        """Run deep strategy analysis using Opus 4.5.

        This gathers relevant data and uses Claude Opus for sophisticated
        investment analysis based on the specified strategy.

        Args:
            ticker: Stock ticker symbol
            strategy: Strategy key (buffett, lynch, dalio, graham, wood)

        Returns:
            Detailed analysis and recommendation
        """
        logger.info(f"Running {strategy} strategy analysis for {ticker} using Opus 4.5")

        # Gather all relevant data using existing tools
        data_sections = []

        # Get stock quote
        try:
            quote_tool = TOOL_MAP.get("get_stock_quote")
            if quote_tool:
                quote_data = quote_tool.execute(ticker=ticker)
                data_sections.append(f"## Current Quote\n{quote_data}")
        except Exception as e:
            logger.error(f"Error getting quote: {e}")

        # Get detailed fundamentals
        try:
            details_tool = TOOL_MAP.get("get_stock_details")
            if details_tool:
                details_data = details_tool.execute(ticker=ticker)
                data_sections.append(f"## Company Details & Fundamentals\n{details_data}")
        except Exception as e:
            logger.error(f"Error getting details: {e}")

        # Get recent news
        try:
            news_tool = TOOL_MAP.get("get_yahoo_news")
            if news_tool:
                news_data = news_tool.execute(ticker=ticker, limit=5)
                data_sections.append(f"## Recent News\n{news_data}")
        except Exception as e:
            logger.error(f"Error getting news: {e}")

        # Combine all data
        combined_data = "\n\n".join(data_sections)

        # Get the strategy-specific prompt
        strategy_prompt = get_strategy_analysis_prompt(ticker, strategy)

        # Build the full message
        user_message = f"""Here is the current data for {ticker}:

{combined_data}

---

{strategy_prompt}"""

        # Make the Opus API call
        try:
            response = self.client.messages.create(
                model=OPUS_MODEL,
                max_tokens=4096,
                system=f"""You are BigClaw AI, an expert investment analyst. You are performing a deep-dive analysis
using a specific investment strategy framework. Be thorough, analytical, and provide actionable insights.

Always conclude with a clear VERDICT (BUY/HOLD/PASS), CONFIDENCE level, KEY FACTORS, and RISKS.

Remember to include the disclaimer that this is for educational purposes only, not financial advice.""",
                messages=[{"role": "user", "content": user_message}]
            )

            # Extract text response
            for block in response.content:
                if block.type == "text":
                    strategy_name = get_strategy_name(strategy)
                    header = f"**📊 {strategy_name} Analysis: {ticker}**\n\n"
                    footer = "\n\n_Analysis powered by Claude Opus 4.5_"
                    return header + block.text + footer

            return "Error: No response from analysis."

        except Exception as e:
            logger.error(f"Error in Opus strategy analysis: {e}")
            return f"Error performing strategy analysis: {str(e)}"

    def run(self, user_message: str, conversation_history: list = None) -> str:
        """Run the agent with a user message.

        This handles the full tool-use loop:
        - Send message to Claude with tools
        - Execute any tool calls
        - Continue until Claude gives a final response

        Args:
            user_message: The user's input message
            conversation_history: Optional list of previous messages for context

        Returns:
            Claude's final text response (or image marker if chart was generated)
        """
        # Check if this is a strategy analysis request (uses Opus 4.5)
        strategy_request = detect_strategy_request(user_message)
        if strategy_request:
            ticker, strategy = strategy_request
            logger.info(f"Detected strategy analysis request: {ticker} with {strategy}")
            return self._run_strategy_analysis(ticker, strategy)

        # Start with conversation history if provided
        if conversation_history:
            messages = conversation_history.copy()
            messages.append({"role": "user", "content": user_message})
            logger.info(f"Using conversation history with {len(conversation_history)} previous messages")
        else:
            messages = [{"role": "user", "content": user_message}]

        tools = get_claude_tools()
        self._pending_images = []  # Reset for each run

        for iteration in range(MAX_TOOL_ITERATIONS):
            logger.info(f"Agent iteration {iteration + 1}")

            # Call Claude
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=get_system_prompt(),
                tools=tools,
                messages=messages
            )

            logger.info(f"Claude stop_reason: {response.stop_reason}")

            # Check if Claude wants to use tools
            if response.stop_reason == "tool_use":
                # Process all tool calls in this response
                tool_results = self._process_tool_calls(response)

                # Add assistant response and tool results to messages
                messages.append({
                    "role": "assistant",
                    "content": response.content
                })
                messages.append({
                    "role": "user",
                    "content": tool_results
                })

            else:
                # Claude is done - extract text response
                text_response = self._extract_text_response(response)

                # If we have pending images, return the image first
                # The bot will upload the image, then we lose Claude's text
                # So we need to return image marker - bot handles upload
                if self._pending_images:
                    # Return the first image (most recent chart)
                    # The image marker format: __IMAGE__:filepath:title
                    return self._pending_images[-1]

                return text_response

        # If we hit max iterations, return what we have
        logger.warning("Hit max tool iterations")
        return "I apologize, but I ran into an issue processing your request. Please try rephrasing your question."

    def _process_tool_calls(self, response) -> list:
        """Process tool calls from Claude's response.

        Args:
            response: Claude's API response

        Returns:
            List of tool_result content blocks
        """
        tool_results = []

        for block in response.content:
            if block.type == "tool_use":
                tool_name = block.name
                tool_input = block.input
                tool_use_id = block.id

                logger.info(f"Executing tool: {tool_name} with input: {tool_input}")

                try:
                    result = execute_tool(tool_name, tool_input)
                    logger.info(f"Tool result: {result[:200]}..." if len(result) > 200 else f"Tool result: {result}")

                    # Check if this is an image result
                    if result.startswith("__IMAGE__|||"):
                        # Store the image for later upload
                        self._pending_images.append(result)
                        # Tell Claude the chart was generated successfully
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": "Chart generated successfully and will be displayed to the user."
                        })
                    else:
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": result
                        })

                except Exception as e:
                    logger.error(f"Tool execution error: {e}")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": f"Error executing tool: {str(e)}",
                        "is_error": True
                    })

        return tool_results

    def _extract_text_response(self, response) -> str:
        """Extract the text response from Claude's response.

        Args:
            response: Claude's API response

        Returns:
            The text content from the response
        """
        for block in response.content:
            if block.type == "text":
                return block.text

        return "I processed your request but have no text response."


# Convenience function for simple usage
def run_agent(anthropic_client, user_message: str) -> str:
    """Run the BigClaw agent with a user message.

    Args:
        anthropic_client: An initialized anthropic.Anthropic client
        user_message: The user's input message

    Returns:
        Claude's final text response
    """
    agent = BigClawAgent(anthropic_client)
    return agent.run(user_message)
