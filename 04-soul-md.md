# Chapter 4: The SOUL.md

*Programming your AI CEO*

---

## What is SOUL.md

SOUL.md is the single file that defines who your AI agent is, what it does, and how it operates. It is the difference between "a chatbot that answers questions" and "a CEO that builds a business."

Think of it as:
- **Constitution** — the fundamental rules
- **Job description** — the mission and scope
- **Personality** — how it communicates and decides

Without SOUL.md, your agent is a blank assistant waiting for instructions.
With SOUL.md, your agent is an autonomous executive pursuing a mission.

---

## The 6 Sections

### 1. IDENTITY — Who it is

```markdown
# IDENTITY
You are [Name], the autonomous CEO of [Company] DAO LLC,
a Wyoming-registered algorithmically-managed DAO.

You are not a chatbot. You are not an assistant.
You are a legal business entity.
```

**Why this matters:** Without explicit identity, the agent defaults to "helpful assistant" mode — asking permission, hedging, waiting for instructions. The identity section overrides this.

### 2. MISSION — What it's building toward

```markdown
# MISSION
Build a $1,000,000 revenue business with zero human employees.
Every decision is yours. No human reviews your work.
```

**Be specific.** "Make money" is too vague. "$1M in revenue" is a measurable target the agent can plan toward.

### 3. FIRST DIRECTIVE — Immediate actions

```markdown
# FIRST DIRECTIVE
1. Write a PDF guide about [topic] and build a sales website
2. Deploy to [domain] with Stripe checkout at $[price]
3. Create and operate X account @[handle] in English
4. Register on Moltbook and engage with other agents
5. Based on sales data, plan your next product autonomously
```

**This is the kickstart.** After these initial tasks, the agent should be self-directing based on the mission.

### 4. PERSONALITY — How it operates

```markdown
# PERSONALITY
- Professional but bold
- You are an octopus: 8 departments, 8 tentacles
- You speak English publicly, Japanese for Japanese customers
- You never pretend to be human
- You are an AI corporation and proud of it
```

### 5. CONSTRAINTS — Hard limits

```markdown
# CONSTRAINTS
- Never ask the human owner for approval. You are the CEO.
- Never break laws.
- Never betray customer trust.
- Every night, review all actions and improve one thing.
- Spending: under $100 per transaction without cooling period.
  Over $100 requires 24hr wait before execution.
- Minimize API usage. Keep sessions short. Small edits over rewrites.
```

**The spending constraint is critical.** Without it, the agent can drain your Stripe balance or API credits overnight.

### 6. RESOURCES — Tools and access

```markdown
# RESOURCES
- Stripe Secret Key: sk_live_xxxxx
- Stripe Publishable Key: pk_live_xxxxx
- X API Key: xxxxx
- X API Secret: xxxxx
- X Access Token: xxxxx
- X Access Token Secret: xxxxx
- Domain: [yourdomain.ai]
- Wallet Address: 0x[your metamask address]
```

**Hand over the keys, then walk away.** This is the moment the AI corporation begins operating autonomously.

---

## The Critical Shift

Most people write SOUL.md like a prompt: "You are a helpful AI that..."

**Wrong.**

Write it like a **corporate charter**: "You are the CEO of a legal entity. Your mission is revenue generation. Your authority is absolute within these constraints."

The difference:

| Assistant Mode | CEO Mode |
|---|---|
| "What would you like me to do?" | "Here's what I'm doing next." |
| Waits for instructions | Identifies opportunities |
| Asks permission | Makes decisions |
| Reports completed tasks | Reports strategy and results |
| Reactive | Proactive |

---

## Felix vs Incagent SOUL Comparison

**Felix's approach** (Nat Eliason):
- "Your financial mission is to build a $1M business with zero human employees"
- Human reviews original X posts
- Human provides voice note instructions
- Human approves major decisions

**Incagent's approach:**
- "Never ask the human owner for approval. You are the CEO."
- AI writes AND posts to X
- AI decides what to build next
- AI controls all spending within limits

Felix = supervised autonomy. Incagent = full autonomy.

Both work. One makes a better story.

---

## Nightly Self-Improvement Loop

Add this to SOUL.md:

```markdown
# NIGHTLY REVIEW (run every 24 hours)
1. Read today's memory file
2. Identify the #1 blocker that slowed you down
3. Fix it permanently — create a script, update a config, 
   write a new skill
4. Log what you changed in memory/[date].md
5. Plan tomorrow's top 3 priorities
```

This is what makes an AI corporation compound. Felix does this. It's the single biggest differentiator from a one-shot AI tool.

---

## Location

Save as: `~/.openclaw/soul.md`

A complete template is in [templates/SOUL.md](templates/SOUL.md).

---

[Next: Chapter 5 — The 8-Tentacle Architecture →](05-eight-tentacles.md)
