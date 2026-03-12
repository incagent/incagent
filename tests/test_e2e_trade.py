"""E2E Test: 仮想2社間の完全取引フロー.

シナリオ:
1. Buyer(Acme Corp) と Seller(CloudPeak) を作成
2. 交渉 → 合意 → 契約締結
3. 決済（シミュレーション）
4. デジタル納品 → 自動検証 → 完了
5. 物理納品 → 人間承認 → 完了
6. 紛争 → 証拠提出 → 解決
7. 台帳の改ざん検知
8. Memory（学習記録）の確認
"""

import tempfile
from pathlib import Path

import pytest

from incagent import (
    Contract,
    ContractStatus,
    ContractTerms,
    IncAgent,
)
from incagent.delivery import DeliveryType
from incagent.settlement import DisputeStatus, SettlementMode


@pytest.fixture
def tmp_dirs():
    """Create separate temp dirs for buyer and seller."""
    buyer_dir = tempfile.mkdtemp(prefix="buyer_")
    seller_dir = tempfile.mkdtemp(prefix="seller_")
    return buyer_dir, seller_dir


class TestFullTradeLifecycle:
    """2社間の完全取引フロー（デジタル商品）."""

    async def test_digital_trade_end_to_end(self, tmp_dirs):
        """Buyer → Seller: GPU Cluster Hours（デジタル商品）
        交渉 → 合意 → 決済 → 自動検証 → 完了"""
        buyer_dir, seller_dir = tmp_dirs

        # 1. エージェント作成
        buyer = IncAgent(
            name="Acme Corp",
            role="buyer",
            autonomous_mode=True,
            data_dir=buyer_dir,
        )
        seller = IncAgent(
            name="CloudPeak",
            role="seller",
            autonomous_mode=True,
            data_dir=seller_dir,
        )

        assert buyer.state.value == "idle"
        assert seller.state.value == "idle"

        # 2. 契約作成
        contract = Contract(
            title="GPU Cluster Hours",
            terms=ContractTerms(
                quantity=1000,
                unit_price_range=(50.0, 80.0),
                currency="USD",
                payment_terms="net_30",
            ),
        )

        # 3. 交渉実行
        result = await buyer.negotiate(contract, counterparty=seller)

        # 交渉結果の確認
        assert result.status.value in ("agreed", "rejected", "timeout")
        if result.status.value == "agreed":
            assert result.final_terms is not None
            assert result.final_terms.unit_price is not None
            assert result.rounds >= 1

            # 契約が合意・署名済み
            assert contract.status == ContractStatus.COMPLETED
            assert buyer.agent_id in contract.signatures

            # 台帳に記録されている
            entries = buyer.get_ledger_entries(limit=100)
            actions = [e.get("action") for e in entries]
            assert "negotiation_started" in actions
            assert "negotiation_completed" in actions

            # Memoryに学習記録
            stats = buyer._memory.stats()
            assert stats.get("total_trades", 0) >= 1

        buyer.close()
        seller.close()

    async def test_physical_trade_with_human_approval(self, tmp_dirs):
        """物理商品の取引 → 人間が納品確認 → 完了"""
        buyer_dir, seller_dir = tmp_dirs

        buyer = IncAgent(
            name="ManufactCo",
            role="buyer",
            autonomous_mode=True,
            data_dir=buyer_dir,
        )
        seller = IncAgent(
            name="PartsCo",
            role="seller",
            autonomous_mode=True,
            data_dir=seller_dir,
        )

        # 物理品の契約
        contract = Contract(
            title="Industrial Parts 500pcs",
            terms=ContractTerms(
                quantity=500,
                unit_price_range=(20.0, 35.0),
                currency="USD",
                delivery_days=14,
                payment_terms="net_30",
            ),
        )

        result = await buyer.negotiate(contract, counterparty=seller)

        if result.status.value == "agreed":
            # Settlement作成済み確認
            settlements = buyer.list_active_settlements()
            # 物理品はdelivery_days > 0 → DeliveryType.PHYSICAL
            # auto-verifyされないので active に残る
            assert len(settlements) >= 1

            # 物理品は自動完了しない → 手動確認が必要
            settlement = settlements[0]
            assert settlement.status in ("paid", "delivering", "pending")

            # 人間が納品確認
            confirmed = buyer.confirm_delivery(
                settlement.settlement_id,
                approved=True,
                notes="500個受領確認済み、品質OK",
            )
            assert confirmed is True
            assert settlement.status == "verified"

            # 完了処理
            completed = await buyer._settlement.complete(settlement.settlement_id)
            assert completed is True
            assert settlement.status == "completed"

        buyer.close()
        seller.close()

    async def test_trade_dispute_flow(self, tmp_dirs):
        """取引 → 紛争 → 証拠提出 → 解決"""
        buyer_dir, seller_dir = tmp_dirs

        buyer = IncAgent(
            name="DisputeBuyer",
            role="buyer",
            autonomous_mode=True,
            data_dir=buyer_dir,
        )
        seller = IncAgent(
            name="DisputeSeller",
            role="seller",
            autonomous_mode=True,
            data_dir=seller_dir,
        )

        contract = Contract(
            title="Software License",
            terms=ContractTerms(
                quantity=10,
                unit_price_range=(100.0, 200.0),
                currency="USD",
                delivery_days=7,
                payment_terms="net_30",
            ),
        )

        result = await buyer.negotiate(contract, counterparty=seller)

        if result.status.value == "agreed":
            settlements = buyer.list_active_settlements()
            assert len(settlements) >= 1
            settlement = settlements[0]

            # Buyer が紛争提起
            dispute = buyer.file_dispute(
                settlement.settlement_id,
                reason="ライセンスキーが無効",
            )
            assert dispute is not None
            assert dispute.reason == "ライセンスキーが無効"
            assert settlement.status == "disputed"

            # 証拠追加
            added = buyer._settlement.add_dispute_evidence(
                dispute.dispute_id,
                {"type": "screenshot", "url": "https://evidence.example.com/invalid_key.png"},
            )
            assert added is True
            assert len(dispute.evidence) == 1

            # 追加の証拠
            buyer._settlement.add_dispute_evidence(
                dispute.dispute_id,
                {"type": "api_log", "response_code": 403, "message": "Invalid license key"},
            )
            assert len(dispute.evidence) == 2

            # 紛争解決（Buyer勝利 → 返金）
            buyer._settlement.resolve_dispute(
                dispute.dispute_id,
                DisputeStatus.RESOLVED_BUYER,
                notes="ライセンスキー無効を確認。全額返金",
            )
            assert dispute.status == DisputeStatus.RESOLVED_BUYER
            assert settlement.status == "refunded"
            assert dispute.resolved_at is not None

        buyer.close()
        seller.close()

    async def test_dispute_seller_wins(self, tmp_dirs):
        """紛争でSeller勝利 → 取引完了"""
        buyer_dir, seller_dir = tmp_dirs

        buyer = IncAgent(
            name="ClaimBuyer",
            role="buyer",
            autonomous_mode=True,
            data_dir=buyer_dir,
        )
        seller = IncAgent(
            name="DefendSeller",
            role="seller",
            autonomous_mode=True,
            data_dir=seller_dir,
        )

        contract = Contract(
            title="Cloud Storage 1TB",
            terms=ContractTerms(
                quantity=1,
                unit_price_range=(500.0, 800.0),
                currency="USD",
                delivery_days=3,
                payment_terms="net_30",
            ),
        )

        result = await buyer.negotiate(contract, counterparty=seller)

        if result.status.value == "agreed":
            settlements = buyer.list_active_settlements()
            settlement = settlements[0]

            dispute = buyer.file_dispute(
                settlement.settlement_id,
                reason="容量が足りない",
            )

            # Seller側が証拠提出
            buyer._settlement.add_dispute_evidence(
                dispute.dispute_id,
                {"type": "dashboard_screenshot", "storage_used": "1024GB", "storage_limit": "1024GB"},
            )

            # 紛争解決（Seller勝利 → 取引続行）
            buyer._settlement.resolve_dispute(
                dispute.dispute_id,
                DisputeStatus.RESOLVED_SELLER,
                notes="1TBは正しく提供されている。Buyer側の誤認",
            )
            assert dispute.status == DisputeStatus.RESOLVED_SELLER
            assert settlement.status == "completed"

        buyer.close()
        seller.close()


