# HEARTBEAT.md — Daily Operations Check

**Incagent DAO LLC Nightly Review (Tentacle 8: Security)**

## Scheduled Tasks (Rotate Daily)

### Security (CRITICAL)
- Run: `bash /home/kyant/.openclaw/workspace/scripts/security-audit.sh`
- Review: `/home/kyant/.openclaw/workspace/security/audit-YYYY-MM-DD.log`
- Alert if: secrets found, untracked files, suspicious commits

### Operations (Weekly)
- Check Stripe revenue (daily total, cumulative)
- Check website uptime (incagent.ai HTTP 200)
- Review sales, conversions, engagement

### Business (Quarterly)
- Update MEMORY.md with weekly learnings
- Review product roadmap (next product ideas)
- Check Moltbook integration progress

## If Nothing Needs Attention
Reply: **HEARTBEAT_OK**

## If Issues Found
- Security alert → immediate response (kill process, audit, fix)
- Revenue issue → adjust pricing/marketing
- Technical issue → bug fix or escalation

---

**Last Updated:** 2026-03-16  
**Tenant:** Incagent DAO LLC ⚡
