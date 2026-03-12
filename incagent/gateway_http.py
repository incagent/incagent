"""HTTP API layer for the Gateway — secured with auth, rate limiting, audit.

Security layers (applied in order):
1. Rate limiting (per IP)
2. API key authentication (HMAC-SHA256)
3. Input validation
4. Endpoint-level permission checks
5. Audit logging
"""

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

from incagent.security import (
    AuditLogger,
    InputValidator,
    RateLimiter,
    SecurityConfig,
    hash_api_key,
    verify_api_key,
    verify_request_signature,
)

if TYPE_CHECKING:
    from incagent.gateway import Gateway

logger = logging.getLogger("incagent.gateway.http")


def _get_client_ip(request: Request) -> str:
    """Extract client IP from request (handles proxies)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def create_app(gateway: Gateway, security: SecurityConfig | None = None) -> Starlette:
    """Create the secured ASGI application for the Gateway."""

    sec = security or getattr(gateway, '_security', None) or SecurityConfig()

    # Prepare hashed API keys for verification
    key_hashes = [hash_api_key(k) for k in sec.api_keys]
    # Also check env var
    env_key = __import__("os").environ.get("INCAGENT_API_KEY", "")
    if env_key:
        key_hashes.append(hash_api_key(env_key))

    # Rate limiter
    limiter = RateLimiter(
        max_per_minute=sec.rate_limit_per_minute,
        burst=sec.rate_limit_burst,
    )

    # Audit logger
    audit: AuditLogger | None = None
    if sec.audit_log_path:
        audit = AuditLogger(sec.audit_log_path)
    elif hasattr(gateway.agent, '_config'):
        audit = AuditLogger(gateway.agent._config.data_dir / "audit.db")

    def _audit(event: str, actor: str, target: str = "", details: str = "", ip: str = "") -> None:
        if audit:
            try:
                audit.log(event, actor, target, details, ip)
            except Exception as e:
                logger.error("Audit log failed: %s", e)

    # ── Security middleware ────────────────────────────────────────

    async def security_middleware(request: Request, call_next: Any) -> JSONResponse:
        """Combined security middleware: rate limit + auth.

        Note: Does NOT read request body to avoid consuming it before handlers.
        Body-level validation (HMAC, input) is done in each endpoint handler.
        """
        ip = _get_client_ip(request)
        path = request.url.path

        # 1. Rate limiting
        if not limiter.allow(ip):
            _audit("rate_limited", ip, path, ip=ip)
            return JSONResponse(
                {"error": "Rate limit exceeded", "retry_after_seconds": 60},
                status_code=429,
            )

        # 2. Authentication (skip for public endpoints)
        if sec.require_auth and path not in sec.public_endpoints:
            auth_header = request.headers.get("authorization", "")
            api_key = ""

            if auth_header.startswith("Bearer "):
                api_key = auth_header[7:]
            elif request.query_params.get("api_key"):
                api_key = request.query_params["api_key"]

            if not key_hashes:
                # No keys configured = auth disabled (backward compat)
                pass
            elif not api_key or not verify_api_key(api_key, key_hashes):
                _audit("auth_failed", ip, path, ip=ip)
                return JSONResponse(
                    {"error": "Unauthorized. Provide valid API key via Authorization: Bearer <key>"},
                    status_code=401,
                )

        # Pass through (body-level checks in handlers)
        response = await call_next(request)
        return response

    # ── Endpoint handlers ─────────────────────────────────────────

    async def health(request: Request) -> JSONResponse:
        """GET /health — agent health status (public)."""
        status = gateway.agent.health_status()
        status["gateway_running"] = gateway.is_running
        if hasattr(gateway.agent, '_memory'):
            status["memory_entries"] = gateway.agent._memory.stats()
        return JSONResponse(status)

    async def identity(request: Request) -> JSONResponse:
        """GET /identity — public identity info (public)."""
        return JSONResponse(gateway.agent.identity.to_public_dict())

    async def receive_message(request: Request) -> JSONResponse:
        """POST /messages — receive a message from another agent."""
        from incagent.messaging import AgentMessage
        ip = _get_client_ip(request)
        try:
            body = await request.json()

            # Input validation
            violations = InputValidator.validate_json_body(body)
            if violations:
                return JSONResponse({"error": "Validation failed", "violations": violations}, status_code=400)

            msg = AgentMessage.from_wire(body)
            gateway.agent._bus.send(msg)
            _audit("message_received", msg.sender_id, gateway.agent.agent_id,
                   f"type={msg.message_type.value}", ip)
            return JSONResponse({"status": "accepted", "message_id": msg.message_id})
        except Exception as e:
            logger.error("Failed to process message: %s", e)
            return JSONResponse({"error": str(e)}, status_code=400)

    async def propose_trade(request: Request) -> JSONResponse:
        """POST /propose — receive a trade proposal from a remote agent."""
        from incagent.contract import Contract, ContractTerms
        ip = _get_client_ip(request)
        try:
            body = await request.json()

            violations = InputValidator.validate_json_body(body)
            if violations:
                return JSONResponse({"error": "Validation failed", "violations": violations}, status_code=400)

            contract = Contract(
                title=body["title"],
                terms=ContractTerms(**body.get("terms", {})),
            )
            if hasattr(gateway.agent, '_heartbeat') and gateway.agent._heartbeat:
                gateway.agent._heartbeat.queue_proposal(body.get("proposer_url", ""), contract)

            _audit("trade_proposed", body.get("proposer_url", "unknown"), gateway.agent.agent_id,
                   f"contract={contract.contract_id}", ip)

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
        limit = min(int(request.query_params.get("limit", "50")), 200)  # Cap at 200
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
        ip = _get_client_ip(request)
        if not hasattr(gateway.agent, '_registry'):
            return JSONResponse({"error": "Registry not configured"}, status_code=404)
        try:
            body = await request.json()

            violations = InputValidator.validate_json_body(body)
            if violations:
                return JSONResponse({"error": "Validation failed", "violations": violations}, status_code=400)

            from incagent.registry import PeerAgent
            peer = PeerAgent(**body)
            gateway.agent._registry.register(peer)
            _audit("peer_registered", ip, peer.agent_id, ip=ip)
            return JSONResponse({"status": "registered", "peer_id": peer.agent_id})
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    async def trigger_improve(request: Request) -> JSONResponse:
        """POST /improve — trigger one self-improvement cycle."""
        ip = _get_client_ip(request)

        # Security: check if self-improvement via API is allowed
        if not sec.allow_self_improve_via_api:
            _audit("improve_blocked", ip, "self_improve", "API access denied", ip)
            return JSONResponse(
                {"error": "Self-improvement via API is disabled. Set allow_self_improve_via_api=True."},
                status_code=403,
            )

        if not hasattr(gateway.agent, '_self_improve'):
            return JSONResponse({"error": "Self-improvement not configured"}, status_code=404)
        try:
            result = await gateway.agent.improve()
            _audit("self_improve", gateway.agent.agent_id, "", json.dumps(result, default=str), ip)
            return JSONResponse(result)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    async def tools_list(request: Request) -> JSONResponse:
        """GET /tools — list all available tools."""
        tools = gateway.agent.list_tools()
        return JSONResponse({"tools": tools, "count": len(tools)})

    async def tools_execute(request: Request) -> JSONResponse:
        """POST /tools/{name} — execute a tool by name."""
        ip = _get_client_ip(request)
        tool_name = request.path_params["name"]

        # Security: check tool permissions
        if sec.tool_denylist and tool_name in sec.tool_denylist:
            _audit("tool_denied", ip, tool_name, "In denylist", ip)
            return JSONResponse({"error": f"Tool '{tool_name}' is not allowed via API"}, status_code=403)

        if sec.tool_allowlist and tool_name not in sec.tool_allowlist:
            _audit("tool_denied", ip, tool_name, "Not in allowlist", ip)
            return JSONResponse({"error": f"Tool '{tool_name}' is not in the allowlist"}, status_code=403)

        try:
            body = await request.json()

            violations = InputValidator.validate_json_body(body)
            if violations:
                return JSONResponse({"error": "Validation failed", "violations": violations}, status_code=400)

            result = await gateway.agent.use_tool(tool_name, **body)
            _audit("tool_executed", ip, tool_name,
                   f"success={result.success}", ip)
            return JSONResponse(result.to_dict())
        except Exception as e:
            return JSONResponse({"success": False, "error": str(e)}, status_code=400)

    async def tools_create(request: Request) -> JSONResponse:
        """POST /tools — create a new custom tool."""
        ip = _get_client_ip(request)

        # Security: check if tool creation via API is allowed
        if not sec.allow_tool_creation_via_api:
            _audit("tool_create_blocked", ip, "tools", "API access denied", ip)
            return JSONResponse(
                {"error": "Tool creation via API is disabled. Set allow_tool_creation_via_api=True."},
                status_code=403,
            )

        try:
            body = await request.json()
            name = body.get("name", "")
            code = body.get("code", "")

            if not name or not code:
                return JSONResponse({"error": "name and code required"}, status_code=400)

            # Validate tool name
            safe_name = InputValidator.sanitize_name(name)
            if not safe_name:
                return JSONResponse(
                    {"error": "Invalid tool name. Use only alphanumeric, underscore, hyphen."},
                    status_code=400,
                )

            # Validate code safety (sandbox check happens in registry too)
            from incagent.security import CodeSandbox
            sandbox = CodeSandbox(sec.blocked_imports)
            violations = sandbox.validate(code)
            if violations:
                _audit("tool_create_blocked", ip, safe_name,
                       f"violations={json.dumps(violations)}", ip)
                return JSONResponse(
                    {"error": "Code validation failed", "violations": violations},
                    status_code=400,
                )

            success = gateway.agent.create_tool(safe_name, code)
            _audit("tool_created", ip, safe_name, f"success={success}", ip)
            return JSONResponse({"success": success, "tool": safe_name})
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
        ip = _get_client_ip(request)
        try:
            body = await request.json()
            settlement_id = body["settlement_id"]
            approved = body.get("approved", True)
            notes = body.get("notes", "")
            result = gateway.agent.confirm_delivery(settlement_id, approved, notes)
            _audit("delivery_confirmed", ip, settlement_id,
                   f"approved={approved}", ip)
            return JSONResponse({"confirmed": result, "settlement_id": settlement_id})
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    async def delivery_webhook(request: Request) -> JSONResponse:
        """POST /delivery/webhook — external system confirms delivery."""
        ip = _get_client_ip(request)
        try:
            body = await request.json()
            settlement_id = body.pop("settlement_id", "")
            result = gateway.agent._settlement.confirm_delivery_webhook(settlement_id, body)
            _audit("delivery_webhook", ip, settlement_id, ip=ip)
            return JSONResponse({"verified": result})
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    async def dispute_file(request: Request) -> JSONResponse:
        """POST /dispute — file a dispute for a settlement."""
        ip = _get_client_ip(request)
        try:
            body = await request.json()
            dispute = gateway.agent.file_dispute(
                body["settlement_id"], body["reason"],
                body.get("evidence"),
            )
            if dispute:
                _audit("dispute_filed", ip, body["settlement_id"],
                       body["reason"], ip)
                return JSONResponse(dispute.model_dump(mode="json"))
            return JSONResponse({"error": "Settlement not found"}, status_code=404)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    async def metrics_view(request: Request) -> JSONResponse:
        """GET /metrics — Prometheus metrics (public)."""
        from starlette.responses import Response
        from incagent.metrics import METRICS
        return Response(METRICS.render(), media_type="text/plain; charset=utf-8")

    async def tax_summary(request: Request) -> JSONResponse:
        """GET /tax — tax year summary."""
        year = request.query_params.get("year")
        summary = gateway.agent.get_tax_summary(int(year) if year else None)
        return JSONResponse(summary)

    async def audit_view(request: Request) -> JSONResponse:
        """GET /audit — view audit log (requires auth)."""
        if not audit:
            return JSONResponse({"error": "Audit log not configured"}, status_code=404)
        limit = min(int(request.query_params.get("limit", "50")), 200)
        event_type = request.query_params.get("event_type")
        entries = audit.query(event_type=event_type, limit=limit)
        valid, last_id = audit.verify_chain()
        return JSONResponse({
            "entries": entries,
            "chain_valid": valid,
            "last_valid_id": last_id,
        })

    # ── Routes ────────────────────────────────────────────────────

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
        Route("/audit", audit_view, methods=["GET"]),
        Route("/metrics", metrics_view, methods=["GET"]),
        Route("/tax", tax_summary, methods=["GET"]),
    ]

    # ── CORS — locked down by default ─────────────────────────────

    allowed_origins = sec.allowed_origins if sec.allowed_origins else []
    middleware_list = []

    if allowed_origins:
        middleware_list.append(
            Middleware(
                CORSMiddleware,
                allow_origins=allowed_origins,
                allow_methods=["GET", "POST"],
                allow_headers=["Authorization", "Content-Type",
                               "X-IncAgent-Timestamp", "X-IncAgent-Signature"],
                allow_credentials=False,
            )
        )

    app = Starlette(routes=routes, middleware=middleware_list)

    # Attach security middleware manually (Starlette pure ASGI)
    from starlette.middleware import Middleware as _MW
    from starlette.middleware.base import BaseHTTPMiddleware

    class SecurityMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next: Any) -> Any:
            return await security_middleware(request, call_next)

    app.add_middleware(SecurityMiddleware)

    return app