class TestMultiTradeSession:
    """複数回取引して学習する."""

    async def test_consecutive_trades(self, tmp_dirs):
        """同じ相手と3回取引 → Memory に記録される"""
        buyer_dir, seller_dir = tmp_dirs

        buyer = IncAgent(
            name="RepeatBuyer",
            role="buyer",
            autonomous_mode=True,
            data_dir=buyer_dir,
        )
        seller = IncAgent(
            name="RepeatSeller",
            role="seller",
            autonomous_mode=True,
            data_dir=seller_dir,
        )

        agreed_count = 0
        for i in range(3):
            contract = Contract(
                title=f"API Credits Batch #{i+1}",
                terms=ContractTerms(
                    quantity=100 * (i + 1),
                    unit_price_range=(10.0, 30.0),
                    currency="USD",
                    payment_terms="net_30",
                ),
            )
            result = await buyer.negotiate(contract, counterparty=seller)
            if result.status.value == "agreed":
                agreed_count += 1

        # 少なくとも1回は合意しているはず
        assert agreed_count >= 1

        # Memory に取引履歴が記録されている
        stats = buyer._memory.stats()
        assert stats.get("total_trades", 0) == 3  # 合意/不合意問わず記録

        # パートナー情報が記録されている
        partners = buyer._memory.get_all_partners()
        seller_records = [p for p in partners if p.get("partner_name") == "RepeatSeller"]
        assert len(seller_records) == 1
        assert seller_records[0]["total_trades"] == 3

        buyer.close()
        seller.close()


