"""Autonomous negotiation engine powered by LLMs."""

from __future__ import annotations

import json
import logging
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from incagent.config import LLMConfig
from incagent.contract import Contract, ContractTerms

logger = logging.getLogger("incagent.negotiation")


class NegotiationStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    AGREED = "agreed"
    REJECTED = "rejected"
    TIMEOUT = "timeout"


class NegotiationPolicy(BaseModel):
    """Defines the boundaries within which an agent can negotiate."""

    min_price: float | None = None
    max_price: float | None = None
    min_quantity: int | None = None
    max_quantity: int | None = None
    required_terms: list[str] = Field(default_factory=list)
    max_rounds: int = 10
    acceptable_payment_terms: list[str] = Field(
        default_factory=lambda: ["net_30", "net_60", "prepaid"]
    )
    walk_away_threshold: float = 0.0  # Walk away if value below this


class NegotiationRound(BaseModel):
    """A single round of negotiation."""

    round_number: int
    proposer: str
    proposed_terms: dict[str, Any]
    response: str = ""
    accepted: bool = False


class NegotiationResult(BaseModel):
    """The outcome of a negotiation."""

    status: NegotiationStatus
    final_terms: ContractTerms | None = None
    rounds: int = 0
    history: list[NegotiationRound] = Field(default_factory=list)
    reason: str = ""


class NegotiationEngine:
    """LLM-powered autonomous negotiation between two agents."""

    def __init__(self, llm_config: LLMConfig | None = None) -> None:
        self._config = llm_config or LLMConfig()
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if self._config.provider == "anthropic":
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self._config.api_key)
            except ImportError:
                raise RuntimeError("Install anthropic: pip install incagent[llm]")
        else:
            try:
                import openai
                self._client = openai.OpenAI(api_key=self._config.api_key)
            except ImportError:
                raise RuntimeError("Install openai: pip install incagent[llm]")
        return self._client

    async def negotiate(
        self,
        contract: Contract,
        my_policy: NegotiationPolicy,
        counterparty_policy: NegotiationPolicy | None = None,
    ) -> NegotiationResult:
        """Run autonomous negotiation rounds."""
        rounds: list[NegotiationRound] = []
        current_terms = contract.terms.model_dump()

        for round_num in range(1, my_policy.max_rounds + 1):
            # Generate counter-proposal using LLM
            proposal = await self._generate_proposal(
                contract, current_terms, my_policy, rounds, round_num
            )

            round_entry = NegotiationRound(
                round_number=round_num,
                proposer=contract.proposer_id if round_num % 2 == 1 else contract.counterparty_id,
                proposed_terms=proposal.get("terms", current_terms),
                response=proposal.get("reasoning", ""),
                accepted=proposal.get("accepted", False),
            )
            rounds.append(round_entry)

            if proposal.get("accepted"):
                final_terms = ContractTerms(**proposal.get("terms", current_terms))
                return NegotiationResult(
                    status=NegotiationStatus.AGREED,
                    final_terms=final_terms,
                    rounds=round_num,
                    history=rounds,
                )

            if proposal.get("walk_away"):
                return NegotiationResult(
                    status=NegotiationStatus.REJECTED,
                    rounds=round_num,
                    history=rounds,
                    reason=proposal.get("reasoning", "Terms unacceptable"),
                )

            current_terms = proposal.get("terms", current_terms)

        return NegotiationResult(
            status=NegotiationStatus.TIMEOUT,
            rounds=my_policy.max_rounds,
            history=rounds,
            reason=f"Max rounds ({my_policy.max_rounds}) reached without agreement",
        )

    async def _generate_proposal(
        self,
        contract: Contract,
        current_terms: dict[str, Any],
        policy: NegotiationPolicy,
        history: list[NegotiationRound],
        round_number: int,
    ) -> dict[str, Any]:
        """Use LLM to generate a negotiation response."""
        prompt = self._build_prompt(contract, current_terms, policy, history, round_number)

        try:
            client = self._get_client()
            if self._config.provider == "anthropic":
                response = client.messages.create(
                    model=self._config.model,
                    max_tokens=self._config.max_tokens,
                    temperature=self._config.temperature,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = response.content[0].text
            else:
                response = client.chat.completions.create(
                    model=self._config.model,
                    max_tokens=self._config.max_tokens,
                    temperature=self._config.temperature,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = response.choices[0].message.content

            return self._parse_response(text)
        except Exception as e:
            logger.error("LLM negotiation failed: %s", e)
            # Fallback: simple rule-based negotiation
            return self._rule_based_proposal(current_terms, policy, round_number)

    def _build_prompt(
        self,
        contract: Contract,
        current_terms: dict[str, Any],
        policy: NegotiationPolicy,
        history: list[NegotiationRound],
        round_number: int,
    ) -> str:
        history_text = ""
        for r in history:
            history_text += f"Round {r.round_number}: {json.dumps(r.proposed_terms)} -> {r.response}\n"

        return f"""You are an AI negotiation agent for a corporate transaction.

Contract: {contract.title}
Current proposed terms: {json.dumps(current_terms)}
Round: {round_number}

Your negotiation boundaries:
- Price range: {policy.min_price} to {policy.max_price}
- Quantity range: {policy.min_quantity} to {policy.max_quantity}
- Acceptable payment terms: {policy.acceptable_payment_terms}
- Walk away if value below: {policy.walk_away_threshold}

Previous rounds:
{history_text or "None (first round)"}

Respond with a JSON object:
{{
    "accepted": true/false,
    "walk_away": true/false,
    "terms": {{...updated terms...}},
    "reasoning": "brief explanation"
}}

Be strategic. Aim for a deal within your boundaries. Concede gradually."""

    def _parse_response(self, text: str) -> dict[str, Any]:
        """Extract JSON from LLM response."""
        try:
            # Try to find JSON in the response
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
        return {"accepted": False, "terms": {}, "reasoning": "Failed to parse LLM response"}

    def _rule_based_proposal(
        self, current_terms: dict[str, Any], policy: NegotiationPolicy, round_number: int
    ) -> dict[str, Any]:
        """Simple rule-based fallback when LLM is unavailable."""
        terms = dict(current_terms)
        price = terms.get("unit_price") or (
            terms.get("unit_price_range", [0, 0])[0] if isinstance(terms.get("unit_price_range"), (list, tuple)) else 0
        )

        if policy.max_price and policy.min_price:
            # Gradually move toward midpoint
            target = (policy.min_price + policy.max_price) / 2
            step = (target - price) / max(1, (policy.max_rounds - round_number + 1))
            new_price = price + step
            new_price = max(policy.min_price, min(policy.max_price, new_price))
            terms["unit_price"] = round(new_price, 2)

            # Accept if within acceptable range
            if policy.min_price <= price <= policy.max_price:
                return {"accepted": True, "terms": terms, "reasoning": "Price within acceptable range"}

        if policy.walk_away_threshold > 0:
            estimated = terms.get("quantity", 1) * terms.get("unit_price", 0)
            if estimated < policy.walk_away_threshold:
                return {"walk_away": True, "terms": terms, "reasoning": "Below walk-away threshold"}

        return {"accepted": False, "terms": terms, "reasoning": f"Counter-proposal round {round_number}"}
