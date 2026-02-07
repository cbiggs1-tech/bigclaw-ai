"""Base tool interface for BigClaw AI tools."""

from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """Abstract base class for all BigClaw tools.

    Each tool must define:
    - name: Unique identifier for the tool
    - description: What the tool does (shown to Claude)
    - parameters: JSON schema for input parameters
    - execute(): The actual tool logic
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name for this tool."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Description of what this tool does (shown to Claude)."""
        pass

    @property
    @abstractmethod
    def parameters(self) -> dict:
        """JSON schema for the tool's input parameters."""
        pass

    @abstractmethod
    def execute(self, **kwargs) -> Any:
        """Execute the tool with the given parameters.

        Returns:
            The result to send back to Claude.
        """
        pass

    def to_claude_tool(self) -> dict:
        """Convert this tool to Claude's tool format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters
        }