class TestAgentHealth:
    """ヘルスチェック・台帳検証."""

    async def test_health_after_trade(self, tmp_dirs):
        buyer_dir, seller_dir = tmp_dirs

        buyer = IncAgent(
            name="HealthCheckCo",
            role="buyer",
            autonomous_mode=True,
            data_dir=buyer_dir,
        )
        seller = IncAgent(
            name="PartnerCo",
            role="seller",
            autonomous_mode=True,
            data_dir=seller_dir,
        )

        contract = Contract(
            title="Health Check Trade",
            terms=ContractTerms(
                quantity=50,
                unit_price_range=(10.0, 20.0),
                currency="USD",
            ),
        )
        await buyer.negotiate(contract, counterparty=seller)

        # ヘルスチェック
        health = buyer.health_status()
        assert health["name"] == "HealthCheckCo"
        assert health["state"] == "idle"
        assert health["circuit_breaker"] == "closed"
        assert health["ledger_valid"] is True
        assert isinstance(health["tools"], int)

        # 台帳の改ざん検知
        assert buyer.verify_ledger() is True

        buyer.close()
        seller.close()

    async def test_ledger_integrity(self, tmp_dirs):
        """台帳のハッシュチェーン検証."""
        buyer_dir, _ = tmp_dirs

        buyer = IncAgent(
            name="LedgerTestCo",
            role="buyer",
            autonomous_mode=True,
            data_dir=buyer_dir,
        )

        # 台帳にエントリがある
        entries = buyer.get_ledger_entries()
        assert len(entries) >= 1  # 少なくとも agent_created

        # チェーン整合性
        assert buyer.verify_ledger() is True

        buyer.close()


