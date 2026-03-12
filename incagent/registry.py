"""Agent Registry — discovery, connection, and peer management.

Agents register themselves on startup and discover trading partners.
Supports both local (in-memory) and remote (HTTP) registry modes.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger("incagent.registry")


class PeerAgent(BaseModel):
    """A known peer agent in the network."""

    agent_id: str
    name: str
    role: str  # buyer, seller, broker
    url: str  # Gateway URL (e.g. http://host:8400)
    capabilities: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    public_key_hex: str = ""
    last_seen: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    def is_alive(self, timeout_seconds: float = 300) -> bool:
        """Check if peer was seen recently."""
        delta = (datetime.now(timezone.utc) - self.last_seen).total_seconds()
        return delta < timeout_seconds


class Registry:
    """Local agent registry with optional remote hub sync."""

    def __init__(self, hub_url: str | None = None) -> None:
        self._peers: dict[str, PeerAgent] = {}
        self._hub_url = hub_url  # Optional central registry URL

    def register(self, peer: PeerAgent) -> None:
        """Register a peer agent."""
        peer.last_seen = datetime.now(timezone.utc)
        self._peers[peer.agent_id] = peer
        logger.info("Registered peer: %s (%s) at %s", peer.name, peer.role, peer.url)

    def unregister(self, agent_id: str) -> None:
        """Remove a peer from the registry."""
        if agent_id in self._peers:
            name = self._peers[agent_id].name
            del self._peers[agent_id]
            logger.info("Unregistered peer: %s", name)

    def heartbeat(self, agent_id: str) -> None:
        """Update last_seen for a peer."""
        if agent_id in self._peers:
            self._peers[agent_id].last_seen = datetime.now(timezone.utc)

    def find_by_role(self, role: str) -> list[PeerAgent]:
        """Find peers by role (buyer/seller/broker)."""
        return [p for p in self._peers.values() if p.role == role and p.is_alive()]

    def find_by_capability(self, capability: str) -> list[PeerAgent]:
        """Find peers that have a specific capability."""
        return [
            p for p in self._peers.values()
            if capability in p.capabilities and p.is_alive()
        ]

    def find_by_industry(self, industry: str) -> list[PeerAgent]:
        """Find peers in a specific industry."""
        return [
            p for p in self._peers.values()
            if industry in p.industries and p.is_alive()
        ]

    def find_trading_partners(self, my_role: str, industry: str | None = None) -> list[PeerAgent]:
        """Find complementary trading partners (buyers find sellers, etc.)."""
        target_role = "seller" if my_role == "buyer" else "buyer"
        candidates = self.find_by_role(target_role)
        if industry:
            candidates = [p for p in candidates if industry in p.industries]
        return candidates

    def list_peers(self) -> list[PeerAgent]:
        """List all known peers."""
        return list(self._peers.values())

    def get(self, agent_id: str) -> PeerAgent | None:
        """Get a specific peer."""
        return self._peers.get(agent_id)

    async def announce(self, my_info: PeerAgent) -> None:
        """Announce self to all known peers."""
        wire = my_info.model_dump()
        wire["last_seen"] = my_info.last_seen.isoformat()

        async with httpx.AsyncClient(timeout=10.0) as client:
            for peer in self._peers.values():
                if peer.agent_id == my_info.agent_id:
                    continue
                try:
                    await client.post(f"{peer.url}/peers", json=wire)
                    logger.info("Announced to peer: %s", peer.name)
                except Exception as e:
                    logger.warning("Failed to announce to %s: %s", peer.name, e)

    async def discover_from_hub(self) -> list[PeerAgent]:
        """Fetch peer list from central hub (if configured)."""
        if not self._hub_url:
            return []

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self._hub_url}/agents")
                resp.raise_for_status()
                data = resp.json()
                peers = []
                for item in data.get("agents", []):
                    peer = PeerAgent(**item)
                    self.register(peer)
                    peers.append(peer)
                logger.info("Discovered %d peers from hub", len(peers))
                return peers
        except Exception as e:
            logger.warning("Hub discovery failed: %s", e)
            return []

    async def probe_peer(self, url: str) -> PeerAgent | None:
        """Probe a URL to discover an agent's identity and register it."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{url}/identity")
                resp.raise_for_status()
                data = resp.json()
                peer = PeerAgent(
                    agent_id=data["agent_id"],
                    name=data["name"],
                    role=data["role"],
                    url=url,
                    public_key_hex=data.get("public_key", ""),
                )
                self.register(peer)
                return peer
        except Exception as e:
            logger.warning("Failed to probe %s: %s", url, e)
            return None
