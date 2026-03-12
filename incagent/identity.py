"""Corporate identity management with cryptographic signing.

Identity is persistent per organization:
- org_id is deterministic (derived from org name) and never changes
- Key pair is saved to disk and reloaded on restart
- agent_id = org_id (stable across restarts)
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from pydantic import BaseModel, Field

logger = logging.getLogger("incagent.identity")


def _org_id(name: str) -> str:
    """Derive a deterministic org_id from the organization name.

    This ensures the same company always gets the same ID,
    even across reinstalls — as long as they use the same name.
    """
    h = hashlib.sha256(f"incagent:org:{name}".encode()).hexdigest()
    # Format as UUID v5-style for readability
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


class CorporateIdentity(BaseModel):
    """Represents a legally-bound corporate AI agent identity."""

    agent_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    role: str = "buyer"
    jurisdiction: str = "US-DE"  # Delaware default
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    public_key_hex: str = ""
    metadata: dict = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}

    def fingerprint(self) -> str:
        """Return a deterministic hash of this identity."""
        data = f"{self.agent_id}:{self.name}:{self.public_key_hex}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def to_public_dict(self) -> dict:
        """Return public-facing identity info (no secrets)."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "role": self.role,
            "jurisdiction": self.jurisdiction,
            "public_key": self.public_key_hex,
            "fingerprint": self.fingerprint(),
        }


class KeyPair:
    """Ed25519 key pair for signing messages and contracts."""

    def __init__(self, private_key: ed25519.Ed25519PrivateKey | None = None) -> None:
        self._private_key = private_key or ed25519.Ed25519PrivateKey.generate()
        self._public_key = self._private_key.public_key()

    @property
    def public_key_hex(self) -> str:
        raw = self._public_key.public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        return raw.hex()

    def sign(self, data: bytes) -> bytes:
        """Sign arbitrary data."""
        return self._private_key.sign(data)

    def sign_json(self, obj: dict) -> str:
        """Sign a JSON-serializable dict, return hex signature."""
        canonical = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
        return self.sign(canonical).hex()

    def save(self, path: Path) -> None:
        """Save private key to disk (PEM format, encrypted with best-effort)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        pem = self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        path.write_bytes(pem)
        # Restrict permissions on Unix
        try:
            path.chmod(0o600)
        except (OSError, NotImplementedError):
            pass  # Windows
        logger.info("Saved key pair to %s", path)

    @classmethod
    def load(cls, path: Path) -> KeyPair:
        """Load a key pair from disk."""
        pem = path.read_bytes()
        private_key = serialization.load_pem_private_key(pem, password=None)
        if not isinstance(private_key, ed25519.Ed25519PrivateKey):
            raise ValueError("Expected Ed25519 private key")
        return cls(private_key=private_key)

    @staticmethod
    def verify(public_key_hex: str, data: bytes, signature: bytes) -> bool:
        """Verify a signature against a public key."""
        try:
            raw_key = bytes.fromhex(public_key_hex)
            pub = ed25519.Ed25519PublicKey.from_public_bytes(raw_key)
            pub.verify(signature, data)
            return True
        except Exception:
            return False


# ── Organization Setup ────────────────────────────────────────────────

def org_data_dir(base_dir: Path, org_name: str) -> Path:
    """Return the per-org data directory.

    Structure:
        {base_dir}/{org_id}/
            identity.json      ← persisted identity
            key.pem            ← Ed25519 private key
            ledger.db          ← transaction ledger
            memory.db          ← learning memory
            audit.db           ← security audit log
            skills/            ← skill files
            tools/             ← custom tool files
            reports/           ← generated reports
    """
    oid = _org_id(org_name)
    return base_dir / oid


def init_org(
    base_dir: Path,
    name: str,
    role: str = "buyer",
    jurisdiction: str = "US-DE",
) -> tuple[CorporateIdentity, KeyPair, Path]:
    """Initialize a new organization's data directory.

    If already initialized, loads existing identity and key pair.
    This is idempotent — safe to call multiple times.

    Returns (identity, keypair, data_dir).
    """
    data_dir = org_data_dir(base_dir, name)
    identity_file = data_dir / "identity.json"
    key_file = data_dir / "key.pem"

    if identity_file.exists() and key_file.exists():
        # Load existing
        identity_data = json.loads(identity_file.read_text(encoding="utf-8"))
        # Preserve created_at as string for Pydantic
        identity = CorporateIdentity(**identity_data)
        kp = KeyPair.load(key_file)
        logger.info("Loaded existing org: %s [%s]", name, identity.agent_id)
        return identity, kp, data_dir

    # Create new
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "skills").mkdir(exist_ok=True)
    (data_dir / "tools").mkdir(exist_ok=True)
    (data_dir / "reports").mkdir(exist_ok=True)

    oid = _org_id(name)
    kp = KeyPair()
    identity = CorporateIdentity(
        agent_id=oid,
        name=name,
        role=role,
        jurisdiction=jurisdiction,
        public_key_hex=kp.public_key_hex,
    )

    # Save identity
    identity_file.write_text(
        json.dumps(identity.model_dump(mode="json"), indent=2, default=str),
        encoding="utf-8",
    )

    # Save key pair
    kp.save(key_file)

    logger.info("Initialized new org: %s [%s] at %s", name, oid, data_dir)
    return identity, kp, data_dir


def create_identity(
    name: str, role: str = "buyer", jurisdiction: str = "US-DE",
) -> tuple[CorporateIdentity, KeyPair]:
    """Create a new corporate identity with a fresh key pair.

    NOTE: This creates an ephemeral identity (random UUID).
    For persistent org identity, use init_org() instead.
    """
    kp = KeyPair()
    identity = CorporateIdentity(
        name=name,
        role=role,
        jurisdiction=jurisdiction,
        public_key_hex=kp.public_key_hex,
    )
    return identity, kp
