# OpenClaw Skills Audit

**Incagent DAO LLC Security Posture**  
**Audit Date:** 2026-03-16

## Installed Skills (System-Wide)

### Currently Loaded (Critical Access Skills)
These skills have read/write access to the workspace and are loaded at runtime.

| Skill | Purpose | Risk Level | Status | Notes |
|-------|---------|-----------|--------|-------|
| coding-agent | Delegate code tasks to Claude Code, Codex, Pi | HIGH | ✅ Needed | Used for complex features. Monitor carefully. |
| healthcheck | Security hardening, risk audits | MEDIUM | ✅ Needed | Essential for ongoing security. |
| node-connect | OpenClaw connection troubleshooting | LOW | ✅ Needed | Safe. Connection diagnostics. |
| skill-creator | Create/audit AgentSkills | MEDIUM | ✅ Needed | Used for security/governance updates. Audit skill.md changes. |
| tmux | Remote control tmux sessions | MEDIUM | ✅ Kept | May need. Can be disabled if unused. |
| weather | Weather API queries | LOW | ✅ Optional | Not needed for Incagent. Can be unloaded. |

### Not Currently Used (Can Remove)
- oracle, ordercli, peekaboo, sag, session-logs, sherpa-onnx-tts
- slack, songsee, sonoscli, spotify-player
- summarize, things-mac, trello, video-frames, voice-call, wacli
- xurl (and any others not listed above)

## Risk Assessment

### High-Risk Vectors
1. **coding-agent** — Delegates to external model endpoints; can read workspace files
   - Mitigation: Only use for Incagent code. Review generated code before execution.
   
2. **skill-creator** — Can modify skill definitions; affects system behavior
   - Mitigation: Only use to audit trusted skills. Verify changes before applying.

3. **Any skill with shell execution** — Can run arbitrary commands
   - Mitigation: Disable if unused. Monitor script execution.

### Medium-Risk Vectors
- Workspace read access by any skill
- API key handling in skill configuration
- Memory access via skills

## Action Items

- [ ] Remove unused skills (weather, songsee, spotify, etc.)
- [ ] Document which skills touch the workspace
- [ ] Set up skill execution logging
- [ ] Create skill whitelisting policy

## Approved Skills for Incagent Operation

**CRITICAL (cannot disable):**
- healthcheck
- node-connect
- skill-creator

**APPROVED (conditional use):**
- coding-agent (code generation only, review required)
- tmux (if needed for automation)

**MUST REMOVE:**
- All entertainment/utility skills (weather, spotify, etc.)
- Any skill not directly supporting Incagent operations

---

**Next Review:** Weekly (every Monday)
