"""Security module — authentication, rate limiting, input validation, audit.

This is the central security layer for IncAgent:
- API key authentication (HMAC-SHA256 signed requests)
- Per-IP and per-key rate limiting
- Input validation and sanitization
- Code execution sandboxing rules
- Peer-to-peer message signing and verification
- Immutable audit logging
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("incagent.security")


# ── Configuration ─────────────────────────────────────────────────────

class SecurityConfig(BaseModel):
    """Security configuration for the agent."""

    # API authentication
    api_keys: list[str] = Field(default_factory=list, description="Allowed API keys (HMAC secrets)")
    require_auth: bool = Field(default=True, description="Require authentication on all endpoints")
    public_endpoints: list[str] = Field(
        default_factory=lambda: ["/health", "/identity", "/metrics"],
        description="Endpoints accessible without auth",
    )

    # Rate limiting
    rate_limit_per_minute: int = Field(default=60, ge=1, description="Max requests per minute per IP")
    rate_limit_burst: int = Field(default=10, ge=1, description="Max burst requests")

    # CORS
    allowed_origins: list[str] = Field(
        default_factory=list,
        description="Allowed CORS origins (empty = none)",
    )

    # Tool execution
    tool_allowlist: list[str] = Field(
        default_factory=list,
        description="If non-empty, only these tools can be executed via API",
    )
    tool_denylist: list[str] = Field(
        default_factory=lambda: ["shell_exec"],
        description="Tools that cannot be executed via API",
    )
    allow_tool_creation_via_api: bool = Field(
        default=False,
        description="Whether POST /tools (create) is allowed via API",
    )
    allow_self_improve_via_api: bool = Field(
        default=False,
        description="Whether POST /improve is allowed via API",
    )

    # Code sandbox
    blocked_imports: list[str] = Field(
        default_factory=lambda: [
            "subprocess", "os.system", "shutil.rmtree", "ctypes",
            "importlib", "pickle", "marshal", "shelve",
            "__import__", "eval", "exec", "compile",
            "socket", "http.server", "xmlrpc",
        ],
        description="Imports blocked in dynamically created tools",
    )

    # Peer verification
    require_peer_signature: bool = Field(
        default=False,
        description="Require HMAC signature on peer messages",
    )
    peer_message_max_age_seconds: int = Field(
        default=300,
        description="Max age of peer messages before rejection (replay protection)",
    )

    # Audit
    audit_log_path: Path | None = Field(
        default=None,
        description="Path to immutable audit log (SQLite)",
    )


# ── API Key Authentication ────────────────────────────────────────────

def generate_api_key() -> str:
    """Generate a cryptographically secure API key."""
    return f"inc_{secrets.token_urlsafe(32)}"


def hash_api_key(key: str) -> str:
    """Hash an API key for storage (never store raw keys)."""
    return hashlib.sha256(key.encode()).hexdigest()


def verify_api_key(provided: str, stored_hashes: list[str]) -> bool:
    """Verify an API key against stored hashes."""
    h = hash_api_key(provided)
    return any(hmac.compare_digest(h, stored) for stored in stored_hashes)


# ── HMAC Request Signing ──────────────────────────────────────────────

def sign_request(body: bytes, secret: str, timestamp: str | None = None) -> dict[str, str]:
    """Sign a request body with HMAC-SHA256.

    Returns headers to include in the request:
      X-IncAgent-Timestamp: ISO timestamp
      X-IncAgent-Signature: HMAC hex digest
    """
    ts = timestamp or datetime.now(timezone.utc).isoformat()
    message = f"{ts}.{body.decode('utf-8', errors='replace')}"
    sig = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    return {
        "X-IncAgent-Timestamp": ts,
        "X-IncAgent-Signature": sig,
    }


def verify_request_signature(
    body: bytes,
    timestamp: str,
    signature: str,
    secret: str,
    max_age_seconds: int = 300,
) -> bool:
    """Verify HMAC signature of an incoming request.

    Also checks timestamp freshness to prevent replay attacks.
    """
    # Check timestamp freshness
    try:
        ts = datetime.fromisoformat(timestamp)
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        if abs(age) > max_age_seconds:
            logger.warning("Request signature expired: age=%.0fs max=%ds", age, max_age_seconds)
            return False
    except (ValueError, TypeError):
        logger.warning("Invalid timestamp in request signature")
        return False

    # Verify HMAC
    message = f"{timestamp}.{body.decode('utf-8', errors='replace')}"
    expected = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


# ── Rate Limiter ──────────────────────────────────────────────────────

class RateLimiter:
    """Token bucket rate limiter per client (IP or API key)."""

    def __init__(self, max_per_minute: int = 60, burst: int = 10) -> None:
        self._max_per_minute = max_per_minute
        self._burst = burst
        self._tokens: dict[str, float] = defaultdict(lambda: float(burst))
        self._last_refill: dict[str, float] = defaultdict(time.monotonic)

    def allow(self, client_id: str) -> bool:
        """Check if request is allowed. Returns False if rate limited."""
        now = time.monotonic()
        elapsed = now - self._last_refill[client_id]
        self._last_refill[client_id] = now

        # Refill tokens
        refill = elapsed * (self._max_per_minute / 60.0)
        self._tokens[client_id] = min(
            float(self._burst),
            self._tokens[client_id] + refill,
        )

        if self._tokens[client_id] >= 1.0:
            self._tokens[client_id] -= 1.0
            return True
        return False

    def cleanup(self, max_age: float = 3600.0) -> None:
        """Remove stale entries to prevent memory leak."""
        now = time.monotonic()
        stale = [k for k, v in self._last_refill.items() if now - v > max_age]
        for k in stale:
            self._tokens.pop(k, None)
            self._last_refill.pop(k, None)


# ── Input Validation ──────────────────────────────────────────────────

class InputValidator:
    """Validates and sanitizes input to prevent injection attacks."""

    # Patterns for validating structured identifiers (names, IDs).
    NAME_DANGEROUS_PATTERNS = [
        r"\.\./",           # path traversal
        r"\\\.\\.",         # windows path traversal
        r"[;&|`$]",        # shell metacharacters
        r"<script",         # XSS
        r"javascript:",     # XSS
        r"\x00",           # null byte
    ]

    # Patterns for validating free-text content (skills, descriptions).
    # More permissive than NAME patterns — allows |, $, etc. that appear in Markdown.
    CONTENT_DANGEROUS_PATTERNS = [
        r"\.\./",           # path traversal
        r"<script",         # XSS
        r"javascript:",     # XSS
        r"\x00",           # null byte
        r";\s*(rm|del|drop)\s",  # command injection
        r"`[^`]*\beval\b",      # eval in backticks
    ]

    @classmethod
    def sanitize_name(cls, name: str, max_length: int = 64) -> str | None:
        """Sanitize a tool/skill name. Returns None if invalid."""
        if not name or len(name) > max_length:
            return None

        # Only allow alphanumeric, underscore, hyphen
        cleaned = re.sub(r"[^a-zA-Z0-9_\-]", "", name)
        if not cleaned or cleaned != name.strip():
            return None
        return cleaned

    @classmethod
    def validate_no_injection(cls, text: str) -> list[str]:
        """Check free-text content for injection patterns.

        Uses CONTENT_DANGEROUS_PATTERNS which is more permissive than
        NAME patterns — Markdown pipe tables, dollar amounts, etc. are fine.
        """
        violations = []
        for pattern in cls.CONTENT_DANGEROUS_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                violations.append(f"Dangerous pattern detected: {pattern}")
        return violations

    @classmethod
    def validate_name_no_injection(cls, text: str) -> list[str]:
        """Check identifier/name for injection patterns (strict)."""
        violations = []
        for pattern in cls.NAME_DANGEROUS_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                violations.append(f"Dangerous pattern in name: {pattern}")
        return violations

    @classmethod
    def validate_json_body(cls, body: dict[str, Any], max_depth: int = 5) -> list[str]:
        """Validate JSON body for excessive nesting and size."""
        violations = []

        def _check_depth(obj: Any, depth: int) -> None:
            if depth > max_depth:
                violations.append(f"JSON nesting too deep (max {max_depth})")
                return
            if isinstance(obj, dict):
                for v in obj.values():
                    _check_depth(v, depth + 1)
            elif isinstance(obj, list):
                for v in obj:
                    _check_depth(v, depth + 1)

        _check_depth(body, 0)

        # Check total serialized size
        try:
            serialized = json.dumps(body)
            if len(serialized) > 1_000_000:  # 1MB limit
                violations.append("Request body too large (max 1MB)")
        except (TypeError, ValueError):
            violations.append("Invalid JSON body")

        return violations


# ── Code Sandbox ──────────────────────────────────────────────────────

class CodeSandbox:
    """Validates dynamically generated code before execution.

    This prevents malicious code injection via LLM-generated tools or
    skill.md files that trick the agent into creating dangerous tools.
    """

    def __init__(self, blocked_imports: list[str] | None = None) -> None:
        self._blocked = blocked_imports or SecurityConfig().blocked_imports

    def validate(self, code: str) -> list[str]:
        """Analyze code for dangerous patterns. Returns violations."""
        violations = []

        # Check blocked imports
        for blocked in self._blocked:
            # Match various import forms
            patterns = [
                rf"import\s+{re.escape(blocked)}",
                rf"from\s+{re.escape(blocked)}\s+import",
                rf"__import__\s*\(\s*['\"].*{re.escape(blocked)}",
            ]
            for p in patterns:
                if re.search(p, code):
                    violations.append(f"Blocked import: {blocked}")
                    break

        # Check for dangerous builtins used directly
        dangerous_calls = [
            (r"\beval\s*\(", "eval() call"),
            (r"\bexec\s*\(", "exec() call"),
            (r"\bcompile\s*\(", "compile() call"),
            (r"\b__import__\s*\(", "__import__() call"),
            (r"\bgetattr\s*\(\s*__builtins__", "builtins access"),
            (r"\bglobals\s*\(\s*\)", "globals() access"),
            (r"\bos\.system\s*\(", "os.system() call"),
            (r"\bos\.popen\s*\(", "os.popen() call"),
            (r"\bos\.exec", "os.exec*() call"),
            (r"\bsubprocess\.", "subprocess usage"),
            (r"\bopen\s*\([^)]*,\s*['\"]w", "file write via open()"),
        ]
        for pattern, desc in dangerous_calls:
            if re.search(pattern, code):
                violations.append(f"Dangerous call: {desc}")

        # Check for network operations
        network_patterns = [
            (r"\bsocket\.", "Raw socket access"),
            (r"\brequests\.", "HTTP requests (use http_api tool instead)"),
            (r"\burllib\.", "URL operations"),
            (r"\bhttp\.client\.", "HTTP client"),
        ]
        for pattern, desc in network_patterns:
            if re.search(pattern, code):
                violations.append(f"Network operation: {desc}")

        # Check for file system operations outside tool scope
        fs_patterns = [
            (r"\bshutil\.rmtree", "Recursive directory deletion"),
            (r"\bos\.remove\s*\(", "File deletion"),
            (r"\bos\.unlink\s*\(", "File deletion"),
            (r"\bPathlib.*unlink", "File deletion via pathlib"),
        ]
        for pattern, desc in fs_patterns:
            if re.search(pattern, code):
                violations.append(f"File system operation: {desc}")

        # Size check
        if len(code) > 50_000:
            violations.append("Code too large (max 50KB)")

        # Must actually define a BaseTool subclass
        if not re.search(r"class\s+\w+\s*\(\s*BaseTool\s*\)", code):
            violations.append("Must define a class inheriting from BaseTool")

        return violations


# ── Audit Logger ──────────────────────────────────────────────────────

class AuditLogger:
    """Append-only audit log stored in SQLite with integrity hashing.

    Every entry includes a SHA-256 chain hash linking it to the previous
    entry, making tampering detectable.
    """

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=FULL")
        self._init_db()
        self._last_hash = self._get_last_hash()

    def _init_db(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor TEXT NOT NULL,
                target TEXT,
                details TEXT,
                ip_address TEXT,
                chain_hash TEXT NOT NULL,
                UNIQUE(id, chain_hash)
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_event ON audit_log(event_type)
        """)
        self._conn.commit()

    def _get_last_hash(self) -> str:
        row = self._conn.execute(
            "SELECT chain_hash FROM audit_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else "genesis"

    def _compute_hash(self, prev_hash: str, event_type: str, actor: str, details: str) -> str:
        payload = f"{prev_hash}|{event_type}|{actor}|{details}"
        return hashlib.sha256(payload.encode()).hexdigest()

    def log(
        self,
        event_type: str,
        actor: str,
        target: str = "",
        details: str = "",
        ip_address: str = "",
    ) -> None:
        """Append an audit entry. This is append-only; entries cannot be modified."""
        ts = datetime.now(timezone.utc).isoformat()
        chain_hash = self._compute_hash(self._last_hash, event_type, actor, details)

        self._conn.execute(
            """INSERT INTO audit_log (timestamp, event_type, actor, target, details, ip_address, chain_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (ts, event_type, actor, target, details, ip_address, chain_hash),
        )
        self._conn.commit()
        self._last_hash = chain_hash

    def verify_chain(self) -> tuple[bool, int]:
        """Verify the integrity of the entire audit chain.

        Returns (is_valid, last_valid_id).
        """
        rows = self._conn.execute(
            "SELECT id, event_type, actor, details, chain_hash FROM audit_log ORDER BY id"
        ).fetchall()

        prev_hash = "genesis"
        last_valid = 0
        for row_id, event_type, actor, details, stored_hash in rows:
            expected = self._compute_hash(prev_hash, event_type, actor, details)
            if not hmac.compare_digest(expected, stored_hash):
                logger.error("Audit chain broken at id=%d", row_id)
                return False, last_valid
            prev_hash = stored_hash
            last_valid = row_id

        return True, last_valid

    def query(
        self,
        event_type: str | None = None,
        actor: str | None = None,
        since: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query audit log entries."""
        sql = "SELECT id, timestamp, event_type, actor, target, details, ip_address FROM audit_log WHERE 1=1"
        params: list[Any] = []

        if event_type:
            sql += " AND event_type = ?"
            params.append(event_type)
        if actor:
            sql += " AND actor = ?"
            params.append(actor)
        if since:
            sql += " AND timestamp >= ?"
            params.append(since)

        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        return [
            {
                "id": r[0], "timestamp": r[1], "event_type": r[2],
                "actor": r[3], "target": r[4], "details": r[5],
                "ip_address": r[6],
            }
            for r in rows
        ]

    def close(self) -> None:
        self._conn.close()


# ── Shell Command Sandbox ─────────────────────────────────────────────

SHELL_BLOCKED_PATTERNS = [
    # Destructive
    r"rm\s+-rf\s+/",
    r"rm\s+-rf\s+~",
    r"rm\s+-rf\s+\*",
    r"mkfs\b",
    r"dd\s+if=",
    r":\(\)\s*\{",  # fork bomb
    r">\s*/dev/sd",
    r"chmod\s+-R\s+777\s+/",

    # Data exfiltration
    r"\bcurl\b.*\|\s*bash",
    r"\bwget\b.*\|\s*bash",
    r"\bnc\s+-",           # netcat
    r"\bncat\b",
    r"\bsocat\b",

    # Reverse shells
    r"/dev/tcp/",
    r"bash\s+-i\s+>&",
    r"python.*socket.*connect",
    r"perl.*socket.*INET",

    # Credential theft
    r"cat.*/etc/shadow",
    r"cat.*/etc/passwd",
    r"cat.*\.ssh/",
    r"cat.*\.env",
    r"cat.*\.aws/credentials",
    r"cat.*\.kube/config",

    # Crypto mining
    r"xmrig",
    r"minerd",
    r"cryptonight",

    # Privilege escalation
    r"\bsudo\b",
    r"\bsu\s+-",
    r"\bchmod\s+[46]755\s+/",
    r"\bchown\s+root",

    # Process manipulation
    r"kill\s+-9\s+1\b",
    r"killall\b",
    r"pkill\b.*-9",

    # System modification
    r"\bsystemctl\b",
    r"\bservice\b",
    r"\bcrontab\b",
    r"\bat\s+-f",
]

SHELL_ALLOWED_COMMANDS: list[str] = [
    # Only these command prefixes are allowed when in strict mode
    "echo", "cat", "head", "tail", "grep", "awk", "sed", "sort", "uniq",
    "wc", "date", "whoami", "pwd", "ls", "find", "python", "pip",
    "node", "npm", "git", "curl", "jq",
]


def validate_shell_command(command: str, strict: bool = False) -> list[str]:
    """Validate a shell command against security rules.

    Args:
        command: The shell command to validate
        strict: If True, only allow commands from the allowlist

    Returns:
        List of violations (empty = safe)
    """
    violations = []

    for pattern in SHELL_BLOCKED_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            violations.append(f"Blocked pattern: {pattern}")

    if strict:
        # In strict mode, the first word must be in the allowlist
        first_cmd = command.strip().split()[0] if command.strip() else ""
        # Handle paths like /usr/bin/python
        base_cmd = first_cmd.rsplit("/", 1)[-1] if "/" in first_cmd else first_cmd
        if base_cmd not in SHELL_ALLOWED_COMMANDS:
            violations.append(f"Command not in allowlist: {base_cmd}")

    # Check for pipe to dangerous commands
    if "|" in command:
        parts = command.split("|")
        for part in parts[1:]:
            stripped = part.strip().split()[0] if part.strip() else ""
            if stripped in ("bash", "sh", "zsh", "python", "perl", "ruby", "node"):
                violations.append(f"Pipe to interpreter: {stripped}")

    return violations


# ── Peer Message Verification ─────────────────────────────────────────

def sign_peer_message(payload: dict[str, Any], private_key_hex: str) -> dict[str, str]:
    """Sign a peer-to-peer message.

    Adds timestamp and HMAC signature to prevent tampering and replay.
    """
    ts = datetime.now(timezone.utc).isoformat()
    body = json.dumps(payload, sort_keys=True, default=str)
    return sign_request(body.encode(), private_key_hex, ts)


def verify_peer_message(
    payload: dict[str, Any],
    timestamp: str,
    signature: str,
    peer_secret: str,
    max_age: int = 300,
) -> bool:
    """Verify a signed peer message."""
    body = json.dumps(payload, sort_keys=True, default=str)
    return verify_request_signature(body.encode(), timestamp, signature, peer_secret, max_age)
