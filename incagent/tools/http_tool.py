"""HTTP API tool — interact with any REST API."""

from __future__ import annotations

from typing import Any

from incagent.tools.base import BaseTool, ToolParam, ToolResult


class HttpApiTool(BaseTool):
    """Make HTTP API requests with full control over method, headers, auth."""

    @property
    def name(self) -> str:
        return "http_api"

    @property
    def description(self) -> str:
        return (
            "Make HTTP API requests to external services. "
            "Use for CRM integrations, accounting APIs, job board posting, "
            "payment processing, ERP systems, any REST API."
        )

    @property
    def parameters(self) -> list[ToolParam]:
        return [
            ToolParam("url", "string", "API endpoint URL"),
            ToolParam("method", "string", "HTTP method (GET, POST, PUT, DELETE, PATCH)", required=False, default="GET"),
            ToolParam("headers", "object", "HTTP headers", required=False),
            ToolParam("body", "object", "Request body (JSON)", required=False),
            ToolParam("query_params", "object", "URL query parameters", required=False),
            ToolParam("auth_token", "string", "Bearer token for Authorization header", required=False),
            ToolParam("timeout", "number", "Timeout in seconds", required=False, default=30),
        ]

    async def execute(self, **kwargs: Any) -> ToolResult:
        url = kwargs.get("url", "")
        method = kwargs.get("method", "GET").upper()
        headers = dict(kwargs.get("headers") or {})
        body = kwargs.get("body")
        query_params = kwargs.get("query_params")
        auth_token = kwargs.get("auth_token")
        timeout = kwargs.get("timeout", 30)

        if not url:
            return ToolResult(success=False, error="URL is required")

        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.request(
                    method, url,
                    headers=headers or None,
                    json=body if body else None,
                    params=query_params or None,
                    timeout=float(timeout),
                )

                try:
                    resp_data = resp.json()
                except Exception:
                    resp_data = resp.text[:5000]

                return ToolResult(
                    success=200 <= resp.status_code < 400,
                    data={
                        "status": resp.status_code,
                        "headers": dict(resp.headers),
                        "body": resp_data,
                    },
                    error=None if resp.status_code < 400 else f"HTTP {resp.status_code}",
                )
        except ImportError:
            return ToolResult(success=False, error="httpx not installed")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
