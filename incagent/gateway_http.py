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
        return JSONResponse({"peers": [p.model_dump(mode="json") for p in peers]})

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

    async def trigger_improve(request: Request) -> JSONResponse:
        """POST /improve — trigger one self-improvement cycle."""
        if not hasattr(gateway.agent, '_self_improve'):
            return JSONResponse({"error": "Self-improvement not configured"}, status_code=404)
        try:
            result = await gateway.agent.improve()
            return JSONResponse(result)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    async def tools_list(request: Request) -> JSONResponse:
        """GET /tools — list all available tools."""
        tools = gateway.agent.list_tools()
        return JSONResponse({"tools": tools, "count": len(tools)})

    async def tools_execute(request: Request) -> JSONResponse:
        """POST /tools/{name} — execute a tool by name."""
        tool_name = request.path_params["name"]
        try:
            body = await request.json()
            result = await gateway.agent.use_tool(tool_name, **body)
            return JSONResponse(result.to_dict())
        except Exception as e:
            return JSONResponse({"success": False, "error": str(e)}, status_code=400)

    async def tools_create(request: Request) -> JSONResponse:
        """POST /tools — create a new custom tool."""
        try:
            body = await request.json()
            name = body.get("name", "")
            code = body.get("code", "")
            if not name or not code:
                return JSONResponse({"error": "name and code required"}, status_code=400)
            success = gateway.agent.create_tool(name, code)
            return JSONResponse({"success": success, "tool": name})
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    async def balance(request: Request) -> JSONResponse:
        """GET /balance — agent's USDC balance."""
        try:
            bal = await gateway.agent.get_balance()
            return JSONResponse({
                "balance_usdc": bal,
                "wallet": gateway.agent._settlement.payment_executor.wallet_address,
            })
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    async def settlements_list(request: Request) -> JSONResponse:
        """GET /settlements — list active settlements."""
        active = gateway.agent.list_active_settlements()
        return JSONResponse({
            "settlements": [s.model_dump(mode="json") for s in active],
            "count": len(active),
        })

    async def delivery_confirm(request: Request) -> JSONResponse:
        """POST /delivery/confirm — human confirms physical delivery."""
        try:
            body = await request.json()
            settlement_id = body["settlement_id"]
            approved = body.get("approved", True)
            notes = body.get("notes", "")
            result = gateway.agent.confirm_delivery(settlement_id, approved, notes)
            return JSONResponse({"confirmed": result, "settlement_id": settlement_id})
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    async def delivery_webhook(request: Request) -> JSONResponse:
        """POST /delivery/webhook — external system confirms delivery."""
        try:
            body = await request.json()
            settlement_id = body.pop("settlement_id", "")
            result = gateway.agent._settlement.confirm_delivery_webhook(settlement_id, body)
            return JSONResponse({"verified": result})
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    async def dispute_file(request: Request) -> JSONResponse:
        """POST /dispute — file a dispute for a settlement."""
        try:
            body = await request.json()
            dispute = gateway.agent.file_dispute(
                body["settlement_id"], body["reason"],
                body.get("evidence"),
            )
            if dispute:
                return JSONResponse(dispute.model_dump(mode="json"))
            return JSONResponse({"error": "Settlement not found"}, status_code=404)
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
        Route("/improve", trigger_improve, methods=["POST"]),
        Route("/tools", tools_list, methods=["GET"]),
        Route("/tools", tools_create, methods=["POST"]),
        Route("/tools/{name}", tools_execute, methods=["POST"]),
        Route("/balance", balance, methods=["GET"]),
        Route("/settlements", settlements_list, methods=["GET"]),
        Route("/delivery/confirm", delivery_confirm, methods=["POST"]),
        Route("/delivery/webhook", delivery_webhook, methods=["POST"]),
        Route("/dispute", dispute_file, methods=["POST"]),
    ]

    middleware = [
        Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]),
    ]

    return Starlette(routes=routes, middleware=middleware)
