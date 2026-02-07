"""BigClaw AI Slack Bot - Main entry point.

A Slack bot powered by Claude with tool-use capabilities for
investment research and market analysis.
"""

import os
import re
import logging
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

print("Script started - loading .env...")

load_dotenv()
print("dotenv loaded")

# Check required environment variables
required_vars = ["SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "SLACK_SIGNING_SECRET"]
missing = [v for v in required_vars if not os.environ.get(v)]
if missing:
    print(f"ERROR: Missing environment variables: {', '.join(missing)}")
    print("Please check your .env file and add them.")
    exit(1)

print("All required env vars found. Initializing Slack app...")

app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET")
)

BOT_NAME = "BigClaw AI"

# ────────────────────────────────────────────────
# Claude/Anthropic Integration with Tool Use
# ────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
anthropic_client = None
agent = None

if ANTHROPIC_API_KEY:
    try:
        import anthropic
        from agent import BigClawAgent
        from memory import get_memory
        from scheduler import init_scheduler

        anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        agent = BigClawAgent(anthropic_client)
        memory = get_memory()

        # Initialize trading scheduler (will be started later)
        trading_scheduler = init_scheduler(anthropic_client, app)

        print("BigClaw Agent initialized with tool support and conversation memory!")
    except ImportError as e:
        print(f"WARNING: Missing package. Run: pip install anthropic")
        print(f"Details: {e}")
        memory = None
        trading_scheduler = None
    except Exception as e:
        print(f"WARNING: Failed to initialize agent: {e}")
        memory = None
        trading_scheduler = None
else:
    print("NOTE: ANTHROPIC_API_KEY not set. Bot will use echo mode.")
    memory = None
    trading_scheduler = None


def get_response(user_message: str, conversation_id: str = None) -> str:
    """Get a response using the BigClaw agent with conversation memory.

    Args:
        user_message: The user's message
        conversation_id: Unique ID for this conversation (channel or DM)

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

        # Add channel context to the message so Claude can use "this channel"
        # for setting report channels, etc.
        message_with_context = user_message
        if conversation_id:
            message_with_context = f"[Current channel: {conversation_id}]\n\n{user_message}"

        # Run the agent with history
        response = agent.run(message_with_context, conversation_history=history)

        # Store the exchange in memory
        if memory and conversation_id:
            memory.add_message(conversation_id, "user", user_message)

            # For image responses, store a description instead of the marker
            if response.startswith("__IMAGE__|||"):
                # Extract title from __IMAGE__|||filepath|||title
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


def send_response(reply: str, channel: str, say_func):
    """Send a response, handling both text and image uploads.

    If reply starts with __IMAGE__, upload the image file.
    Otherwise, send as regular text message.
    """
    if reply.startswith("__IMAGE__|||"):
        # Parse image response: __IMAGE__|||filepath|||title
        # Using ||| as delimiter to avoid issues with : in Windows paths
        parts = reply.split("|||")
        if len(parts) >= 3:
            filepath = parts[1]
            title = parts[2]

            try:
                # Upload file to Slack
                result = app.client.files_upload_v2(
                    channel=channel,
                    file=filepath,
                    title=title,
                    initial_comment=f"Here's the chart you requested:"
                )
                logger.info(f"Image uploaded successfully: {title}")

                # Clean up temp file
                import os
                if os.path.exists(filepath):
                    os.remove(filepath)
                    logger.info(f"Cleaned up temp file: {filepath}")

            except Exception as e:
                logger.error(f"Failed to upload image: {e}")
                say_func(f"I generated the chart but couldn't upload it: {str(e)}")
        else:
            say_func("Error processing chart response.")
    else:
        # Regular text response
        say_func(reply)


def strip_bot_mention(text: str) -> str:
    """Remove the @mention of the bot from the message text."""
    cleaned = re.sub(r'<@[A-Z0-9]+>', '', text).strip()
    return cleaned


# ────────────────────────────────────────────────
# Handler: Respond to @mentions in channels
# ────────────────────────────────────────────────

@app.event("app_mention")
def handle_mention(event, say, logger):
    logger.info("APP_MENTION received")
    channel = event.get('channel')
    logger.info(f"User: {event.get('user')}, Channel: {channel}")

    text = event.get("text", "").strip()
    if not text:
        return

    user_message = strip_bot_mention(text)

    # Handle special commands
    if user_message.lower() in ["clear", "reset", "forget", "new conversation"]:
        if memory:
            memory.clear_conversation(channel)
            say("Conversation cleared! Starting fresh.")
        else:
            say("Memory not available.")
        return

    if not user_message:
        say("Hey! How can I help you with investment research today?")
        return

    logger.info(f"Processing message: {user_message}")

    # Use channel as conversation ID for context
    reply = get_response(user_message, conversation_id=channel)

    try:
        send_response(reply, channel, say)
        logger.info("Reply sent successfully")
    except Exception as e:
        logger.error(f"Reply failed: {str(e)}")
        say(f"Sorry, I had trouble responding: {str(e)}")


# ────────────────────────────────────────────────
# Handler: Direct Messages (DMs)
# ────────────────────────────────────────────────

@app.message()
def handle_direct_message(message, say, logger):
    channel_type = message.get("channel_type")
    channel = message.get("channel")

    if message.get("bot_id"):
        return

    if channel_type != "im":
        return

    text = message.get("text", "").strip()
    if not text:
        return

    # Handle special commands
    if text.lower() in ["clear", "reset", "forget", "new conversation"]:
        if memory:
            memory.clear_conversation(channel)
            say("Conversation cleared! Starting fresh.")
        else:
            say("Memory not available.")
        return

    logger.info(f"DM received: {text}")

    # Use DM channel as conversation ID
    reply = get_response(text, conversation_id=channel)

    try:
        send_response(reply, channel, say)
        logger.info("DM reply sent")
    except Exception as e:
        logger.error(f"DM reply failed: {str(e)}")


# ────────────────────────────────────────────────
# Slash command
# ────────────────────────────────────────────────

@app.command("/bigclaw")
def handle_bigclaw_command(ack, say, command, logger):
    ack()
    channel = command.get("channel_id")
    logger.info(f"Slash command received: {command.get('text')}")

    user_text = command.get("text", "").strip()

    if not user_text:
        say("Usage: `/bigclaw <your question>`\nExample: `/bigclaw Analyze AAPL like Warren Buffett would`")
        return

    # Use channel as conversation ID
    reply = get_response(user_text, conversation_id=channel)
    send_response(reply, channel, say)


# ────────────────────────────────────────────────
# Start the bot (Socket Mode)
# ────────────────────────────────────────────────

if __name__ == "__main__":
    print("Starting Socket Mode handler...")
    print(f"Agent: {'Enabled with tools' if agent else 'Disabled (echo mode)'}")
    print(f"Memory: {'Enabled' if memory else 'Disabled'}")

    # List available tools
    if agent:
        from tools import TOOLS
        tool_names = [t.name for t in TOOLS]
        print(f"Available tools ({len(tool_names)}): {tool_names}")

    # Start the trading scheduler
    if trading_scheduler:
        trading_scheduler.start()
        print("Trading scheduler: ACTIVE (9:00 AM analysis, 4:30 PM reports)")
    else:
        print("Trading scheduler: DISABLED")

    try:
        handler = SocketModeHandler(app, os.environ.get("SLACK_APP_TOKEN"))
        print("Handler created. Connecting...")
        print(f"\n{BOT_NAME} is ready! Listening for messages...")
        handler.start()
    except Exception as e:
        print(f"Failed to start bot: {str(e)}")
        logger.error(f"Startup failed: {str(e)}")
