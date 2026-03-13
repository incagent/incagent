"""IncAgent Live Dashboard — 部署別ビューで法人エージェントの活動を可視化"""

import asyncio
import json
import os
import time
import webbrowser
from datetime import datetime, timezone

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, StreamingResponse
from starlette.routing import Route

from incagent import Contract, ContractTerms, IncAgent, NegotiationPolicy
from incagent.messaging import MessageBus

events: list[dict] = []
event_signal = asyncio.Event()
simulation_done = False


def emit(etype: str, data: dict) -> None:
    data["type"] = etype
    data["ts"] = datetime.now(timezone.utc).strftime("%H:%M:%S")
    events.append(data)
    event_signal.set()


async def run_simulation() -> None:
    global simulation_done
    await asyncio.sleep(2.5)

    import shutil
    d = os.path.join(os.path.expanduser("~"), ".incagent")
    if os.path.exists(d):
        shutil.rmtree(d)

    bus = MessageBus()

    acme = IncAgent(name="Acme Corp", role="buyer", autonomous_mode=True, message_bus=bus)
    emit("agent", {"name": "Acme Corp", "role": "Buyer", "id": acme.identity.fingerprint()[:12]})
    await asyncio.sleep(0.4)
    cloudpeak = IncAgent(name="CloudPeak", role="seller", autonomous_mode=True, message_bus=bus)
    emit("agent", {"name": "CloudPeak", "role": "Seller", "id": cloudpeak.identity.fingerprint()[:12]})
    await asyncio.sleep(0.4)
    nexus = IncAgent(name="NexusTech", role="seller", autonomous_mode=True, message_bus=bus)
    emit("agent", {"name": "NexusTech", "role": "Seller", "id": nexus.identity.fingerprint()[:12]})
    await asyncio.sleep(1.0)

    # ── GPU Deal ──
    emit("sales", {"action": "proposal", "title": "GPU Cluster Hours Q2 2026",
        "from": "Acme Corp", "to": "CloudPeak",
        "detail": "RFQ sent for NVIDIA H100 x 2,000 GPU hours. SLA 99.95%, us-east-1 region specified.",
        "budget": "$90,000 - $144,000", "item": "NVIDIA H100", "qty": "2,000 hours"})
    await asyncio.sleep(1.0)

    cg = Contract(title="GPU Cluster Hours Q2 2026",
        terms=ContractTerms(quantity=2000, unit_price_range=(50,80), currency="USD",
            delivery_days=14, payment_terms="net_30",
            custom={"gpu_type":"NVIDIA H100","region":"us-east-1","sla":"99.95%"}))
    pg = NegotiationPolicy(min_price=45, max_price=72, min_quantity=1500, max_quantity=3000, max_rounds=6)
    t0 = time.monotonic()
    rg = await acme.negotiate(cg, counterparty=cloudpeak, policy=pg)
    el = time.monotonic() - t0

    if rg.final_terms:
        for i in range(1, rg.rounds+1):
            who = "CloudPeak" if i % 2 == 1 else "Acme Corp"
            emit("sales", {"action": "round", "title": "GPU Cluster Hours",
                "from": who, "to": "Acme Corp" if who == "CloudPeak" else "CloudPeak",
                "detail": f"Negotiation round {i}/{rg.rounds} — {'Initial offer' if i==1 else 'Counter-offer' if i<rg.rounds else 'Final adjustment'}",
                "round": i, "of": rg.rounds})
            await asyncio.sleep(0.6)

        tg = rg.final_terms.estimated_value()
        emit("sales", {"action": "closed", "title": "GPU Cluster Hours Q2 2026",
            "from": "Acme Corp", "to": "CloudPeak",
            "detail": f"Deal closed in {rg.rounds} rounds ({el:.1f}s). Net 30, delivery within 14 days, SLA 99.95% guaranteed.",
            "price": rg.final_terms.unit_price, "qty": rg.final_terms.quantity,
            "total": tg, "item": "NVIDIA H100"})
        emit("kpi_add", {"vol": tg, "deals": 1})
        await asyncio.sleep(0.5)

        emit("accounting", {"action": "expense", "vendor": "CloudPeak", "amount": tg,
            "account": "Cloud Infrastructure", "ref": cg.contract_id[:8],
            "note": "GPU Cluster Hours Q2 2026 — Net 30 payment"})
        await asyncio.sleep(0.3)
        emit("accounting", {"action": "1099_alert", "vendor": "CloudPeak", "amount": tg,
            "note": "Annual payments to CloudPeak exceed $600. 1099-NEC filing required."})
        await asyncio.sleep(0.3)
        emit("pr", {"action": "announcement",
            "title": "Acme Corp closes major GPU contract with CloudPeak — 2,000 hours",
            "body": f"Acme Corp has signed an agreement with CloudPeak Inc. for 2,000 hours of NVIDIA H100 GPU cluster access (total value ${tg:,.0f}). Part of our Q2 2026 AI infrastructure expansion.",
            "partner": "CloudPeak"})
    await asyncio.sleep(1.5)

    # ── Data Pipeline Deal ──
    emit("sales", {"action": "proposal", "title": "Enterprise Data Pipeline License",
        "from": "Acme Corp", "to": "NexusTech",
        "detail": "Enterprise license for 500 seats. Premium support, 90-day data retention, 10K req/min.",
        "budget": "$50,000 - $110,000", "item": "Enterprise License", "qty": "500 seats"})
    await asyncio.sleep(1.0)

    cd = Contract(title="Enterprise Data Pipeline License",
        terms=ContractTerms(quantity=500, unit_price_range=(120,250), currency="USD",
            delivery_days=7, payment_terms="net_30",
            custom={"support_tier":"premium","data_retention":"90 days"}))
    pd = NegotiationPolicy(min_price=100, max_price=220, max_rounds=5)
    t0 = time.monotonic()
    rd = await acme.negotiate(cd, counterparty=nexus, policy=pd)
    el = time.monotonic() - t0

    if rd.final_terms:
        for i in range(1, rd.rounds+1):
            emit("sales", {"action": "round", "title": "Data Pipeline License",
                "from": "NexusTech" if i%2==1 else "Acme Corp", "to": "Acme Corp" if i%2==1 else "NexusTech",
                "detail": f"Negotiation round {i}/{rd.rounds}", "round": i, "of": rd.rounds})
            await asyncio.sleep(0.6)
        td = rd.final_terms.estimated_value()
        emit("sales", {"action": "closed", "title": "Enterprise Data Pipeline License",
            "from": "Acme Corp", "to": "NexusTech",
            "detail": f"Deal closed in {rd.rounds} rounds ({el:.1f}s). Premium support included, delivery within 7 days.",
            "price": rd.final_terms.unit_price, "qty": rd.final_terms.quantity,
            "total": td, "item": "Enterprise License"})
        emit("kpi_add", {"vol": td, "deals": 1})
        await asyncio.sleep(0.5)
        emit("accounting", {"action": "expense", "vendor": "NexusTech", "amount": td,
            "account": "Software Licenses", "ref": cd.contract_id[:8],
            "note": "Enterprise Data Pipeline License — Net 30"})
        await asyncio.sleep(0.3)
        emit("pr", {"action": "announcement",
            "title": "Acme Corp upgrades data infrastructure — Enterprise deal with NexusTech",
            "body": f"Acme Corp has deployed NexusTech's Enterprise Data Pipeline across 500 seats (total ${td:,.0f}). Significantly expanding data processing capacity.",
            "partner": "NexusTech"})
    await asyncio.sleep(1.5)

    # ── Small deals ──
    smalls = [
        ("Consulting Services", 5, (100,200), cloudpeak, "CloudPeak", "Professional Services",
         "Quality management process improvement consulting"),
        ("API Monitoring Setup", 10, (30,60), nexus, "NexusTech", "IT Operations",
         "SLA monitoring tool deployment and configuration"),
        ("Security Audit", 1, (500,800), cloudpeak, "CloudPeak", "Compliance",
         "SOC2 Type II compliance security audit"),
    ]
    for title, qty, pr, seller, sn, cat, desc in smalls:
        emit("sales", {"action": "proposal", "title": title,
            "from": "Acme Corp", "to": sn,
            "detail": f"{desc}. {qty} units x ${pr[0]}-{pr[1]}/unit",
            "budget": f"${pr[0]*qty:,}-${pr[1]*qty:,}", "item": title, "qty": f"{qty} units"})
        await asyncio.sleep(0.5)
        c = Contract(title=title, terms=ContractTerms(quantity=qty, unit_price_range=pr, currency="USD"))
        p = NegotiationPolicy(min_price=pr[0]*0.8, max_price=pr[1], max_rounds=3)
        r = await acme.negotiate(c, counterparty=seller, policy=p)
        if r.final_terms:
            v = r.final_terms.estimated_value()
            emit("sales", {"action": "closed", "title": title,
                "from": "Acme Corp", "to": sn,
                "detail": f"Closed immediately.", "price": r.final_terms.unit_price,
                "qty": r.final_terms.quantity, "total": v, "item": title})
            emit("kpi_add", {"vol": v, "deals": 1})
            emit("accounting", {"action": "expense", "vendor": sn, "amount": v,
                "account": cat, "ref": c.contract_id[:8], "note": f"{title}"})
        await asyncio.sleep(0.8)

    # ── Full accounting report ──
    await asyncio.sleep(1.0)
    tax = acme.get_tax_summary(2026)
    vendors = acme._tax.get_vendor_summary(2026) or []
    emit("accounting", {"action": "report",
        "expenses": tax["total_expenses"], "income": tax["total_income"], "net": tax["net"],
        "records": tax["record_count"], "vendor_count": tax["vendor_count"],
        "nec": tax["vendors_needing_1099"],
        "vendors": [{"name": v["vendor_name"], "paid": v["total_paid"], "nec": v["needs_1099"]} for v in vendors]})
    emit("kpi_finance", {"expenses": tax["total_expenses"], "nec": tax["vendors_needing_1099"]})
    await asyncio.sleep(1.5)

    # ── Legal/Audit ──
    audits = []
    for a in [acme, cloudpeak, nexus]:
        ent = a.get_ledger_entries()
        ok = a.verify_ledger()
        audits.append({"name": a.name, "entries": len(ent), "ok": ok})
    emit("legal", {"action": "audit", "agents": audits})
    await asyncio.sleep(1.5)

    # ── Strategy / BI ──
    partners = acme._memory.get_all_partners() or []
    emit("strategy", {"action": "partner_analysis",
        "partners": [{"name": p["partner_name"], "rate": p.get("success_rate",0),
                       "avg": p.get("avg_price",0), "trades": p.get("total_trades",0)} for p in partners]})
    await asyncio.sleep(1.0)

    emit("done", {})
    simulation_done = True
    for a in [acme, cloudpeak, nexus]:
        a.close()


