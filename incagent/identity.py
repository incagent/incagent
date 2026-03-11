"""Corporate identity management with cryptographic signing."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from pydantic import BaseModel, Field


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

    def __init__(self) -> None:
        self._private_key = ed25519.Ed25519PrivateKey.generate()
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


def create_identity(name: str, role: str = "buyer", jurisdiction: str = "US-DE") -> tuple[CorporateIdentity, KeyPair]:
    """Create a new corporate identity with a fresh key pair."""
    kp = KeyPair()
    identity = CorporateIdentity(
        name=name,
        role=role,
        jurisdiction=jurisdiction,
        public_key_hex=kp.public_key_hex,
    )
    return identity, kp
