"""IncAgent フルデモ — AI法人エージェント自律取引

3社のAIエージェントが自律的に:
1. GPU時間の売買を交渉・契約
2. 税務記録を自動生成（1099-NEC検出）
3. 台帳検証・学習メモリで取引パートナーを評価

LLM不要 — rule-basedフォールバックで全プロセスが動く。
"""

import asyncio
import time
from datetime import datetime, timezone

from incagent import (
    Contract,
    ContractTerms,
    IncAgent,
    NegotiationPolicy,
)
from incagent.messaging import MessageBus


# ── 色付きログ ─────────────────────────────────────────────────────

RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[92m"
BLUE = "\033[94m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
RED = "\033[91m"
DIM = "\033[2m"


def header(text: str) -> None:
    print(f"\n{BOLD}{'=' * 64}")
    print(f"  {text}")
    print(f"{'=' * 64}{RESET}\n")


def step(n: int, text: str) -> None:
    print(f"{CYAN}[Step {n}]{RESET} {text}")


def money(label: str, value: float, color: str = GREEN) -> None:
    print(f"  {label}: {color}${value:,.2f}{RESET}")


def info(label: str, value: str) -> None:
    print(f"  {DIM}{label}:{RESET} {value}")


# ── メイン ─────────────────────────────────────────────────────────

async def main() -> None:
    bus = MessageBus()

    header("IncAgent Demo — AI法人エージェント自律取引")
    print(f"{DIM}時刻: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}{RESET}")
    print()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Phase 1: エージェント作成
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    step(1, "3社のAIエージェントを起動")

    acme = IncAgent(
        name="Acme Corp",
        role="buyer",
        autonomous_mode=True,
        message_bus=bus,
    )
    cloudpeak = IncAgent(
        name="CloudPeak",
        role="seller",
        autonomous_mode=True,
        message_bus=bus,
    )
    nexus = IncAgent(
        name="NexusTech",
        role="seller",
        autonomous_mode=True,
        message_bus=bus,
    )

    agents = [acme, cloudpeak, nexus]
    for a in agents:
        info(f"{a.name}", f"ID={a.identity.fingerprint()[:12]}  Role={a.identity.role}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Phase 2: GPU時間 — Acme × CloudPeak（大型取引）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    header("Phase 2: GPU Cluster Hours — Acme Corp × CloudPeak")

    contract_gpu = Contract(
        title="GPU Cluster Hours Q2 2026",
        terms=ContractTerms(
            quantity=2000,
            unit_price_range=(50, 80),
            currency="USD",
            delivery_days=14,
            payment_terms="net_30",
            custom={
                "gpu_type": "NVIDIA H100",
                "region": "us-east-1",
                "sla": "99.95%",
            },
        ),
    )

    buyer_policy = NegotiationPolicy(
        min_price=45.0,
        max_price=72.0,
        min_quantity=1500,
        max_quantity=3000,
        max_rounds=6,
    )

    step(2, f"交渉開始: {contract_gpu.title}")
    info("Buyer予算", "$45-72/unit × 2,000 units")
    info("Seller希望", "$50-80/unit")

    t0 = time.monotonic()
    result_gpu = await acme.negotiate(contract_gpu, counterparty=cloudpeak, policy=buyer_policy)
    elapsed = time.monotonic() - t0

    print()
    if result_gpu.final_terms:
        step(3, f"{GREEN}交渉成立{RESET} — {result_gpu.rounds}ラウンド ({elapsed:.1f}s)")
        money("単価", result_gpu.final_terms.unit_price)
        money("数量", float(result_gpu.final_terms.quantity), BLUE)
        money("取引総額", result_gpu.final_terms.estimated_value(), YELLOW)
        info("支払条件", result_gpu.final_terms.payment_terms)
    else:
        step(3, f"{RED}交渉決裂{RESET}: {result_gpu.reason}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Phase 3: データパイプライン — Acme × NexusTech（中型取引）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    header("Phase 3: Enterprise Data Pipeline — Acme Corp × NexusTech")

    contract_data = Contract(
        title="Enterprise Data Pipeline License",
        terms=ContractTerms(
            quantity=500,
            unit_price_range=(120, 250),
            currency="USD",
            delivery_days=7,
            payment_terms="net_30",
            custom={
                "support_tier": "premium",
                "data_retention": "90 days",
                "api_rate_limit": "10,000 req/min",
            },
        ),
    )

    data_policy = NegotiationPolicy(
        min_price=100.0,
        max_price=220.0,
        max_rounds=5,
    )

    step(4, f"交渉開始: {contract_data.title}")
    info("Buyer予算", "$100-220/unit × 500 units")

    t0 = time.monotonic()
    result_data = await acme.negotiate(contract_data, counterparty=nexus, policy=data_policy)
    elapsed = time.monotonic() - t0

    print()
    if result_data.final_terms:
        step(5, f"{GREEN}交渉成立{RESET} — {result_data.rounds}ラウンド ({elapsed:.1f}s)")
        money("単価", result_data.final_terms.unit_price)
        money("取引総額", result_data.final_terms.estimated_value(), YELLOW)
    else:
        step(5, f"{RED}交渉決裂{RESET}: {result_data.reason}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Phase 4: 追加取引（1099-NEC閾値テスト用）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    header("Phase 4: 追加小口取引 × 3（税務記録蓄積）")

    small_contracts = [
        ("Consulting Services", 5, (100, 200), cloudpeak),
        ("API Monitoring Setup", 10, (30, 60), nexus),
        ("Security Audit", 1, (500, 800), cloudpeak),
    ]

    for title, qty, price_range, seller in small_contracts:
        c = Contract(
            title=title,
            terms=ContractTerms(quantity=qty, unit_price_range=price_range, currency="USD"),
        )
        p = NegotiationPolicy(min_price=price_range[0] * 0.8, max_price=price_range[1], max_rounds=3)
        r = await acme.negotiate(c, counterparty=seller, policy=p)
        status = f"{GREEN}成立{RESET}" if r.final_terms else f"{RED}決裂{RESET}"
        val = f"${r.final_terms.estimated_value():,.2f}" if r.final_terms else "—"
        print(f"  {title}: {status} ({val})")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Phase 5: 経理レポート
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    header("Phase 5: 経理レポート（Tax Summary 2026）")

    tax = acme.get_tax_summary(2026)
    step(6, "Acme Corp — 2026年度 税務サマリ")
    money("総支出", tax["total_expenses"], RED)
    money("総収入", tax["total_income"], GREEN)
    money("純額", tax["net"], YELLOW)
    info("取引件数", str(tax["record_count"]))
    info("ベンダー数", str(tax["vendor_count"]))
    info("1099-NEC対象", f"{tax['vendors_needing_1099']}社 (>$600/年)")

    # Vendor breakdown
    vendor_summary = acme._tax.get_vendor_summary(2026)
    if vendor_summary:
        print(f"\n  {BOLD}ベンダー別支払:{RESET}")
        for v in vendor_summary:
            flag = f" {RED}← 1099-NEC{RESET}" if v["needs_1099"] else ""
            print(f"    {v['vendor_name']}: ${v['total_paid']:,.2f}{flag}")

    # CSV export
    csv_output = acme._tax.export_csv(2026)
    csv_lines = csv_output.strip().split("\n")
    print(f"\n  {BOLD}CSV出力 ({len(csv_lines) - 1}件):{RESET}")
    for line in csv_lines[:4]:
        print(f"    {DIM}{line}{RESET}")
    if len(csv_lines) > 4:
        print(f"    {DIM}... ({len(csv_lines) - 4} more rows){RESET}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Phase 6: 台帳検証
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    header("Phase 6: 台帳・監査")

    step(7, "ハッシュチェーン検証")
    for a in agents:
        entries = a.get_ledger_entries()
        valid = a.verify_ledger()
        status = f"{GREEN}OK{RESET}" if valid else f"{RED}CORRUPTED{RESET}"
        print(f"  {a.name}: {len(entries)}エントリ — {status}")

    # Recent ledger entries
    print(f"\n  {BOLD}Acme Corp 直近アクティビティ:{RESET}")
    for entry in acme.get_ledger_entries(limit=8):
        ts = entry['timestamp'][:19]
        print(f"    {DIM}{ts}{RESET}  {entry['action']}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Phase 7: メモリ（学習記録）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    header("Phase 7: エージェント学習メモリ")

    step(8, "Acme Corp — 取引パートナー信頼度")
    stats = acme._memory.stats()
    info("総取引記録", str(stats.get("trade_history_count", 0)))
    info("戦略洞察", str(stats.get("strategy_count", 0)))

    # Partner reliability
    partners = acme._memory.get_all_partners()
    if partners:
        for p in partners:
            reliability = f"{p.get('success_rate', 0) * 100:.0f}%"
            avg_price = p.get('avg_price', 0)
            print(f"    {p['partner_name']}: 信頼度={reliability}  平均単価=${avg_price:.2f}  取引数={p.get('total_trades', 0)}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Summary
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    header("Summary")

    total_value = 0.0
    deals = 0
    all_results = [
        ("GPU Cluster Hours", result_gpu),
        ("Data Pipeline License", result_data),
    ]
    for title, r in all_results:
        if r.final_terms:
            v = r.final_terms.estimated_value()
            total_value += v
            deals += 1
            print(f"  {GREEN}✓{RESET} {title}: ${v:,.2f}")
        else:
            print(f"  {RED}✗{RESET} {title}: 決裂")

    print()
    money("総取引額", total_value, BOLD + YELLOW)
    info("成立取引", f"{deals}件")
    info("台帳エントリ", str(len(acme.get_ledger_entries())))
    info("学習記録", f"{stats.get('trade_history_count', 0)}件")
    info("1099-NEC対象ベンダー", f"{tax['vendors_needing_1099']}社")

    print(f"\n{BOLD}全プロセスがAIエージェント主導で自律実行。人間は物理世界だけ。{RESET}\n")

    # Cleanup
    for a in agents:
        a.close()


if __name__ == "__main__":
    asyncio.run(main())