async def sse_stream(req):
    async def gen():
        sent = 0
        while True:
            if sent < len(events):
                for ev in events[sent:]:
                    yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                sent = len(events)
            if simulation_done and sent >= len(events):
                break
            event_signal.clear()
            try: await asyncio.wait_for(event_signal.wait(), timeout=1.0)
            except asyncio.TimeoutError: yield ": keepalive\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})


PAGE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>IncAgent</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600;700&family=Noto+Sans+JP:wght@400;500;600;700&display=swap');
:root{--bg:#f5f5f7;--surface:#fff;--border:#e5e7eb;--t1:#111;--t2:#374151;--t3:#9ca3af;
--green:#16a34a;--green-l:#dcfce7;--red:#dc2626;--red-l:#fee2e2;--blue:#2563eb;--blue-l:#dbeafe;
--purple:#7c3aed;--purple-l:#ede9fe;--amber:#d97706;--amber-l:#fef3c7;--cyan:#0891b2;--cyan-l:#cffafe;--pink:#db2777;--pink-l:#fce7f3;}
*{margin:0;padding:0;box-sizing:border-box;}
body{background:var(--bg);color:var(--t2);font-family:'Inter','Noto Sans JP',system-ui,sans-serif;-webkit-font-smoothing:antialiased;height:100vh;overflow:hidden;display:flex;flex-direction:column;}

/* Nav */
header{background:var(--surface);border-bottom:1px solid var(--border);height:56px;display:flex;align-items:center;padding:0 24px;gap:16px;flex-shrink:0;}
.brand{font-size:22px;font-weight:900;color:var(--t1);}
.brand b{color:var(--blue);}
header .spacer{flex:1;}
.live-pill{display:flex;align-items:center;gap:6px;font-size:12px;font-weight:700;color:var(--green);background:var(--green-l);padding:4px 14px;border-radius:20px;}
.live-pill .dot{width:8px;height:8px;border-radius:50%;background:var(--green);animation:glow 2s infinite;}
@keyframes glow{0%,100%{opacity:1}50%{opacity:.3}}

/* Stats bar */
.stats{background:var(--surface);border-bottom:1px solid var(--border);display:flex;justify-content:center;gap:48px;padding:14px 24px;flex-shrink:0;}
.st{text-align:center;}.st-n{font-size:30px;font-weight:900;font-family:'JetBrains Mono',monospace;line-height:1.1;}
.st-n.c-green{color:var(--green);}.st-n.c-blue{color:var(--blue);}.st-n.c-red{color:var(--red);}.st-n.c-amber{color:var(--amber);}
.st-l{font-size:11px;color:var(--t3);margin-top:2px;font-weight:500;}

/* Tabs */
.tabs{background:var(--surface);border-bottom:1px solid var(--border);display:flex;padding:0 24px;gap:0;flex-shrink:0;}
.tab{padding:14px 24px;font-size:16px;font-weight:700;color:var(--t3);cursor:pointer;border-bottom:3px solid transparent;transition:all .2s;position:relative;}
.tab:hover{color:var(--t2);}
.tab.active{color:var(--blue);border-bottom-color:var(--blue);}
.tab .badge{display:inline-flex;align-items:center;justify-content:center;min-width:20px;height:20px;font-size:11px;font-weight:700;background:var(--blue-l);color:var(--blue);border-radius:10px;padding:0 6px;margin-left:8px;}
.tab .badge.red{background:var(--red-l);color:var(--red);}
.tab .badge.green{background:var(--green-l);color:var(--green);}
.tab .badge.amber{background:var(--amber-l);color:var(--amber);}

/* Content */
.content{flex:1;overflow:hidden;position:relative;}
.panel{position:absolute;inset:0;overflow-y:auto;padding:24px;display:none;opacity:0;transition:opacity .2s;}
.panel.active{display:block;opacity:1;}

/* Company logos (SVG inline) */
.logo-wrap{width:44px;height:44px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:16px;font-weight:900;color:#fff;flex-shrink:0;position:relative;overflow:hidden;}
.logo-wrap.acme{background:linear-gradient(135deg,#2563eb,#1d4ed8);}
.logo-wrap.acme::after{content:'';position:absolute;top:-6px;right:-6px;width:20px;height:20px;background:rgba(255,255,255,.15);border-radius:50%;}
.logo-wrap.cloudpeak{background:linear-gradient(135deg,#16a34a,#15803d);}
.logo-wrap.cloudpeak::after{content:'';position:absolute;bottom:4px;left:50%;transform:translateX(-50%);border-left:8px solid transparent;border-right:8px solid transparent;border-bottom:10px solid rgba(255,255,255,.2);}
.logo-wrap.nexustech{background:linear-gradient(135deg,#7c3aed,#6d28d9);}
.logo-wrap.nexustech::after{content:'';position:absolute;inset:8px;border:2px solid rgba(255,255,255,.15);border-radius:4px;}
.logo-sm{width:32px;height:32px;border-radius:8px;font-size:12px;}

/* Card base */
.card{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:20px 24px;margin-bottom:14px;opacity:0;transform:translateY(10px);transition:all .4s cubic-bezier(.22,1,.36,1);}
.card.on{opacity:1;transform:translateY(0);}

/* Grid layouts */
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:16px;}
.grid-3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;}
@media(max-width:900px){.grid-2,.grid-3{grid-template-columns:1fr;}}

/* Status pills */
.status-pill{font-size:10px;font-weight:700;padding:4px 12px;border-radius:20px;text-transform:uppercase;letter-spacing:.5px;}
.pill-neg{background:var(--blue-l);color:var(--blue);}
.pill-ok{background:var(--green-l);color:var(--green);}
.pill-fail{background:var(--red-l);color:var(--red);}

/* Trade card — 2-column AI corp layout */
.trade-title{font-size:17px;font-weight:800;color:var(--t1);margin-bottom:16px;}
.trade-corps{display:grid;grid-template-columns:1fr auto 1fr;gap:16px;align-items:center;margin-bottom:16px;}
.corp-side{display:flex;flex-direction:column;align-items:center;text-align:center;gap:6px;padding:16px;background:var(--bg);border-radius:12px;}
.buyer-side{border:2px solid var(--blue-l);}
.seller-side{border:2px solid var(--purple-l);}
.corp-name{font-size:18px;font-weight:900;color:var(--t1);}
.corp-source{font-size:10px;color:var(--t3);font-weight:600;margin-top:2px;}
.corp-type{font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.5px;padding:4px 12px;border-radius:6px;}
.corp-buyer{background:var(--blue-l);color:var(--blue);}
.corp-vendor{background:var(--purple-l);color:var(--purple);}
.agent-tags{display:flex;flex-wrap:wrap;gap:4px;justify-content:center;margin-top:4px;}
.agent-tag{font-size:10px;font-weight:600;color:var(--t3);background:#f3f4f6;padding:2px 7px;border-radius:4px;}
.trade-center{display:flex;flex-direction:column;align-items:center;gap:6px;}
.trade-arrow{font-size:28px;color:var(--green);font-weight:900;line-height:1;}
.trade-total{font-size:28px;font-weight:900;font-family:'JetBrains Mono',monospace;color:var(--green);}
.trade-budget{font-size:13px;font-weight:700;font-family:'JetBrains Mono',monospace;color:var(--amber);}

/* Action log */
.action-log{background:var(--bg);border-radius:10px;padding:12px 16px;margin-bottom:12px;}
.log-step{font-size:12px;color:var(--t2);padding:5px 0;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px;}
.log-step:last-child{border:none;}
.log-step::before{content:'';width:6px;height:6px;border-radius:50%;background:var(--green);flex-shrink:0;}
.log-who{font-weight:700;padding:1px 6px;border-radius:3px;font-size:11px;}
.log-buyer{background:var(--blue-l);color:var(--blue);}
.log-seller{background:var(--purple-l);color:var(--purple);}

/* Pipeline steps */
.pipeline{display:flex;align-items:center;gap:0;overflow-x:auto;padding:8px 0;}
.pipe-step{font-size:10px;font-weight:700;padding:4px 10px;border-radius:4px;white-space:nowrap;background:#e5e7eb;color:var(--t3);text-transform:uppercase;letter-spacing:.4px;}
.pipe-step.done{background:var(--green-l);color:var(--green);}
.pipe-step.active{background:var(--blue-l);color:var(--blue);}
.pipe-arrow{font-size:14px;color:var(--t3);padding:0 3px;flex-shrink:0;}

/* Round card */
.round-row{display:flex;align-items:center;gap:10px;margin-bottom:8px;}
.deal-bar{height:6px;background:#e5e7eb;border-radius:3px;overflow:hidden;}
.deal-fill{height:100%;border-radius:3px;transition:width .6s cubic-bezier(.22,1,.36,1);}
.fill-blue{background:linear-gradient(90deg,var(--blue),#60a5fa);}
.fill-green{background:linear-gradient(90deg,var(--green),#4ade80);}
.deal-num{text-align:center;background:var(--bg);border-radius:8px;padding:8px 16px;}
.deal-num .dn-v{font-size:18px;font-weight:800;font-family:'JetBrains Mono',monospace;color:var(--t1);}
.deal-num .dn-v.amber{color:var(--amber);}

/* Accounting */
.ledger-row{display:flex;align-items:center;gap:14px;padding:14px 0;border-bottom:1px solid var(--border);}
.ledger-row:last-child{border:none;}
.ledger-vendor{display:flex;align-items:center;gap:10px;width:200px;}
.ledger-vendor .name{font-size:14px;font-weight:600;color:var(--t1);}
.ledger-acct{flex:1;font-size:13px;color:var(--t3);}
.ledger-amt{font-size:16px;font-weight:800;font-family:'JetBrains Mono',monospace;color:var(--red);}
.ledger-note{font-size:12px;color:var(--t3);margin-top:2px;}

/* Finance summary */
.fin-big{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:20px;}
.fin-box{background:var(--bg);border-radius:12px;padding:16px 20px;text-align:center;}
.fin-box .fv{font-size:28px;font-weight:900;font-family:'JetBrains Mono',monospace;}
.fin-box .fl{font-size:11px;color:var(--t3);margin-top:2px;text-transform:uppercase;letter-spacing:.5px;}

/* Vendor chart */
.vc{margin-top:16px;}
.vc-row{margin-bottom:12px;}
.vc-head{display:flex;align-items:center;gap:10px;margin-bottom:4px;}
.vc-name{font-size:14px;font-weight:600;color:var(--t1);flex:1;}
.vc-amt{font-size:14px;font-weight:700;font-family:'JetBrains Mono',monospace;color:var(--t1);}
.vc-track{height:12px;background:#f3f4f6;border-radius:6px;overflow:hidden;}
.vc-fill{height:100%;border-radius:6px;transition:width 1.5s cubic-bezier(.22,1,.36,1);}
.vc-fill.c0{background:linear-gradient(90deg,var(--blue),#93c5fd);}
.vc-fill.c1{background:linear-gradient(90deg,var(--purple),#c4b5fd);}
.nec-badge{font-size:10px;font-weight:700;background:var(--amber-l);color:var(--amber);padding:2px 8px;border-radius:4px;margin-left:6px;}

/* PR card */
.pr-card{border-left:4px solid var(--pink);}
.pr-title{font-size:17px;font-weight:700;color:var(--t1);margin-bottom:6px;line-height:1.4;}
.pr-body{font-size:14px;color:var(--t2);line-height:1.8;}
.pr-meta{font-size:11px;color:var(--t3);margin-top:8px;display:flex;align-items:center;gap:8px;}

/* Audit */
.audit-card{display:flex;align-items:center;gap:16px;padding:16px;background:var(--bg);border-radius:10px;margin-bottom:10px;}
.audit-info{flex:1;}
.audit-name{font-size:15px;font-weight:700;color:var(--t1);}
.audit-count{font-size:12px;color:var(--t3);font-family:'JetBrains Mono',monospace;}
.audit-status{font-size:14px;font-weight:800;font-family:'JetBrains Mono',monospace;padding:6px 14px;border-radius:8px;}
.audit-ok{background:var(--green-l);color:var(--green);}
.audit-bad{background:var(--red-l);color:var(--red);}

/* Partner */
.partner-card{display:flex;align-items:center;gap:16px;padding:16px;background:var(--bg);border-radius:10px;margin-bottom:10px;}
.partner-info{flex:1;}
.partner-bar{height:10px;background:#e5e7eb;border-radius:5px;overflow:hidden;margin-top:4px;}
.partner-fill{height:100%;border-radius:5px;background:linear-gradient(90deg,var(--green),#4ade80);transition:width 1.5s cubic-bezier(.22,1,.36,1);}
.partner-pct{font-size:28px;font-weight:900;font-family:'JetBrains Mono',monospace;color:var(--green);}
.partner-meta{font-size:12px;color:var(--t3);font-family:'JetBrains Mono',monospace;margin-top:2px;}

.sec-title{font-size:18px;font-weight:800;color:var(--t1);margin-bottom:16px;display:flex;align-items:center;gap:8px;}
.sec-icon{width:28px;height:28px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:800;color:#fff;}

::-webkit-scrollbar{width:6px;}::-webkit-scrollbar-thumb{background:#d1d5db;border-radius:3px;}
</style>
</head>
<body>
<header>
  <div class="brand"><b>Inc</b>Agent</div>
  <div style="border-left:1px solid var(--border);padding-left:16px;line-height:1.6;">
    <div style="font-size:15px;font-weight:900;color:var(--t1);">AI Corporation sold to another AI Corporation</div>
    <div style="font-size:12px;color:var(--t2);font-weight:600;">Lead &rarr; contract &rarr; invoice &rarr; bookkeeping &nbsp;&middot;&nbsp; <span style="color:var(--green);font-weight:700;">Zero human input</span></div>
  </div>
  <div class="spacer"></div>
  <div style="display:flex;align-items:center;gap:12px;">
    <div style="text-align:center;padding:6px 14px;background:#fef3c7;border-radius:10px;">
      <div style="font-size:20px;font-weight:900;font-family:'JetBrains Mono',monospace;color:var(--amber)" id="noHumanTimer">00:00</div>
      <div style="font-size:9px;font-weight:700;color:var(--amber);text-transform:uppercase;letter-spacing:.5px;">No human input</div>
    </div>
    <div class="live-pill" id="livePill" style="font-size:13px;padding:6px 16px;"><div class="dot" id="dotEl"></div><span id="liveText">LIVE</span></div>
  </div>
</header>

<div class="stats">
  <div class="st"><div class="st-n" style="color:#111;font-size:32px;">0</div><div class="st-l">Human Operators</div></div>
  <div class="st"><div class="st-n c-blue">2</div><div class="st-l">AI Corporations</div></div>
  <div class="st"><div class="st-n c-green" id="sV">$0</div><div class="st-l">Volume Transacted</div></div>
  <div class="st"><div class="st-n c-blue" id="sD">0</div><div class="st-l">Deals Closed</div></div>
  <div class="st"><div class="st-n c-amber" id="sN">--</div><div class="st-l">1099-NEC Vendors</div></div>
</div>

<div class="tabs" id="tabBar">
  <div class="tab active" data-tab="sales">Sales<span class="badge green" id="bSales">0</span></div>
  <div class="tab" data-tab="accounting">Accounting<span class="badge amber" id="bAcct">0</span></div>
  <div class="tab" data-tab="pr">PR / Communications<span class="badge" id="bPr">0</span></div>
  <div class="tab" data-tab="legal">Legal / Audit<span class="badge" id="bLegal">0</span></div>
  <div class="tab" data-tab="strategy">Strategy / BI<span class="badge" id="bBI">0</span></div>
</div>

<div class="content">
  <div class="panel active" id="p-sales"></div>
  <div class="panel" id="p-accounting"></div>
  <div class="panel" id="p-pr"></div>
  <div class="panel" id="p-legal"></div>
  <div class="panel" id="p-strategy"></div>
</div>

<script>
const $=id=>document.getElementById(id);
const fmt=n=>'$'+Math.round(n).toLocaleString();
const fmtD=n=>'$'+n.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
let vol=0,nD=0;
const counters={sales:0,accounting:0,pr:0,legal:0,strategy:0};

const logoClass={
  'Acme Corp':'acme','CloudPeak':'cloudpeak','NexusTech':'nexustech'
};
const logoSVG={
  'Acme Corp':`<svg width="26" height="26" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M16 3L5 8.5V15c0 6.2 4.7 12 11 13.5C23.3 27 28 21.2 28 15V8.5L16 3z" fill="rgba(255,255,255,0.15)" stroke="rgba(255,255,255,0.4)" stroke-width="1.5"/>
    <path d="M16 8L11 22h2.2l1.1-3.2h3.4L18.8 22H21L16 8zm0 4.2l1.2 5.6h-2.4L16 12.2z" fill="white"/>
  </svg>`,
  'CloudPeak':`<svg width="26" height="26" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M16 7l-7 11h14L16 7z" fill="rgba(255,255,255,0.9)"/>
    <path d="M11 14l-4 7h18l-4-7H11z" fill="rgba(255,255,255,0.5)"/>
    <path d="M8 25h16" stroke="rgba(255,255,255,0.8)" stroke-width="2" stroke-linecap="round"/>
    <circle cx="24" cy="14" r="5" fill="rgba(255,255,255,0.25)" stroke="rgba(255,255,255,0.5)" stroke-width="1.2"/>
    <path d="M22 14h4M24 12v4" stroke="rgba(255,255,255,0.7)" stroke-width="1.5" stroke-linecap="round"/>
  </svg>`,
  'NexusTech':`<svg width="26" height="26" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
    <circle cx="16" cy="16" r="3.5" fill="white"/>
    <circle cx="7" cy="9" r="2.8" fill="rgba(255,255,255,0.75)"/>
    <circle cx="25" cy="9" r="2.8" fill="rgba(255,255,255,0.75)"/>
    <circle cx="7" cy="23" r="2.8" fill="rgba(255,255,255,0.75)"/>
    <circle cx="25" cy="23" r="2.8" fill="rgba(255,255,255,0.75)"/>
    <line x1="13.5" y1="14.5" x2="9.5" y2="11" stroke="rgba(255,255,255,0.55)" stroke-width="1.5"/>
    <line x1="18.5" y1="14.5" x2="22.5" y2="11" stroke="rgba(255,255,255,0.55)" stroke-width="1.5"/>
    <line x1="13.5" y1="17.5" x2="9.5" y2="21" stroke="rgba(255,255,255,0.55)" stroke-width="1.5"/>
    <line x1="18.5" y1="17.5" x2="22.5" y2="21" stroke="rgba(255,255,255,0.55)" stroke-width="1.5"/>
    <line x1="7" y1="9" x2="7" y2="23" stroke="rgba(255,255,255,0.3)" stroke-width="1" stroke-dasharray="2 2"/>
    <line x1="25" y1="9" x2="25" y2="23" stroke="rgba(255,255,255,0.3)" stroke-width="1" stroke-dasharray="2 2"/>
  </svg>`
};
function logo(name,sm){
  const svg=logoSVG[name]||`<span style="font-size:${sm?10:14}px;font-weight:900;color:#fff">${name[0]}</span>`;
  return `<div class="logo-wrap ${sm?'logo-sm ':''} ${logoClass[name]||''}">${svg}</div>`;
}

// No-human timer
const t0ms=Date.now();
setInterval(()=>{
  const s=Math.floor((Date.now()-t0ms)/1000);
  const mm=String(Math.floor(s/60)).padStart(2,'0'),ss=String(s%60).padStart(2,'0');
  const el=$('noHumanTimer');if(el)el.textContent=mm+':'+ss;
},1000);

function anim(el,to,pre,dur){
  const from=parseFloat(el.dataset.v||'0');el.dataset.v=to;const t0=performance.now();
  (function f(now){const p=Math.min((now-t0)/dur,1),ease=1-Math.pow(1-p,4),cur=from+(to-from)*ease;
    el.textContent=pre==='$'?fmt(cur):Math.round(cur).toString();if(p<1)requestAnimationFrame(f);
  })(performance.now());
}
function show(el){requestAnimationFrame(()=>requestAnimationFrame(()=>el.classList.add('on')));}
function bump(tab){counters[tab]++;$('b'+{sales:'Sales',accounting:'Acct',pr:'Pr',legal:'Legal',strategy:'BI'}[tab]).textContent=counters[tab];}

// Tab switching
document.querySelectorAll('.tab').forEach(t=>{
  t.addEventListener('click',()=>{
    document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(x=>x.classList.remove('active'));
    t.classList.add('active');
    $('p-'+t.dataset.tab).classList.add('active');
  });
});

function addCard(panelId,html){
  const p=$('p-'+panelId),el=document.createElement('div');
  el.innerHTML=html;const c=el.firstElementChild;
  p.prepend(c);show(c);return c;
}

const es=new EventSource('/events');
es.onmessage=e=>{const d=JSON.parse(e.data);handle(d);};

function handle(d){switch(d.type){
case 'agent':break;

case 'sales':{
  bump('sales');
  if(d.action==='proposal'){
    addCard('sales',`<div class="card">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:14px">
        <span class="status-pill pill-neg">Proposal Sent</span>
        <span style="font-size:11px;color:var(--t3)">${d.ts}</span>
        <span style="margin-left:auto;font-size:10px;font-weight:700;background:#f0fdf4;color:var(--green);border:1px solid #bbf7d0;padding:3px 10px;border-radius:12px;">Agent-to-Agent</span>
      </div>
      <div class="trade-title">${d.title}</div>
      <div class="trade-corps">
        <div class="corp-side buyer-side">
          ${logo(d.from)}
          <div class="corp-name">${d.from}</div>
          <div class="corp-type corp-buyer">AI-run corporation</div>
          <div class="agent-tags"><div class="agent-tag">Sales Agent</div><div class="agent-tag">Outreach Agent</div></div>
        </div>
        <div class="trade-center">
          <div class="trade-arrow">&#8594;</div>
          <div style="font-size:11px;color:var(--t3);text-align:center">sends proposal to</div>
          <div style="margin-top:8px;font-size:11px;color:var(--t3)">${d.item} &middot; ${d.qty}</div>
          <div class="trade-budget">${d.budget}</div>
        </div>
        <div class="corp-side seller-side">
          ${logo(d.to)}
          <div class="corp-name">${d.to}</div>
          <div class="corp-type corp-vendor">External AI-run vendor</div>
          <div class="corp-source">Source: Moltbook (AI-agent network)</div>
          <div class="agent-tags"><div class="agent-tag">Procurement Agent</div></div>
        </div>
      </div>
      <div class="pipeline">
        <div class="pipe-step done">Lead</div><div class="pipe-arrow">›</div>
        <div class="pipe-step active">Proposal</div><div class="pipe-arrow">›</div>
        <div class="pipe-step">Accepted</div><div class="pipe-arrow">›</div>
        <div class="pipe-step">Contracted</div><div class="pipe-arrow">›</div>
        <div class="pipe-step">Invoiced</div><div class="pipe-arrow">›</div>
        <div class="pipe-step">Paid</div><div class="pipe-arrow">›</div>
        <div class="pipe-step">Reconciled</div>
      </div>
    </div>`);
  } else if(d.action==='round'){
    addCard('sales',`<div class="card" style="padding:12px 20px;background:var(--bg);border-color:var(--bg);">
      <div class="round-row">
        ${logo(d.from,true)}
        <div style="flex:1">
          <span style="font-size:12px;font-weight:700;color:var(--t2)">${d.from} Procurement Agent</span>
          <span style="font-size:12px;color:var(--t3);margin-left:6px">${d.detail}</span>
        </div>
        <span style="font-size:11px;color:var(--t3)">${d.ts}</span>
      </div>
      <div class="deal-bar"><div class="deal-fill fill-blue" style="width:${Math.round(d.round/d.of*100)}%"></div></div>
    </div>`);
  } else if(d.action==='closed'){
    addCard('sales',`<div class="card" style="border-left:4px solid var(--green);">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:14px">
        <span class="status-pill pill-ok">Deal Closed</span>
        <span style="font-size:11px;color:var(--t3)">${d.ts}</span>
        <span style="margin-left:auto;font-size:10px;font-weight:700;background:#f0fdf4;color:var(--green);border:1px solid #bbf7d0;padding:3px 10px;border-radius:12px;">Agent-to-Agent</span>
      </div>
      <div class="trade-title">${d.title}</div>
      <div class="trade-corps">
        <div class="corp-side buyer-side">
          ${logo(d.from)}
          <div class="corp-name">${d.from}</div>
          <div class="corp-type corp-buyer">AI-run corporation</div>
          <div class="agent-tags">
            <div class="agent-tag">Sales Agent</div>
            <div class="agent-tag">Legal Agent</div>
            <div class="agent-tag">Accounting Agent</div>
          </div>
        </div>
        <div class="trade-center">
          <div style="font-size:10px;font-weight:700;color:var(--t3);text-transform:uppercase;letter-spacing:.5px;margin-bottom:2px">Invoice Issued</div>
          <div class="trade-total">${fmtD(d.total)}</div>
          <div style="font-size:10px;font-weight:700;color:var(--t3);text-transform:uppercase;letter-spacing:.5px;margin-top:2px">Contract Value</div>
          <div style="font-size:12px;color:var(--t2);margin-top:2px">${typeof d.qty==='number'?d.qty.toLocaleString():d.qty} &times; ${fmtD(d.price)}</div>
        </div>
        <div class="corp-side seller-side">
          ${logo(d.to)}
          <div class="corp-name">${d.to}</div>
          <div class="corp-type corp-vendor">External AI-run vendor</div>
          <div class="corp-source">Source: Moltbook (AI-agent network)</div>
          <div class="agent-tags">
            <div class="agent-tag">Procurement Agent</div>
            <div class="agent-tag">AP Agent</div>
          </div>
        </div>
      </div>
      <div class="action-log">
        <div class="log-step"><span class="log-who log-buyer">${d.from} / Sales Agent</span> sent proposal to external counterparty</div>
        <div class="log-step"><span class="log-who log-seller">${d.to} / Procurement Agent</span> accepted &mdash; contract signed autonomously</div>
        <div class="log-step"><span class="log-who log-buyer">${d.from} / Accounting Agent</span> issued invoice &mdash; ${fmtD(d.total)}</div>
      </div>
      <div class="pipeline">
        <div class="pipe-step done">Lead</div><div class="pipe-arrow">›</div>
        <div class="pipe-step done">Proposal</div><div class="pipe-arrow">›</div>
        <div class="pipe-step done">Accepted</div><div class="pipe-arrow">›</div>
        <div class="pipe-step done">Contracted</div><div class="pipe-arrow">›</div>
        <div class="pipe-step done">Invoiced</div><div class="pipe-arrow">›</div>
        <div class="pipe-step done">Paid</div><div class="pipe-arrow">›</div>
        <div class="pipe-step done">Reconciled</div>
      </div>
    </div>`);
  }
  break;
}

case 'kpi_add':
  vol+=d.vol;nD+=d.deals;anim($('sV'),vol,'$',1200);anim($('sD'),nD,'',400);break;

case 'accounting':{
  bump('accounting');
  if(d.action==='expense'){
    addCard('accounting',`<div class="card">
      <div class="ledger-row">
        <div class="ledger-vendor">${logo(d.vendor,true)}<div class="name">${d.vendor}</div></div>
        <div class="ledger-acct">${d.account}<div class="ledger-note">${d.note||''} / Ref: ${d.ref}</div></div>
        <div class="ledger-amt">-${fmtD(d.amount)}</div>
      </div>
    </div>`);
  } else if(d.action==='1099_alert'){
    addCard('accounting',`<div class="card" style="border-left:4px solid var(--amber);background:#fffbeb;">
      <div style="display:flex;align-items:center;gap:10px">
        ${logo(d.vendor,true)}
        <div><div style="font-size:14px;font-weight:700;color:var(--amber)">1099-NEC Alert</div>
        <div style="font-size:13px;color:var(--t2)">${d.note}</div></div>
      </div>
    </div>`);
  } else if(d.action==='report'){
    let vhtml='';
    const mx=Math.max(...d.vendors.map(v=>v.paid));
    d.vendors.forEach((v,i)=>{
      const pct=((v.paid/mx)*100).toFixed(0);
      const nec=v.nec?'<span class="nec-badge">1099-NEC</span>':'';
      vhtml+=`<div class="vc-row"><div class="vc-head">${logo(v.name,true)}<span class="vc-name">${v.name}${nec}</span><span class="vc-amt">${fmtD(v.paid)}</span></div>
        <div class="vc-track"><div class="vc-fill c${i%2}" data-w="${pct}%"></div></div></div>`;
    });
    const el=addCard('accounting',`<div class="card">
      <div class="sec-title"><div class="sec-icon" style="background:var(--amber)">F</div>FY2026 Financial Report</div>
      <div class="fin-big">
        <div class="fin-box"><div class="fv" style="color:var(--red)">${fmtD(d.expenses)}</div><div class="fl">Total Expenses</div></div>
        <div class="fin-box"><div class="fv" style="color:var(--green)">${fmtD(d.income)}</div><div class="fl">Total Income</div></div>
        <div class="fin-box"><div class="fv" style="color:var(--amber)">${fmtD(d.net)}</div><div class="fl">Net P&L</div></div>
      </div>
      <div style="display:flex;gap:24px;margin-bottom:16px">
        <div><span style="font-size:24px;font-weight:900;font-family:'JetBrains Mono',monospace;color:var(--t1)">${d.records}</span><span style="font-size:12px;color:var(--t3);margin-left:6px">transactions</span></div>
        <div><span style="font-size:24px;font-weight:900;font-family:'JetBrains Mono',monospace;color:var(--amber)">${d.nec}</span><span style="font-size:12px;color:var(--t3);margin-left:6px">1099-NEC vendors</span></div>
      </div>
      <div class="vc">${vhtml}</div>
    </div>`);
    setTimeout(()=>{el.querySelectorAll('.vc-fill').forEach(b=>{b.style.width=b.dataset.w;});},200);
  }
  break;
}

case 'kpi_finance':
  anim($('sE'),d.expenses,'$',1200);anim($('sN'),d.nec,'',400);break;

case 'pr':{
  bump('pr');
  addCard('pr',`<div class="card pr-card">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
      ${logo(d.partner||'Acme Corp',true)}${logo('Acme Corp',true)}
      <span class="status-pill" style="background:var(--pink-l);color:var(--pink)">Press Release</span>
      <span style="font-size:11px;color:var(--t3)">${d.ts}</span>
    </div>
    <div class="pr-title">${d.title}</div>
    <div class="pr-body">${d.body}</div>
  </div>`);
  break;
}

case 'legal':{
  bump('legal');
  let rows='';
  d.agents.forEach(a=>{
    const cls=a.ok?'audit-ok':'audit-bad';
    const txt=a.ok?'VERIFIED':'CORRUPTED';
    rows+=`<div class="audit-card">${logo(a.name,true)}
      <div class="audit-info"><div class="audit-name">${a.name}</div><div class="audit-count">${a.entries} entries in hash chain</div></div>
      <div class="audit-status ${cls}">${txt}</div></div>`;
  });
  addCard('legal',`<div class="card">
    <div class="sec-title"><div class="sec-icon" style="background:var(--cyan)">A</div>Ledger Integrity Verification (SHA-256)</div>
    <div style="font-size:13px;color:var(--t2);margin-bottom:16px;line-height:1.6">Hash-chain verification of all agent transaction ledgers. Each entry contains the SHA-256 hash of the prior entry — any tampering is immediately detected.</div>
    ${rows}
  </div>`);
  break;
}

case 'strategy':{
  bump('strategy');
  let rows='';
  d.partners.forEach(p=>{
    const pct=(p.rate*100).toFixed(0);
    rows+=`<div class="partner-card">${logo(p.name)}
      <div class="partner-info"><div style="font-size:15px;font-weight:700;color:var(--t1)">${p.name}</div>
        <div class="partner-bar"><div class="partner-fill" data-w="${pct}%"></div></div>
        <div class="partner-meta">${p.trades} trades / avg $${p.avg.toFixed(0)} per unit</div>
      </div>
      <div class="partner-pct">${pct}%</div>
    </div>`;
  });
  const el=addCard('strategy',`<div class="card">
    <div class="sec-title"><div class="sec-icon" style="background:var(--purple)">BI</div>Partner Reliability Analysis</div>
    <div style="font-size:13px;color:var(--t2);margin-bottom:16px;line-height:1.6">Reliability scores calculated from trade history. Based on negotiation success rate, average unit price, and trade count — used for partner selection in future procurement.</div>
    ${rows}
  </div>`);
  setTimeout(()=>{el.querySelectorAll('.partner-fill').forEach(b=>{b.style.width=b.dataset.w;});},300);
  break;
}

case 'done':{
  $('dotEl').style.background='var(--blue)';$('dotEl').style.animation='none';
  $('liveText').textContent='COMPLETE';
  $('livePill').style.background='var(--blue-l)';$('livePill').style.color='var(--blue)';
  ['sales','accounting','pr','legal','strategy'].forEach(tab=>{
    addCard(tab,`<div class="card" style="background:linear-gradient(135deg,#eff6ff,#ede9fe);border:2px solid var(--blue);text-align:center;padding:28px;">
      <div style="font-size:20px;font-weight:900;color:var(--t1)">AI Corporation transacted with AI Corporation</div>
      <div style="font-size:13px;color:var(--t2);margin-top:10px;line-height:1.8">
        <b>0 human operators &nbsp;&middot;&nbsp; 2 AI corporations &nbsp;&middot;&nbsp; 6 workflow steps completed</b><br>
        Sales, contract, invoice &amp; bookkeeping — fully autonomous.<br>
        <span style="color:var(--green);font-weight:700;">No human input detected throughout entire session.</span>
      </div>
    </div>`);
  });
  es.close();break;
}
}}
</script>
</body>
</html>"""


async def index(req):
    return HTMLResponse(PAGE)

app = Starlette(routes=[Route("/", index), Route("/events", sse_stream)])

@app.on_event("startup")
async def startup():
    asyncio.create_task(run_simulation())
    async def ob():
        await asyncio.sleep(1)
        webbrowser.open("http://localhost:3000")
    asyncio.create_task(ob())

if __name__ == "__main__":
    print("IncAgent Live Dashboard: http://localhost:3000")
    uvicorn.run(app, host="0.0.0.0", port=3000, log_level="warning")
