"""HTTP API layer for the Gateway (lightweight ASGI with Starlette)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

if TYPE_CHECKING:
    from incagent.gateway import Gateway

logger = logging.getLogger("incagent.gateway.http")


def create_app(gateway: Gateway) -> Starlette:
    """Create the ASGI application for the Gateway."""

    async def health(request: Request) -> JSONResponse:
        """GET /health — agent health status."""
        status = gateway.agent.health_status()
        status["gateway_running"] = gateway.is_running
        if hasattr(gateway.agent, '_memory'):
            status["memory_entries"] = gateway.agent._memory.stats()
        return JSONResponse(status)

    async def identity(request: Request) -> JSONResponse:
        """GET /identity — public identity info."""
        return JSONResponse(gateway.agent.identity.to_public_dict())

    async def receive_message(request: Request) -> JSONResponse:
        """POST /messages — receive a message from another agent."""
        from incagent.messaging import AgentMessage
        try:
            body = await request.json()
            msg = AgentMessage.from_wire(body)
            gateway.agent._bus.send(msg)
            logger.info("Received message from %s: %s", msg.sender_id, msg.message_type.value)
            return JSONResponse({"status": "accepted", "message_id": msg.message_id})
        except Exception as e:
            logger.error("Failed to process message: %s", e)
            return JSONResponse({"error": str(e)}, status_code=400)

    async def propose_trade(request: Request) -> JSONResponse:
        """POST /propose — receive a trade proposal from a remote agent."""
        from incagent.contract import Contract, ContractTerms
        try:
            body = await request.json()
            contract = Contract(
                title=body["title"],
                terms=ContractTerms(**body.get("terms", {})),
            )
            # Queue for heartbeat to process
            if hasattr(gateway.agent, '_heartbeat') and gateway.agent._heartbeat:
                gateway.agent._heartbeat.queue_proposal(body.get("proposer_url", ""), contract)

            return JSONResponse({
                "status": "queued",
                "contract_id": contract.contract_id,
                "agent": gateway.agent.identity.to_public_dict(),
            })
        except Exception as e:
            logger.error("Failed to process proposal: %s", e)
            return JSONResponse({"error": str(e)}, status_code=400)

    async def ledger(request: Request) -> JSONResponse:
        """GET /ledger — recent ledger entries."""
        limit = int(request.query_params.get("limit", "50"))
        entries = gateway.agent.get_ledger_entries(limit=limit)
        return JSONResponse(entries)

    async def memory_view(request: Request) -> JSONResponse:
        """GET /memory — agent's learned insights."""
        if not hasattr(gateway.agent, '_memory'):
            return JSONResponse({"error": "Memory not configured"}, status_code=404)
        return JSONResponse(gateway.agent._memory.export())

    async def skills_list(request: Request) -> JSONResponse:
        """GET /skills — available skills."""
        if not hasattr(gateway.agent, '_skills'):
            return JSONResponse({"skills": []})
        skills = gateway.agent._skills.list_skills()
        return JSONResponse({"skills": skills})

    async def registry_peers(request: Request) -> JSONResponse:
        """GET /peers — known peer agents."""
        if not hasattr(gateway.agent, '_registry'):
            return JSONResponse({"peers": []})
        peers = gateway.agent._registry.list_peers()
        return JSONResponse({"peers": [p.model_dump() for p in peers]})

    async def register_peer(request: Request) -> JSONResponse:
        """POST /peers — register a new peer agent."""
        if not hasattr(gateway.agent, '_registry'):
            return JSONResponse({"error": "Registry not configured"}, status_code=404)
        try:
            body = await request.json()
            from incagent.registry import PeerAgent
            peer = PeerAgent(**body)
            gateway.agent._registry.register(peer)
            return JSONResponse({"status": "registered", "peer_id": peer.agent_id})
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    routes = [
        Route("/health", health, methods=["GET"]),
        Route("/identity", identity, methods=["GET"]),
        Route("/messages", receive_message, methods=["POST"]),
        Route("/propose", propose_trade, methods=["POST"]),
        Route("/ledger", ledger, methods=["GET"]),
        Route("/memory", memory_view, methods=["GET"]),
        Route("/skills", skills_list, methods=["GET"]),
        Route("/peers", registry_peers, methods=["GET"]),
        Route("/peers", register_peer, methods=["POST"]),
    ]

    middleware = [
        Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]),
    ]

    return Starlette(routes=routes, middleware=middleware)
