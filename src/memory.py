"""Conversation memory for BigClaw AI.

Stores recent conversation history per channel/user to enable
context-aware follow-up questions.
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# Maximum messages to keep per conversation
MAX_MESSAGES_PER_CONVERSATION = 20

# Maximum age of messages to keep (in minutes)
MAX_MESSAGE_AGE_MINUTES = 60


class ConversationMemory:
    """Manages conversation history for multiple channels/users."""

    def __init__(self, max_messages: int = MAX_MESSAGES_PER_CONVERSATION,
                 max_age_minutes: int = MAX_MESSAGE_AGE_MINUTES):
        """Initialize conversation memory.

        Args:
            max_messages: Maximum messages to keep per conversation
            max_age_minutes: Maximum age of messages before cleanup
        """
        self._conversations: dict[str, list[dict]] = defaultdict(list)
        self.max_messages = max_messages
        self.max_age_minutes = max_age_minutes

    def add_message(self, conversation_id: str, role: str, content: str) -> None:
        """Add a message to a conversation.

        Args:
            conversation_id: Unique identifier (channel_id or user_id)
            role: 'user' or 'assistant'
            content: The message content
        """
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now()
        }

        self._conversations[conversation_id].append(message)

        # Trim to max messages
        if len(self._conversations[conversation_id]) > self.max_messages:
            self._conversations[conversation_id] = \
                self._conversations[conversation_id][-self.max_messages:]

        logger.debug(f"Added {role} message to {conversation_id}, "
                    f"history size: {len(self._conversations[conversation_id])}")

    def get_history(self, conversation_id: str) -> list[dict]:
        """Get conversation history for Claude API format.

        Args:
            conversation_id: Unique identifier

        Returns:
            List of message dicts with 'role' and 'content' keys
        """
        self._cleanup_old_messages(conversation_id)

        # Return messages without timestamps (Claude format)
        return [
            {"role": msg["role"], "content": msg["content"]}
            for msg in self._conversations[conversation_id]
        ]

    def get_history_length(self, conversation_id: str) -> int:
        """Get number of messages in a conversation."""
        return len(self._conversations[conversation_id])

    def clear_conversation(self, conversation_id: str) -> None:
        """Clear history for a specific conversation."""
        if conversation_id in self._conversations:
            del self._conversations[conversation_id]
            logger.info(f"Cleared conversation history for {conversation_id}")

    def clear_all(self) -> None:
        """Clear all conversation history."""
        self._conversations.clear()
        logger.info("Cleared all conversation history")

    def _cleanup_old_messages(self, conversation_id: str) -> None:
        """Remove messages older than max_age_minutes."""
        if conversation_id not in self._conversations:
            return

        cutoff = datetime.now() - timedelta(minutes=self.max_age_minutes)
        original_count = len(self._conversations[conversation_id])

        self._conversations[conversation_id] = [
            msg for msg in self._conversations[conversation_id]
            if msg["timestamp"] > cutoff
        ]

        removed = original_count - len(self._conversations[conversation_id])
        if removed > 0:
            logger.debug(f"Cleaned up {removed} old messages from {conversation_id}")


# Global memory instance
memory = ConversationMemory()


def get_memory() -> ConversationMemory:
    """Get the global conversation memory instance."""
    return memory
