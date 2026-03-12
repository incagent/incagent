"""End-to-end tests: two Gateway agents communicating over real HTTP."""

import asyncio
import tempfile
import time
from pathlib import Path

import httpx
import pytest
import uvicorn

from incagent import IncAgent, HeartbeatConfig
from incagent.gateway_http import create_app
from incagent.gateway import Gateway
from incagent.registry import PeerAgent


@pytest.fixture
def data_dirs():
    """Create temp data directories for test agents."""
    d1 = tempfile.mkdtemp()
    d2 = tempfile.mkdtemp()
    return d1, d2


@pytest.fixture
def skills_dir():
    return Path(__file__).resolve().parent.parent / "skills"


class TestE2EGateway:
    """Test two agents communicating over HTTP."""

    @pytest.fixture(autouse=True)
    async def setup_agents(self, data_dirs, skills_dir):
        """Start two agent Gateways on different ports."""
        d1, d2 = data_dirs

        self.buyer = IncAgent(
            name="E2E Buyer",
            role="buyer",
            port=18401,
            autonomous_mode=True,
            skills_dir=skills_dir,
            data_dir=d1,
        )
        self.seller = IncAgent(
            name="E2E Seller",
            role="seller",
            port=18402,
            autonomous_mode=True,
            skills_dir=skills_dir,
            data_dir=d2,
        )

        # Create ASGI apps
        gw_buyer = Gateway(self.buyer, port=18401)
        gw_seller = Gateway(self.seller, port=18402)
        app_buyer = create_app(gw_buyer)
        app_seller = create_app(gw_seller)
        gw_buyer._running = True
        gw_seller._running = True

        # Start servers
        config_b = uvicorn.Config(app_buyer, host="127.0.0.1", port=18401, log_level="error")
        config_s = uvicorn.Config(app_seller, host="127.0.0.1", port=18402, log_level="error")
        self.server_b = uvicorn.Server(config_b)
        self.server_s = uvicorn.Server(config_s)

        self.task_b = asyncio.create_task(self.server_b.serve())
        self.task_s = asyncio.create_task(self.server_s.serve())

        # Wait for servers to start
        for _ in range(50):
            try:
                async with httpx.AsyncClient() as c:
                    await c.get("http://127.0.0.1:18401/health", timeout=1.0)
                    await c.get("http://127.0.0.1:18402/health", timeout=1.0)
                break
            except Exception:
                await asyncio.sleep(0.1)

        yield

        # Cleanup
        self.server_b.should_exit = True
        self.server_s.should_exit = True
        await asyncio.sleep(0.2)
        self.task_b.cancel()
        self.task_s.cancel()
        self.buyer.close()
        self.seller.close()

    async def test_health_endpoint(self):
        """Both agents respond to /health."""
        async with httpx.AsyncClient() as client:
            r1 = await client.get("http://127.0.0.1:18401/health")
            r2 = await client.get("http://127.0.0.1:18402/health")

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["name"] == "E2E Buyer"
        assert r2.json()["name"] == "E2E Seller"
        assert r1.json()["state"] == "idle"

    async def test_identity_endpoint(self):
        """Agents expose their public identity."""
        async with httpx.AsyncClient() as client:
            r = await client.get("http://127.0.0.1:18401/identity")

        data = r.json()
        assert data["name"] == "E2E Buyer"
        assert data["role"] == "buyer"
        assert "public_key" in data
        assert "agent_id" in data

    async def test_peer_registration(self):
        """Register seller as peer of buyer via HTTP."""
        async with httpx.AsyncClient() as client:
            # Get seller identity
            id_resp = await client.get("http://127.0.0.1:18402/identity")
            seller_id = id_resp.json()

            # Register seller with buyer
            reg_resp = await client.post(
                "http://127.0.0.1:18401/peers",
                json={
                    "agent_id": seller_id["agent_id"],
                    "name": seller_id["name"],
                    "role": seller_id["role"],
                    "url": "http://127.0.0.1:18402",
                    "public_key_hex": seller_id.get("public_key", ""),
                },
            )

        assert reg_resp.status_code == 200
        assert reg_resp.json()["status"] == "registered"

        # Verify peer shows up
        async with httpx.AsyncClient() as client:
            peers_resp = await client.get("http://127.0.0.1:18401/peers")
        peers = peers_resp.json()["peers"]
        assert len(peers) == 1
        assert peers[0]["name"] == "E2E Seller"

    async def test_message_delivery(self):
        """Send a message from buyer to seller via HTTP."""
        from incagent.messaging import AgentMessage, MessageType

        msg = AgentMessage(
            sender_id=self.buyer.agent_id,
            recipient_id=self.seller.agent_id,
            message_type=MessageType.PROPOSAL,
            payload={"test": "hello from buyer"},
        )

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "http://127.0.0.1:18402/messages",
                json=msg.to_wire(),
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

    async def test_trade_proposal(self):
        """Send a trade proposal to seller."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "http://127.0.0.1:18402/propose",
                json={
                    "title": "GPU Hours Supply Agreement",
                    "terms": {
                        "quantity": 500,
                        "unit_price": 45.0,
                        "currency": "USD",
                        "delivery_days": 14,
                        "payment_terms": "net_30",
                    },
                    "proposer_url": "http://127.0.0.1:18401",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "queued"
        assert "contract_id" in data
        assert data["agent"]["name"] == "E2E Seller"

    async def test_ledger_endpoint(self):
        """Ledger endpoint returns entries."""
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://127.0.0.1:18401/ledger")

        assert resp.status_code == 200
        entries = resp.json()
        assert isinstance(entries, list)
        assert len(entries) >= 1  # At least agent_created

    async def test_memory_endpoint(self):
        """Memory endpoint returns data."""
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://127.0.0.1:18401/memory")

        assert resp.status_code == 200
        data = resp.json()
        assert "stats" in data

    async def test_skills_endpoint(self):
        """Skills endpoint returns loaded skills."""
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://127.0.0.1:18401/skills")

        assert resp.status_code == 200
        data = resp.json()
        assert "skills" in data
        assert len(data["skills"]) >= 2  # cloud_compute + supply_chain

    async def test_full_discovery_flow(self):
        """Full flow: probe seller -> register -> verify peers."""
        async with httpx.AsyncClient() as client:
            # 1. Probe seller
            id_resp = await client.get("http://127.0.0.1:18402/identity")
            assert id_resp.status_code == 200
            seller_info = id_resp.json()

            # 2. Register with buyer
            reg_resp = await client.post(
                "http://127.0.0.1:18401/peers",
                json={
                    "agent_id": seller_info["agent_id"],
                    "name": seller_info["name"],
                    "role": seller_info["role"],
                    "url": "http://127.0.0.1:18402",
                },
            )
            assert reg_resp.status_code == 200

            # 3. Send proposal
            prop_resp = await client.post(
                "http://127.0.0.1:18402/propose",
                json={
                    "title": "Test Trade",
                    "terms": {"quantity": 100, "unit_price": 25.0},
                    "proposer_url": "http://127.0.0.1:18401",
                },
            )
            assert prop_resp.status_code == 200

            # 4. Check buyer health
            health = await client.get("http://127.0.0.1:18401/health")
            assert health.json()["peers"] == 1
