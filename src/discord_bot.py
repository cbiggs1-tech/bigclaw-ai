"""BigClaw AI Discord Bot - Discord integration.

A Discord bot powered by Claude with tool-use capabilities for
investment research and market analysis. Shares the same agent
and tools as the Slack bot.
"""

import os
import asyncio
import logging
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# Discord bot setup with intents
intents = discord.Intents.default()
intents.message_content = True  # Required to read message content

bot = commands.Bot(command_prefix="!", intents=intents)

BOT_NAME = "BigClaw AI"

# ────────────────────────────────────────────────
# Claude/Anthropic Integration with Tool Use
# ────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
anthropic_client = None
agent = None
memory = None

def init_agent():
    """Initialize the BigClaw agent (called after bot is ready)."""
    global anthropic_client, agent, memory

    if ANTHROPIC_API_KEY:
        try:
            import anthropic
            from agent import BigClawAgent
            from memory import get_memory

            anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            agent = BigClawAgent(anthropic_client)
            memory = get_memory()

            logger.info("BigClaw Agent initialized for Discord!")
            return True
        except ImportError as e:
            logger.error(f"Missing package: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize agent: {e}")
            return False
    else:
        logger.warning("ANTHROPIC_API_KEY not set. Bot will use echo mode.")
        return False


def get_response(user_message: str, conversation_id: str = None) -> str:
    """Get a response using the BigClaw agent with conversation memory.

    Args:
        user_message: The user's message
        conversation_id: Unique ID for this conversation (channel ID)

    Returns:
        The assistant's response
    """
    if not agent:
        return f"[Echo mode - no API key] You said: {user_message}"

    try:
        # Get conversation history if memory is available
        history = None
        if memory and conversation_id:
            history = memory.get_history(conversation_id)
            if history:
                logger.info(f"Loaded {len(history)} messages from conversation history")

        # Run the agent with history
        response = agent.run(user_message, conversation_history=history)

        # Store the exchange in memory
        if memory and conversation_id:
            memory.add_message(conversation_id, "user", user_message)

            # For image responses, store a description instead of the marker
            if response.startswith("__IMAGE__|||"):
                parts = response.split("|||")
                if len(parts) >= 3:
                    chart_title = parts[2]
                    memory.add_message(conversation_id, "assistant",
                                      f"I generated a chart: {chart_title}")
            else:
                memory.add_message(conversation_id, "assistant", response)

        return response
    except Exception as e:
        logger.error(f"Agent error: {e}")
        return f"Sorry, I encountered an error: {str(e)}"


async def send_response(message: discord.Message, reply: str):
    """Send a response, handling both text and image uploads."""

    if reply.startswith("__IMAGE__|||"):
        # Parse image response: __IMAGE__|||filepath|||title
        parts = reply.split("|||")
        if len(parts) >= 3:
            filepath = parts[1]
            title = parts[2]

            try:
                # Upload file to Discord
                file = discord.File(filepath, filename=f"{title.replace(' ', '_')}.png")
                await message.channel.send(
                    content=f"Here's the chart you requested:",
                    file=file
                )
                logger.info(f"Image uploaded successfully: {title}")

                # Clean up temp file
                if os.path.exists(filepath):
                    os.remove(filepath)
                    logger.info(f"Cleaned up temp file: {filepath}")

            except Exception as e:
                logger.error(f"Failed to upload image: {e}")
                await message.channel.send(f"I generated the chart but couldn't upload it: {str(e)}")
        else:
            await message.channel.send("Error processing chart response.")
    else:
        # Regular text response - split if too long for Discord (2000 char limit)
        if len(reply) > 2000:
            # Split into chunks
            chunks = [reply[i:i+1990] for i in range(0, len(reply), 1990)]
            for chunk in chunks:
                await message.channel.send(chunk)
        else:
            await message.channel.send(reply)


# ────────────────────────────────────────────────
# Bot Events
# ────────────────────────────────────────────────

@bot.event
async def on_ready():
    """Called when bot is connected and ready."""
    logger.info(f"{BOT_NAME} connected to Discord as {bot.user}")
    init_agent()

    # Set bot status
    activity = discord.Activity(
        type=discord.ActivityType.watching,
        name="the markets 📊"
    )
    await bot.change_presence(activity=activity)

    # Check if webhook is configured for synchronized reports
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if webhook_url:
        logger.info("Discord webhook configured - reports will sync from scheduler")
    else:
        logger.info("No Discord webhook - use !setwebhook to enable synchronized reports")

    logger.info(f"Discord bot ready! Logged in as {bot.user.name}")
    logger.info(f"Agent: {'Enabled' if agent else 'Disabled (echo mode)'}")
    logger.info(f"Memory: {'Enabled' if memory else 'Disabled'}")


