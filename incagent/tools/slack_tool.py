"""Slack notification tool."""

from __future__ import annotations

import os
from typing import Any

from incagent.tools.base import BaseTool, ToolParam, ToolResult


class SlackNotifyTool(BaseTool):
    """Send messages to Slack channels or users."""

    @property
    def name(self) -> str:
        return "slack_notify"

    @property
    def description(self) -> str:
        return (
            "Send a message to a Slack channel or user. "
            "Use for trade alerts, task assignments, status updates, escalations."
        )

    @property
    def parameters(self) -> list[ToolParam]:
        return [
            ToolParam("channel", "string", "Slack channel or user ID (e.g., #general, @user, C01234)"),
            ToolParam("message", "string", "Message text (supports Slack markdown)"),
            ToolParam("blocks", "object", "Optional Slack Block Kit blocks for rich messages", required=False),
        ]

    async def execute(self, **kwargs: Any) -> ToolResult:
        channel = kwargs.get("channel", "")
        message = kwargs.get("message", "")
        blocks = kwargs.get("blocks")

        token = os.environ.get("SLACK_BOT_TOKEN")
        if not token:
            return ToolResult(success=False, error="SLACK_BOT_TOKEN not set")

        try:
            import httpx
            async with httpx.AsyncClient() as client:
                payload: dict[str, Any] = {
                    "channel": channel,
                    "text": message,
                }
                if blocks:
                    payload["blocks"] = blocks

                resp = await client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={"Authorization": f"Bearer {token}"},
                    json=payload,
                    timeout=10.0,
                )
                data = resp.json()
                if data.get("ok"):
                    return ToolResult(success=True, data={"ts": data.get("ts"), "channel": data.get("channel")})
                return ToolResult(success=False, error=data.get("error", "Unknown Slack error"))
        except ImportError:
            return ToolResult(success=False, error="httpx not installed")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