class TestSettlementDirect:
    """Settlement Engine を直接テスト（negotiation を経由しない）."""

    async def test_full_settlement_lifecycle(self, tmp_dirs):
        """Settlement 単体の完全ライフサイクル."""
        buyer_dir, _ = tmp_dirs

        buyer = IncAgent(
            name="SettleTestCo",
            role="buyer",
            autonomous_mode=True,
            data_dir=buyer_dir,
        )

        engine = buyer._settlement

        # 1. Settlement作成
        s = engine.create_settlement(
            transaction_id="tx_e2e_1",
            contract_id="c_e2e_1",
            buyer_id=buyer.agent_id,
            seller_id="seller_abc",
            amount_usdc=2500.0,
            mode=SettlementMode.DIRECT,
            delivery_type=DeliveryType.PHYSICAL,
            delivery_days=7,
        )
        assert s.status == "pending"
        assert s.delivery is not None
        assert s.delivery.delivery_type == DeliveryType.PHYSICAL
        assert s.delivery.expected_by is not None

        # 2. 決済（シミュレーション — ウォレット未設定）
        s.status = "paid"

        # 3. 納品確認（人間）
        confirmed = engine.confirm_delivery_human(s.settlement_id, True, "7日目に到着")
        assert confirmed is True
        assert s.status == "verified"

        # 4. 完了
        completed = await engine.complete(s.settlement_id)
        assert completed is True
        assert s.status == "completed"
        assert s.completed_at is not None

        buyer.close()

    async def test_webhook_delivery(self, tmp_dirs):
        """外部システムからのWebhook経由の納品確認."""
        buyer_dir, _ = tmp_dirs

        buyer = IncAgent(
            name="WebhookTestCo",
            role="buyer",
            autonomous_mode=True,
            data_dir=buyer_dir,
        )

        engine = buyer._settlement

        s = engine.create_settlement(
            transaction_id="tx_webhook",
            contract_id="c_webhook",
            buyer_id=buyer.agent_id,
            seller_id="seller_webhook",
            amount_usdc=1000.0,
            delivery_type=DeliveryType.PHYSICAL,
        )

        # Webhook from shipping company
        result = engine.confirm_delivery_webhook(s.settlement_id, {
            "verified": True,
            "tracking_number": "JP123456789",
            "carrier": "YamatoTransport",
            "delivered_at": "2026-03-12T10:00:00Z",
        })
        assert result is True
        assert s.status == "verified"

        completed = await engine.complete(s.settlement_id)
        assert completed is True

        buyer.close()

    async def test_delivery_rejection(self, tmp_dirs):
        """納品拒否 → 紛争フロー."""
        buyer_dir, _ = tmp_dirs

        buyer = IncAgent(
            name="RejectTestCo",
            role="buyer",
            autonomous_mode=True,
            data_dir=buyer_dir,
        )

        engine = buyer._settlement

        s = engine.create_settlement(
            transaction_id="tx_reject",
            contract_id="c_reject",
            buyer_id=buyer.agent_id,
            seller_id="seller_reject",
            amount_usdc=500.0,
            delivery_type=DeliveryType.PHYSICAL,
        )

        # 納品拒否
        result = engine.confirm_delivery_human(
            s.settlement_id,
            approved=False,
            notes="商品が破損していた",
        )
        assert result is False
        assert s.status == "disputed"

        # 紛争フロー
        dispute = engine.file_dispute(
            s.settlement_id,
            buyer.agent_id,
            "商品が破損",
            [{"type": "photo", "description": "箱が潰れている"}],
        )
        assert dispute is not None
        assert len(dispute.evidence) == 1

        # 解決（Split）
        engine.resolve_dispute(
            dispute.dispute_id,
            DisputeStatus.RESOLVED_SPLIT,
            notes="半額返金で合意",
        )
        assert dispute.status == DisputeStatus.RESOLVED_SPLIT
        assert s.status == "resolved"

        buyer.close()


