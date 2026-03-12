"""IncAgent configuration management."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class ResilienceConfig(BaseModel):
    """Configuration for self-healing behavior."""

    max_retries: int = Field(default=5, ge=1, le=50)
    backoff_base: float = Field(default=2.0, gt=1.0)
    backoff_max: float = Field(default=60.0, gt=0)
    circuit_breaker_threshold: int = Field(default=3, ge=1)
    circuit_breaker_reset_seconds: float = Field(default=30.0, gt=0)
    fallback_strategy: Literal["cache", "default", "skip"] = "cache"


class ApprovalConfig(BaseModel):
    """Configuration for human-in-the-loop approval."""

    enabled: bool = True
    threshold: float = Field(default=10000.0, ge=0, description="Amount above which human approval is required")
    method: Literal["cli", "webhook", "slack"] = "cli"
    webhook_url: str | None = None
    slack_channel: str | None = None
    timeout_seconds: float = Field(default=3600.0, gt=0, description="Timeout waiting for human approval")
    auto_approve_below_threshold: bool = True


class LLMConfig(BaseModel):
    """Configuration for LLM-powered negotiation."""

    provider: Literal["anthropic", "openai"] = "anthropic"
    model: str = "claude-sonnet-4-20250514"
    api_key: str | None = None
    max_tokens: int = 1024
    temperature: float = 0.7


class SecurityConfigLite(BaseModel):
    """Security settings embedded in AgentConfig.

    For full SecurityConfig, see incagent.security module.
    """

    api_keys: list[str] = Field(default_factory=list, description="Allowed API keys")
    require_auth: bool = Field(default=True, description="Require auth on non-public endpoints")
    allowed_origins: list[str] = Field(default_factory=list, description="CORS allowed origins")
    rate_limit_per_minute: int = Field(default=60, ge=1)
    tool_denylist: list[str] = Field(
        default_factory=lambda: ["shell_exec"],
        description="Tools blocked from API access",
    )
    allow_tool_creation_via_api: bool = False
    allow_self_improve_via_api: bool = False


class TLSConfig(BaseModel):
    """TLS/HTTPS configuration for the Gateway."""

    enabled: bool = Field(default=False, description="Enable HTTPS (TLS 1.3)")
    cert_file: str = Field(default="", description="Path to TLS certificate (PEM)")
    key_file: str = Field(default="", description="Path to TLS private key (PEM)")
    ca_file: str = Field(default="", description="Path to CA bundle (optional, for mTLS)")
    auto_generate: bool = Field(
        default=False,
        description="Auto-generate self-signed cert if cert_file is empty",
    )
    redirect_http: bool = Field(
        default=True,
        description="Start HTTP listener that redirects to HTTPS",
    )
    redirect_http_port: int = Field(default=8080, ge=1, le=65535)
    min_version: str = Field(default="TLSv1.3", description="Minimum TLS version")


class AgentConfig(BaseModel):
    """Top-level agent configuration."""

    name: str
    role: Literal["buyer", "seller", "broker"] = "buyer"
    host: str = "0.0.0.0"
    port: int = 8400
    data_dir: Path = Field(default_factory=lambda: Path.home() / ".incagent")
    resilience: ResilienceConfig = Field(default_factory=ResilienceConfig)
    approval: ApprovalConfig = Field(default_factory=ApprovalConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    security: SecurityConfigLite = Field(default_factory=SecurityConfigLite)
    tls: TLSConfig = Field(default_factory=TLSConfig)
    autonomous_mode: bool = Field(default=False, description="If True, skip all human approvals")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
