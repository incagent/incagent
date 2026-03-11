"""Agent-to-agent messaging via HTTP."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("incagent.messaging")


class MessageType(str, Enum):
    PROPOSAL = "proposal"
    COUNTER_PROPOSAL = "counter_proposal"
    ACCEPT = "accept"
    REJECT = "reject"
    INFO = "info"
    HEARTBEAT = "heartbeat"
    ERROR = "error"


class AgentMessage(BaseModel):
    """A signed message between agents."""

    message_id: str = Field(default_factory=lambda: __import__("uuid").uuid4().hex)
    sender_id: str
    recipient_id: str
    message_type: MessageType
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    signature: str = ""
    reply_to: str | None = None

    def to_wire(self) -> dict[str, Any]:
        """Serialize for transmission."""
        d = self.model_dump()
        d["timestamp"] = self.timestamp.isoformat()
        return d

    @classmethod
    def from_wire(cls, data: dict[str, Any]) -> AgentMessage:
        """Deserialize from wire format."""
        return cls(**data)


class MessageBus:
    """In-process message bus for local agent communication."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Any]] = {}
        self._inbox: dict[str, list[AgentMessage]] = {}

    def register(self, agent_id: str, handler: Any = None) -> None:
        """Register an agent on the bus."""
        if agent_id not in self._inbox:
            self._inbox[agent_id] = []
        if handler:
            self._handlers.setdefault(agent_id, []).append(handler)

    def send(self, message: AgentMessage) -> None:
        """Send a message to a recipient."""
        recipient = message.recipient_id
        if recipient not in self._inbox:
            logger.warning("Unknown recipient: %s", recipient)
            return
        self._inbox[recipient].append(message)
        # Notify handlers
        for handler in self._handlers.get(recipient, []):
            try:
                handler(message)
            except Exception as e:
                logger.error("Handler error for %s: %s", recipient, e)

    def receive(self, agent_id: str) -> list[AgentMessage]:
        """Get all pending messages for an agent."""
        messages = self._inbox.get(agent_id, [])
        self._inbox[agent_id] = []
        return messages

    def peek(self, agent_id: str) -> int:
        """Check how many messages are pending."""
        return len(self._inbox.get(agent_id, []))


class HTTPTransport:
    """HTTP-based agent communication transport."""

    def __init__(self) -> None:
        self._client: Any = None

    async def _get_client(self) -> Any:
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def send(self, url: str, message: AgentMessage) -> dict[str, Any]:
        """Send a message to a remote agent via HTTP POST."""
        client = await self._get_client()
        try:
            response = await client.post(
                f"{url}/messages",
                json=message.to_wire(),
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error("HTTP send failed to %s: %s", url, e)
            raise

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