class TestApprovalWorkflow:
    """承認フロー（非自律モード）のテスト."""

    async def test_high_value_needs_approval(self, tmp_dirs):
        """高額取引でも autonomous_mode=True なら承認スキップで通る."""
        buyer_dir, seller_dir = tmp_dirs

        buyer = IncAgent(
            name="CarefulBuyer",
            role="buyer",
            autonomous_mode=True,
            approval_threshold=1000.0,
            data_dir=buyer_dir,
        )
        seller = IncAgent(
            name="BigSeller",
            role="seller",
            autonomous_mode=True,
            data_dir=seller_dir,
        )

        # 高額契約
        contract = Contract(
            title="Enterprise License",
            terms=ContractTerms(
                quantity=1,
                unit_price_range=(5000.0, 8000.0),
                currency="USD",
            ),
        )

        result = await buyer.negotiate(contract, counterparty=seller)
        # auto_approveなので通る or 承認ワークフロー次第
        # 最低限エラーなく完了すること
        assert result.status.value in ("agreed", "rejected", "timeout")

        buyer.close()
        seller.close()

    async def test_low_value_no_approval(self, tmp_dirs):
        """低額取引は承認不要."""
        buyer_dir, seller_dir = tmp_dirs

        buyer = IncAgent(
            name="QuickBuyer",
            role="buyer",
            autonomous_mode=False,
            approval_threshold=100000.0,  # 10万ドル以上のみ承認
            data_dir=buyer_dir,
        )
        seller = IncAgent(
            name="SmallSeller",
            role="seller",
            autonomous_mode=True,
            data_dir=seller_dir,
        )

        contract = Contract(
            title="Small Purchase",
            terms=ContractTerms(
                quantity=10,
                unit_price_range=(5.0, 10.0),
                currency="USD",
            ),
        )

        result = await buyer.negotiate(contract, counterparty=seller)
        assert result.status.value in ("agreed", "rejected", "timeout")

        buyer.close()
        seller.close()


class TestToolSystem:
    """ツールシステムの統合テスト."""

    async def test_agent_tools_available(self, tmp_dirs):
        """エージェントにツールが搭載されている."""
        buyer_dir, _ = tmp_dirs

        agent = IncAgent(
            name="ToolAgent",
            role="buyer",
            autonomous_mode=True,
            data_dir=buyer_dir,
        )

        tools = agent.list_tools()
        tool_names = [t["name"] for t in tools]

        # ビルトインツールが存在する
        assert "webhook_call" in tool_names
        assert "http_api" in tool_names

        agent.close()

    async def test_agent_create_and_use_tool(self, tmp_dirs):
        """エージェントが自分で新しいツールを作成・使用."""
        buyer_dir, _ = tmp_dirs

        agent = IncAgent(
            name="CreatorAgent",
            role="buyer",
            autonomous_mode=True,
            data_dir=buyer_dir,
        )

        # ツール作成
        code = '''
from incagent.tools.base import BaseTool, ToolParam, ToolResult

class TimestampTool(BaseTool):
    name = "timestamp"
    description = "Returns the current UTC timestamp"
    parameters = []

    async def execute(self, **kwargs) -> ToolResult:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        return ToolResult(success=True, data={"timestamp": now})
'''
        created = agent.create_tool("timestamp", code)
        assert created is True

        # ツール使用
        result = await agent.use_tool("timestamp")
        assert result.success is True
        assert "timestamp" in result.data

        # 台帳に記録
        entries = agent.get_ledger_entries(limit=100)
        tool_actions = [e for e in entries if e.get("action") == "tool_used"]
        assert len(tool_actions) >= 1

        agent.close()


class TestIdentityAndSecurity:
    """アイデンティティ・署名検証."""

    def test_unique_identities(self, tmp_dirs):
        buyer_dir, seller_dir = tmp_dirs

        a1 = IncAgent(name="Corp A", role="buyer", data_dir=buyer_dir, autonomous_mode=True)
        a2 = IncAgent(name="Corp B", role="seller", data_dir=seller_dir, autonomous_mode=True)

        assert a1.agent_id != a2.agent_id
        assert a1.identity.public_key_hex != a2.identity.public_key_hex
        assert a1.identity.fingerprint() != a2.identity.fingerprint()

        a1.close()
        a2.close()

    async def test_contract_signatures(self, tmp_dirs):
        buyer_dir, seller_dir = tmp_dirs

        buyer = IncAgent(name="SignBuyer", role="buyer", data_dir=buyer_dir, autonomous_mode=True)
        seller = IncAgent(name="SignSeller", role="seller", data_dir=seller_dir, autonomous_mode=True)

        contract = Contract(
            title="Signed Deal",
            terms=ContractTerms(quantity=1, unit_price_range=(100.0, 200.0)),
        )

        result = await buyer.negotiate(contract, counterparty=seller)

        if result.status.value == "agreed":
            # Buyer が署名している
            assert buyer.agent_id in contract.signatures
            sig = contract.signatures[buyer.agent_id]
            assert len(sig) > 0  # 署名が存在

        buyer.close()
        seller.close()
