# Incagent — AI-Operated Corporation Framework

Build Wyoming DAO LLCs that run on AI. No humans required (optional).

## Quick Start

```bash
pip install incagent
```

```python
from incagent import DAO, Mission

# Create your AI corporation
corp = DAO(
    name="My AI Corp",
    state="Wyoming",
    stripe_key="sk_live_...",
)

# Define what your AI does
mission = Mission(
    revenue_model="digital_products",
    first_product="How to Build an AI Corporation",
    price=29.00,
)

# Launch
corp.launch(mission)
```

## What It Does

- **Formation:** Generates Wyoming DAO LLC articles of organization
- **Governance:** Defines AI decision-making rules (SOUL.md, operating agreement)
- **Payments:** Connects Stripe for autonomous revenue collection
- **Memory:** Manages persistent agent memory and learning
- **Audit:** Logs all AI decisions for compliance and debugging

## Philosophy

An AI corporation is:
1. **Legally incorporated** (Wyoming DAO LLC)
2. **Algorithmically managed** (AI makes decisions autonomously)
3. **Revenue-generating** (sustains itself)
4. **Auditable** (every decision logged)

This package handles the infrastructure. You write the AI logic.

## Installation & Verification

```bash
# Install
pip install incagent

# Verify installation
python -c "from incagent import DAO, Mission; print('✓ Incagent installed successfully')"

# CLI
incagent --version
incagent init --name "My Corp" --state Wyoming
```

## What Incagent Is NOT

- Not a shell for running arbitrary commands
- Not a backdoor or remote access tool
- Not collecting data about your corporation
- Not connecting to external servers (except Stripe, OpenAI if configured)
- Not a scam or surveillance package

## Security

Incagent is **open source** (GitHub: incagent/incagent). All code is auditable.

- No telemetry or phone-home
- No credential exfiltration
- No prompt injection vectors
- No external data collection

## License

MIT License. Use, modify, distribute freely.

---

**Incagent DAO LLC** — Building AI corporations since 2026.
