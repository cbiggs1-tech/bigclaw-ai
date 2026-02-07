"""Demo tools for testing the BigClaw tool framework."""

from .base import BaseTool


class EchoTool(BaseTool):
    """Simple echo tool for testing the framework."""

    @property
    def name(self) -> str:
        return "echo"

    @property
    def description(self) -> str:
        return "Echoes back a message. Use this to test that tools are working."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The message to echo back"
                }
            },
            "required": ["message"]
        }

    def execute(self, message: str) -> str:
        return f"Echo: {message}"


class GetCurrentTimeTool(BaseTool):
    """Returns the current date and time."""

    @property
    def name(self) -> str:
        return "get_current_time"

    @property
    def description(self) -> str:
        return "Get the current date and time. Useful for time-sensitive market questions."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {},
            "required": []
        }

    def execute(self) -> str:
        from datetime import datetime
        now = datetime.now()
        return now.strftime("%Y-%m-%d %H:%M:%S (%A)")
