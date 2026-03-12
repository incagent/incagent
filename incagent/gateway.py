"""Gateway — persistent agent runtime server (OpenClaw-inspired).

The Gateway is the always-on daemon that:
1. Hosts the agent's HTTP API for inter-agent communication
2. Manages the Heartbeat scheduler for autonomous behavior
3. Routes messages between local and remote agents
4. Exposes management endpoints (health, ledger, config)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from incagent.config import AgentConfig
from incagent.messaging import AgentMessage, MessageType

logger = logging.getLogger("incagent.gateway")


class Gateway:
    """Persistent HTTP server that hosts an IncAgent and manages its lifecycle."""

    def __init__(self, agent: Any, *, host: str = "0.0.0.0", port: int = 8400) -> None:
        self.agent = agent
        self.host = host
        self.port = port
        self._server: asyncio.Server | None = None
        self._running = False

    async def start(self) -> None:
        """Start the Gateway HTTP server."""
        from incagent.gateway_http import create_app

        app = create_app(self)
        self._running = True

        # Start heartbeat if configured
        if hasattr(self.agent, '_heartbeat') and self.agent._heartbeat:
            asyncio.create_task(self.agent._heartbeat.run(self.agent))

        logger.info(
            "Gateway started: %s (%s) listening on %s:%d",
            self.agent.name, self.agent.agent_id, self.host, self.port,
        )

        # Run the ASGI app
        import uvicorn
        config = uvicorn.Config(app, host=self.host, port=self.port, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()

    async def stop(self) -> None:
        """Gracefully stop the Gateway."""
        self._running = False
        if hasattr(self.agent, '_heartbeat') and self.agent._heartbeat:
            self.agent._heartbeat.stop()
        self.agent.close()
        logger.info("Gateway stopped: %s", self.agent.name)

    @property
    def is_running(self) -> bool:
        return self._running
