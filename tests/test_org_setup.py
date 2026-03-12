"""Tests for organization setup, identity persistence, and per-org data isolation."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from incagent.identity import (
    CorporateIdentity,
    KeyPair,
    _org_id,
    init_org,
    org_data_dir,
)


class TestOrgId:
    def test_deterministic(self):
        """Same name always produces same org_id."""
        assert _org_id("Acme Corp") == _org_id("Acme Corp")

    def test_different_names(self):
        """Different names produce different org_ids."""
        assert _org_id("Acme Corp") != _org_id("Beta Inc")

    def test_format_uuid_like(self):
        """org_id looks like a UUID (8-4-4-4-12)."""
        oid = _org_id("Test Corp")
        parts = oid.split("-")
        assert len(parts) == 5
        assert len(parts[0]) == 8
        assert len(parts[4]) == 12


class TestOrgDataDir:
    def test_returns_path(self):
        base = Path("/tmp/incagent")
        d = org_data_dir(base, "My Corp")
        assert d.parent == base
        assert _org_id("My Corp") in str(d)

    def test_deterministic(self):
        base = Path("/tmp/incagent")
        assert org_data_dir(base, "X") == org_data_dir(base, "X")


class TestKeyPairPersistence:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_save_and_load(self):
        """Key pair can be saved and loaded."""
        kp = KeyPair()
        path = Path(self._tmp) / "key.pem"
        kp.save(path)
        assert path.exists()

        loaded = KeyPair.load(path)
        assert loaded.public_key_hex == kp.public_key_hex

    def test_sign_verify_after_reload(self):
        """Signatures made with reloaded keys are valid."""
        kp = KeyPair()
        path = Path(self._tmp) / "key.pem"
        kp.save(path)

        loaded = KeyPair.load(path)
        data = b"test message"
        sig = loaded.sign(data)
        assert KeyPair.verify(loaded.public_key_hex, data, sig)


class TestInitOrg:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.base = Path(self._tmp)

    def teardown_method(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_creates_directory_structure(self):
        """init_org creates all required subdirectories."""
        identity, kp, data_dir = init_org(self.base, "Acme Corp")

        assert data_dir.exists()
        assert (data_dir / "identity.json").exists()
        assert (data_dir / "key.pem").exists()
        assert (data_dir / "skills").is_dir()
        assert (data_dir / "tools").is_dir()
        assert (data_dir / "reports").is_dir()

    def test_identity_has_deterministic_id(self):
        """agent_id is deterministic, not random."""
        identity, _, _ = init_org(self.base, "Acme Corp")
        expected_id = _org_id("Acme Corp")
        assert identity.agent_id == expected_id

    def test_idempotent(self):
        """Calling init_org twice returns the same identity."""
        id1, kp1, d1 = init_org(self.base, "Acme Corp")
        id2, kp2, d2 = init_org(self.base, "Acme Corp")

        assert id1.agent_id == id2.agent_id
        assert kp1.public_key_hex == kp2.public_key_hex
        assert d1 == d2

    def test_different_orgs_isolated(self):
        """Different orgs get different directories."""
        _, _, d1 = init_org(self.base, "Acme Corp")
        _, _, d2 = init_org(self.base, "Beta Inc")

        assert d1 != d2
        assert d1.parent == d2.parent == self.base

    def test_identity_persisted_as_json(self):
        """identity.json contains valid, loadable data."""
        identity, _, data_dir = init_org(self.base, "Test Org")
        raw = json.loads((data_dir / "identity.json").read_text(encoding="utf-8"))
        assert raw["name"] == "Test Org"
        assert raw["agent_id"] == _org_id("Test Org")
        assert raw["role"] == "buyer"


class TestAgentOrgIntegration:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_agent_uses_persistent_id(self):
        """IncAgent uses org_id, not random UUID."""
        from incagent.agent import IncAgent

        agent = IncAgent(name="Persistent Corp", role="buyer", data_dir=self._tmp)
        expected_id = _org_id("Persistent Corp")
        assert agent.agent_id == expected_id
        agent.close()

    def test_agent_reloads_same_identity(self):
        """Two IncAgent instances with same name share identity."""
        from incagent.agent import IncAgent

        a1 = IncAgent(name="Reload Corp", role="buyer", data_dir=self._tmp)
        id1 = a1.agent_id
        pk1 = a1.identity.public_key_hex
        a1.close()

        a2 = IncAgent(name="Reload Corp", role="buyer", data_dir=self._tmp)
        assert a2.agent_id == id1
        assert a2.identity.public_key_hex == pk1
        a2.close()

    def test_agent_data_in_org_dir(self):
        """Agent databases are in the per-org directory."""
        from incagent.agent import IncAgent

        agent = IncAgent(name="Dir Corp", role="buyer", data_dir=self._tmp)
        org_dir = org_data_dir(Path(self._tmp), "Dir Corp")

        assert agent._config.data_dir == org_dir
        assert (org_dir / "ledger.db").exists()
        assert (org_dir / "memory.db").exists()
        agent.close()

    def test_different_agents_isolated(self):
        """Two different agent names have isolated data."""
        from incagent.agent import IncAgent

        a1 = IncAgent(name="Alpha Corp", role="buyer", data_dir=self._tmp)
        a2 = IncAgent(name="Beta Corp", role="seller", data_dir=self._tmp)

        assert a1.agent_id != a2.agent_id
        assert a1._config.data_dir != a2._config.data_dir

        # Ledger entries don't leak between orgs
        a1._ledger.append(a1.agent_id, "test_alpha", {"x": 1})
        entries = a2._ledger.query(agent_id=a1.agent_id)
        assert len(entries) == 0  # a2's ledger doesn't have a1's data

        a1.close()
        a2.close()
