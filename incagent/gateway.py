"""Gateway — persistent agent runtime server (OpenClaw-inspired).

The Gateway is the always-on daemon that:
1. Hosts the agent's HTTP API for inter-agent communication
2. Manages the Heartbeat scheduler for autonomous behavior
3. Routes messages between local and remote agents
4. Exposes management endpoints (health, ledger, config)
5. Serves over HTTPS (TLS 1.3) with optional HTTP→HTTPS redirect
"""

from __future__ import annotations

import asyncio
import logging
import os
import ssl
import tempfile
from pathlib import Path
from typing import Any

from incagent.config import AgentConfig, TLSConfig

logger = logging.getLogger("incagent.gateway")


def _generate_self_signed_cert(data_dir: Path) -> tuple[str, str]:
    """Generate a self-signed TLS certificate for development.

    Returns (cert_path, key_path).
    Uses the stdlib ssl module — no external deps required.
    """
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        import datetime

        key = ec.generate_private_key(ec.SECP256R1())

        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "incagent-self-signed"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "IncAgent"),
        ])

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
            .not_valid_after(
                datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365)
            )
            .add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress_from_str("127.0.0.1")),
                    x509.IPAddress(ipaddress_from_str("0.0.0.0")),
                ]),
                critical=False,
            )
            .sign(key, hashes.SHA256())
        )

        cert_dir = data_dir / "tls"
        cert_dir.mkdir(parents=True, exist_ok=True)
        cert_path = cert_dir / "cert.pem"
        key_path = cert_dir / "key.pem"

        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            )
        )
        # Restrict key file permissions
        try:
            os.chmod(key_path, 0o600)
        except OSError:
            pass  # Windows may not support chmod

        logger.info("Self-signed TLS certificate generated: %s", cert_path)
        return str(cert_path), str(key_path)

    except ImportError:
        # Fallback: use openssl CLI if cryptography not installed
        cert_dir = data_dir / "tls"
        cert_dir.mkdir(parents=True, exist_ok=True)
        cert_path = cert_dir / "cert.pem"
        key_path = cert_dir / "key.pem"

        import subprocess
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "ec",
            "-pkeyopt", "ec_paramgen_curve:prime256v1",
            "-keyout", str(key_path),
            "-out", str(cert_path),
            "-days", "365", "-nodes",
            "-subj", "/CN=incagent-self-signed/O=IncAgent",
        ], check=True, capture_output=True)

        try:
            os.chmod(key_path, 0o600)
        except OSError:
            pass

        logger.info("Self-signed TLS certificate generated (openssl): %s", cert_path)
        return str(cert_path), str(key_path)


def ipaddress_from_str(addr: str) -> Any:
    """Convert string to ipaddress object."""
    import ipaddress
    return ipaddress.ip_address(addr)


def _create_ssl_context(tls_config: TLSConfig, data_dir: Path) -> ssl.SSLContext | None:
    """Create an SSL context from TLS config."""
    if not tls_config.enabled:
        return None

    cert_file = tls_config.cert_file
    key_file = tls_config.key_file

    # Auto-generate self-signed cert if needed
    if not cert_file and tls_config.auto_generate:
        cert_file, key_file = _generate_self_signed_cert(data_dir)
    elif not cert_file:
        logger.error("TLS enabled but no cert_file configured and auto_generate is False")
        return None

    if not os.path.exists(cert_file):
        logger.error("TLS cert file not found: %s", cert_file)
        return None
    if not os.path.exists(key_file):
        logger.error("TLS key file not found: %s", key_file)
        return None

    # Build SSL context
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)

    # Set minimum TLS version
    if tls_config.min_version == "TLSv1.3":
        ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    elif tls_config.min_version == "TLSv1.2":
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2

    ctx.load_cert_chain(cert_file, key_file)

    if tls_config.ca_file and os.path.exists(tls_config.ca_file):
        ctx.load_verify_locations(tls_config.ca_file)
        ctx.verify_mode = ssl.CERT_REQUIRED  # mTLS

    logger.info("TLS context created (min=%s)", tls_config.min_version)
    return ctx


class Gateway:
    """Persistent HTTP/HTTPS server that hosts an IncAgent and manages its lifecycle."""

    def __init__(self, agent: Any, *, host: str = "0.0.0.0", port: int = 8400) -> None:
        self.agent = agent
        self.host = host
        self.port = port
        self._server: asyncio.Server | None = None
        self._running = False

    async def start(self) -> None:
        """Start the Gateway server (HTTPS if TLS configured, otherwise HTTP)."""
        from incagent.gateway_http import create_app
        from incagent.security import SecurityConfig

        # Build SecurityConfig from agent's config
        sec_lite = self.agent._config.security
        sec = SecurityConfig(
            api_keys=sec_lite.api_keys,
            require_auth=sec_lite.require_auth,
            allowed_origins=sec_lite.allowed_origins,
            rate_limit_per_minute=sec_lite.rate_limit_per_minute,
            tool_denylist=sec_lite.tool_denylist,
            allow_tool_creation_via_api=sec_lite.allow_tool_creation_via_api,
            allow_self_improve_via_api=sec_lite.allow_self_improve_via_api,
            audit_log_path=self.agent._config.data_dir / "audit.db",
        )

        app = create_app(self, security=sec)
        self._running = True

        # Start heartbeat if configured
        if hasattr(self.agent, '_heartbeat') and self.agent._heartbeat:
            asyncio.create_task(self.agent._heartbeat.run(self.agent))

        # TLS setup
        tls_config = self.agent._config.tls
        ssl_context = _create_ssl_context(tls_config, self.agent._config.data_dir)

        protocol = "HTTPS" if ssl_context else "HTTP"
        logger.info(
            "Gateway started: %s (%s) listening on %s:%d (%s)",
            self.agent.name, self.agent.agent_id, self.host, self.port, protocol,
        )

        import uvicorn

        # If HTTPS + HTTP redirect enabled, start redirect server in background
        if ssl_context and tls_config.redirect_http:
            redirect_app = _create_redirect_app(self.host, self.port)
            redirect_config = uvicorn.Config(
                redirect_app,
                host=self.host,
                port=tls_config.redirect_http_port,
                log_level="warning",
            )
            redirect_server = uvicorn.Server(redirect_config)
            asyncio.create_task(redirect_server.serve())
            logger.info(
                "HTTP→HTTPS redirect: :%d → :%d",
                tls_config.redirect_http_port, self.port,
            )

        # Start main server
        config = uvicorn.Config(
            app,
            host=self.host,
            port=self.port,
            log_level="info",
            ssl_certfile=tls_config.cert_file or None,
            ssl_keyfile=tls_config.key_file or None,
            **({"ssl": ssl_context} if ssl_context else {}),
        )
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


def _create_redirect_app(https_host: str, https_port: int) -> Any:
    """Create a minimal ASGI app that redirects all HTTP requests to HTTPS."""
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import RedirectResponse
    from starlette.routing import Route

    async def redirect_to_https(request: Request) -> RedirectResponse:
        url = request.url
        # Replace scheme and port
        target = str(url).replace("http://", "https://", 1)
        # Replace port if non-standard
        if f":{request.url.port}" in target:
            target = target.replace(f":{request.url.port}", f":{https_port}", 1)
        return RedirectResponse(url=target, status_code=301)

    return Starlette(routes=[
        Route("/{path:path}", redirect_to_https, methods=["GET", "POST", "PUT", "DELETE", "PATCH"]),
        Route("/", redirect_to_https),
    ])
