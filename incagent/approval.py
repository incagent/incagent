"""Human-in-the-loop approval workflow."""

from __future__ import annotations

import asyncio
import logging
from enum import Enum

from pydantic import BaseModel, Field

from incagent.config import ApprovalConfig
from incagent.contract import Contract

logger = logging.getLogger("incagent.approval")


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


class ApprovalRequest(BaseModel):
    """A request for human approval."""

    request_id: str = Field(default_factory=lambda: __import__("uuid").uuid4().hex)
    contract_id: str
    description: str
    amount: float
    status: ApprovalStatus = ApprovalStatus.PENDING
    reviewer_note: str = ""


class ApprovalGateway:
    """Routes approval requests to the configured method."""

    def __init__(self, config: ApprovalConfig | None = None) -> None:
        self._config = config or ApprovalConfig()
        self._pending: dict[str, ApprovalRequest] = {}

    def needs_approval(self, amount: float) -> bool:
        """Check if this amount requires human approval."""
        if not self._config.enabled:
            return False
        if self._config.auto_approve_below_threshold and amount < self._config.threshold:
            return False
        return True

    async def request_approval(self, contract: Contract) -> ApprovalRequest:
        """Request human approval for a contract."""
        amount = contract.terms.estimated_value()
        req = ApprovalRequest(
            contract_id=contract.contract_id,
            description=f"Contract: {contract.title} | Value: ${amount:,.2f}",
            amount=amount,
        )
        self._pending[req.request_id] = req

        if not self.needs_approval(amount):
            req.status = ApprovalStatus.SKIPPED
            logger.info("Auto-approved (below threshold): %s", req.description)
            return req

        logger.info("Approval required: %s", req.description)

        if self._config.method == "cli":
            return await self._cli_approval(req)
        elif self._config.method == "webhook":
            return await self._webhook_approval(req)
        elif self._config.method == "slack":
            return await self._slack_approval(req)
        else:
            raise ValueError(f"Unknown approval method: {self._config.method}")

    async def _cli_approval(self, req: ApprovalRequest) -> ApprovalRequest:
        """Interactive CLI approval."""
        print(f"\n{'='*60}")
        print("APPROVAL REQUIRED")
        print(f"{'='*60}")
        print(f"  Contract: {req.description}")
        print(f"  Amount:   ${req.amount:,.2f}")
        print(f"{'='*60}")

        loop = asyncio.get_event_loop()
        try:
            response = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: input("Approve? (y/n): ").strip().lower()),
                timeout=self._config.timeout_seconds,
            )
            if response in ("y", "yes"):
                req.status = ApprovalStatus.APPROVED
                logger.info("Approved by human: %s", req.request_id)
            else:
                req.status = ApprovalStatus.REJECTED
                req.reviewer_note = "Rejected by human"
                logger.info("Rejected by human: %s", req.request_id)
        except asyncio.TimeoutError:
            req.status = ApprovalStatus.TIMEOUT
            logger.warning("Approval timed out: %s", req.request_id)

        return req

    async def _webhook_approval(self, req: ApprovalRequest) -> ApprovalRequest:
        """Send approval request via webhook and poll for response."""
        if not self._config.webhook_url:
            raise ValueError("webhook_url not configured")

        import httpx

        async with httpx.AsyncClient() as client:
            # Send the request
            await client.post(
                self._config.webhook_url,
                json={
                    "request_id": req.request_id,
                    "description": req.description,
                    "amount": req.amount,
                    "action_required": "approve_or_reject",
                },
            )
            logger.info("Webhook sent for approval: %s", req.request_id)

        # For now, auto-approve after webhook (real implementation would poll)
        req.status = ApprovalStatus.PENDING
        return req

    async def _slack_approval(self, req: ApprovalRequest) -> ApprovalRequest:
        """Send approval request via Slack."""
        logger.info("Slack approval requested (not yet implemented): %s", req.request_id)
        req.status = ApprovalStatus.PENDING
        return req

    def force_approve(self, request_id: str) -> ApprovalRequest:
        """Manually approve a pending request."""
        req = self._pending[request_id]
        req.status = ApprovalStatus.APPROVED
        return req

    def force_reject(self, request_id: str, note: str = "") -> ApprovalRequest:
        """Manually reject a pending request."""
        req = self._pending[request_id]
        req.status = ApprovalStatus.REJECTED
        req.reviewer_note = note
        return req