@bot.event
async def on_message(message: discord.Message):
    """Handle incoming messages."""

    # Ignore messages from the bot itself
    if message.author == bot.user:
        return

    # Check if bot was mentioned or if it's a DM
    is_mentioned = bot.user in message.mentions
    is_dm = isinstance(message.channel, discord.DMChannel)

    if not is_mentioned and not is_dm:
        # Process commands even if not mentioned
        await bot.process_commands(message)
        return

    # Get the message content, removing the bot mention
    content = message.content
    for mention in message.mentions:
        content = content.replace(f'<@{mention.id}>', '').replace(f'<@!{mention.id}>', '')
    content = content.strip()

    if not content:
        await message.channel.send("Hey! How can I help you with investment research today? 🦀")
        return

    # Handle special commands
    if content.lower() in ["clear", "reset", "forget", "new conversation"]:
        if memory:
            memory.clear_conversation(str(message.channel.id))
            await message.channel.send("Conversation cleared! Starting fresh. 🦀")
        else:
            await message.channel.send("Memory not available.")
        return

    logger.info(f"Discord message from {message.author}: {content}")

    # Show typing indicator while processing
    async with message.channel.typing():
        # Use channel ID as conversation ID
        reply = get_response(content, conversation_id=str(message.channel.id))

    await send_response(message, reply)

    # Process any commands
    await bot.process_commands(message)


# ────────────────────────────────────────────────
# Slash Commands (optional, for future use)
# ────────────────────────────────────────────────

@bot.command(name="claw", help="Ask BigClaw a question")
async def claw_command(ctx, *, question: str = None):
    """!claw <question> - Ask BigClaw a question."""
    if not question:
        await ctx.send("Usage: `!claw <your question>`\nExample: `!claw What's the price of AAPL?`")
        return

    async with ctx.typing():
        reply = get_response(question, conversation_id=str(ctx.channel.id))

    await send_response(ctx.message, reply)


@bot.command(name="analyze", help="Analyze a stock with a strategy")
async def analyze_command(ctx, ticker: str = None, *, strategy: str = None):
    """!analyze <ticker> <strategy> - Analyze a stock."""
    if not ticker:
        await ctx.send("Usage: `!analyze AAPL buffett`\nStrategies: buffett, lynch, dalio, graham, wood")
        return

    strategy = strategy or "buffett"
    question = f"analyze {ticker.upper()} with {strategy}"

    async with ctx.typing():
        reply = get_response(question, conversation_id=str(ctx.channel.id))

    await send_response(ctx.message, reply)


@bot.command(name="quote", help="Get a stock quote")
async def quote_command(ctx, ticker: str = None):
    """!quote <ticker> - Get a quick stock quote."""
    if not ticker:
        await ctx.send("Usage: `!quote AAPL`")
        return

    async with ctx.typing():
        reply = get_response(f"What's the current price of {ticker.upper()}?",
                            conversation_id=str(ctx.channel.id))

    await send_response(ctx.message, reply)


@bot.command(name="status", help="Check BigClaw status")
async def status_command(ctx):
    """!status - Check BigClaw bot status."""
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")

    status_msg = f"""🦀 **BigClaw Status**

**Agent:** {'✅ Enabled' if agent else '❌ Disabled'}
**Memory:** {'✅ Enabled' if memory else '❌ Disabled'}
**Discord Reports:** {'✅ Webhook configured' if webhook_url else '❌ Not configured'}

_To enable synchronized reports, create a webhook in your channel and add DISCORD_WEBHOOK_URL to .env_
"""
    await ctx.send(status_msg)


# ────────────────────────────────────────────────
# Run the Discord bot
# ────────────────────────────────────────────────

def run_discord_bot():
    """Run the Discord bot (blocking)."""
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        logger.error("DISCORD_BOT_TOKEN not set in environment")
        return

    logger.info("Starting Discord bot...")
    bot.run(token)


if __name__ == "__main__":
    run_discord_bot()
