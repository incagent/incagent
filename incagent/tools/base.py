"""Base tool interface — all tools implement this."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("incagent.tools")


@dataclass
class ToolParam:
    """Parameter definition for a tool."""
    name: str
    type: str  # "string", "number", "boolean", "object"
    description: str
    required: bool = True
    default: Any = None


@dataclass
class ToolResult:
    """Result from tool execution."""
    success: bool
    data: Any = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"success": self.success}
        if self.data is not None:
            d["data"] = self.data
        if self.error:
            d["error"] = self.error
        return d


class BaseTool(ABC):
    """Abstract base for all agent tools.

    Subclass this to create a new tool the agent can use.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool name (snake_case)."""

    @property
    @abstractmethod
    def description(self) -> str:
        """What this tool does (shown to LLM for tool selection)."""

    @property
    @abstractmethod
    def parameters(self) -> list[ToolParam]:
        """Parameters this tool accepts."""

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        """Run the tool with given parameters."""

    def schema(self) -> dict[str, Any]:
        """JSON Schema representation for LLM tool_use."""
        props = {}
        required = []
        for p in self.parameters:
            props[p.name] = {
                "type": p.type,
                "description": p.description,
            }
            if p.default is not None:
                props[p.name]["default"] = p.default
            if p.required:
                required.append(p.name)

        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": props,
                "required": required,
            },
        }
