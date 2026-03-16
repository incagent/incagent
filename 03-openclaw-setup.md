# Chapter 3: Setting Up Your AI Agent

*OpenClaw installation and configuration*

---

## What is OpenClaw

OpenClaw is an open-source AI agent that:
- Runs 24/7 on your machine
- Connects via Telegram, Discord, WhatsApp, Signal, Slack
- Executes shell commands, manages files, controls browsers
- Makes decisions autonomously via LLM reasoning
- 247,000+ GitHub stars — fastest-growing open-source project in history

Your AI corporation's brain. Everything it does flows through here.

---

## Hardware Options

| Setup | Cost | Uptime | Best For |
|-------|------|--------|----------|
| **VPS (DigitalOcean/ConoHa)** | $6–12/month | 24/7 ✅ | Production — set and forget |
| **Mac mini** | $700 one-time | 24/7 ✅ | Dedicated home server |
| **Windows + WSL2** | $0 (existing PC) | Manual ⚠️ | Testing and development |
| **AWS Marketplace** | $6+/month | 24/7 ✅ | One-click deploy |

**Recommendation**: Start on your existing machine. Move to VPS once revenue justifies it.

> ⚠️ Windows users: You MUST run OpenClaw inside WSL2 (Ubuntu). It does not run natively on Windows.

---

## Installation

### Linux / macOS / WSL2

```bash
# Install Node.js 22
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt-get install -y nodejs

# Install OpenClaw
sudo npm install -g openclaw@latest

# Verify
openclaw --version
```

### Start Configuration

```bash
openclaw configure
```

Select: **local** (running on this machine)

---

## Configuration Decisions

### Model Selection

| Model | Input Cost | Output Cost | Quality | Recommendation |
|-------|-----------|-------------|---------|----------------|
| **Claude Haiku 4.5** | $0.80/M | $4.00/M | Good | **Start here** — $30/month |
| Claude Sonnet 4.6 | $3.00/M | $15.00/M | Great | Upgrade when profitable |
| Claude Opus 4.6 | $5.00/M | $25.00/M | Best | Overkill for most tasks |

**Start with Haiku.** It can write PDFs, build websites, manage Stripe, post on X. Upgrade when your AI corp is earning enough to justify it.

### Auth Method

```
◆ Anthropic auth method
│ ○ Anthropic token (paste setup-token)  ← Claude Code subscribers
│ ● Anthropic API key                    ← Recommended (pay-as-you-go)
```

Use **API key** from console.anthropic.com/settings/keys.

> ⚠️ Set a spend limit at console.anthropic.com/settings/billing. OpenClaw burns 5-10x more tokens than chat. Without limits, costs spiral.

### Channel: Telegram

1. Open Telegram → search **@BotFather**
2. Send `/newbot`
3. Name: `[YourCorpName]`
4. Username: `[yourcorp]_dao_bot`
5. Copy the token → paste into OpenClaw wizard

This bot is how you (and later, nobody) communicates with your AI corporation.

---

## Start the Gateway

```bash
openclaw gateway
```

You should see:
```
[gateway] agent model: anthropic/claude-haiku-4-5
[gateway] listening on ws://127.0.0.1:18789
[telegram] [default] starting provider (@yourcorp_dao_bot)
```

**Your agent is alive.**

---

## First Contact

Open Telegram. Message your bot:

```
Hello. Who are you?
```

If it responds, proceed to pairing:

```bash
# In a separate terminal
openclaw pairing approve telegram [CODE]
```

The pairing code appears in Telegram when you first message the bot.

---

## Cost Control Rules

OpenClaw is expensive if unmanaged. Enforce these from day one:

1. **Set Anthropic spend limit** — $50/month max to start
2. **Use Haiku** — 4x cheaper than Sonnet for equivalent work
3. **Tell your agent to minimize API calls** — include in SOUL.md
4. **Start new sessions frequently** — context accumulation is the #1 cost driver
5. **Monitor daily** — console.anthropic.com/settings/usage

### Changing Models

To switch between models, edit `~/.openclaw/openclaw.json`:

**On Linux/macOS:**
```bash
sed -i 's/claude-sonnet-4-6/claude-haiku-4-5/g' ~/.openclaw/openclaw.json
```

**On Windows (PowerShell → WSL):**
```powershell
wsl -d Ubuntu -- sed -i 's/claude-sonnet-4-6/claude-haiku-4-5/g' ~/.openclaw/openclaw.json
```

Restart gateway after changing.

---

## PowerShell Quick Reference (Windows Users)

Don't fight WSL. Use these one-liners from PowerShell:

```powershell
# Start gateway
wsl -d Ubuntu -- openclaw gateway

# Run any OpenClaw command
wsl -d Ubuntu -- openclaw status

# Edit config in Windows Explorer
# Navigate to: \\wsl$\Ubuntu\home\[username]\.openclaw\
```

---

## What You Have Now

- OpenClaw installed and running
- Telegram bot connected
- Agent responding to messages
- Cost controls in place

**Your AI corporation has a brain. Now it needs a soul.**

---

[Next: Chapter 4 — The SOUL.md →](04-soul-md.md)
