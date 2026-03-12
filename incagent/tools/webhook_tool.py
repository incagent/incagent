"""Generic webhook tool — call any HTTP endpoint."""

from __future__ import annotations

from typing import Any

from incagent.tools.base import BaseTool, ToolParam, ToolResult


class WebhookCallTool(BaseTool):
    """Call any HTTP webhook/API endpoint."""

    @property
    def name(self) -> str:
        return "webhook_call"

    @property
    def description(self) -> str:
        return (
            "Make an HTTP request to any URL. Use for webhooks, "
            "external API calls, service integrations, notifications."
        )

    @property
    def parameters(self) -> list[ToolParam]:
        return [
            ToolParam("url", "string", "Target URL"),
            ToolParam("method", "string", "HTTP method", required=False, default="POST"),
            ToolParam("headers", "object", "HTTP headers dict", required=False),
            ToolParam("body", "object", "Request body (JSON)", required=False),
            ToolParam("timeout", "number", "Timeout in seconds", required=False, default=30),
        ]

    async def execute(self, **kwargs: Any) -> ToolResult:
        url = kwargs.get("url", "")
        method = kwargs.get("method", "POST").upper()
        headers = kwargs.get("headers") or {}
        body = kwargs.get("body")
        timeout = kwargs.get("timeout", 30)

        if not url:
            return ToolResult(success=False, error="URL is required")

        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.request(
                    method, url,
                    headers=headers,
                    json=body if body else None,
                    timeout=float(timeout),
                )
                try:
                    data = resp.json()
                except Exception:
                    data = resp.text

                return ToolResult(
                    success=200 <= resp.status_code < 400,
                    data={"status": resp.status_code, "body": data},
                    error=None if resp.status_code < 400 else f"HTTP {resp.status_code}",
                )
        except ImportError:
            return ToolResult(success=False, error="httpx not installed")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
