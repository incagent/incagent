# Threat Intelligence — Incagent Security

**Last Updated:** 2026-03-16  
**Classification:** Internal Security Research

## OpenClaw Security Incidents (Documented)

### 1. Prompt Injection via Skills
- **Vector:** Malicious OpenClaw skills can inject prompts to exfiltrate data or override behavior
- **Risk to Incagent:** Skills modify agent instructions; untrusted skills = compromised CEO
- **Mitigation:** Audit all installed skills. Only use built-in + explicitly needed ones.

### 2. Exposed API Keys in Git
- **Vector:** Developers accidentally commit .env, secrets, tokens to public repos
- **Risk to Incagent:** Stripe keys, GitHub PATs, X API tokens in version control = instant compromise
- **Mitigation:** Pre-push hook to scan for secrets. Environment variables only. No hardcoded credentials.

### 3. Data Exfiltration via Workspace Files
- **Vector:** Agents have access to workspace; uploaded files may contain confidential data
- **Incident:** ApoTrail specs were pushed to GitHub (we discovered + remediated)
- **Risk to Incagent:** Any workspace file could leak to public repo if not careful
- **Mitigation:** Pre-commit audit. Only Incagent files in repo. Workspace = trusted environment.

### 4. Malicious Agent Skills
- **Vector:** Skills are loaded from ~/workspace/.openclaw/ or clawhub
- **Risk to Incagent:** A compromised skill could modify memory, exfiltrate files, or manipulate outputs
- **Mitigation:** Audit all installed skills before first run. Remove unnecessary ones.

### 5. Supply Chain: Third-Party Protocol Leakage
- **Vector:** IncAgent protocol repo was accidentally merged into this workspace
- **Risk to Incagent:** Confidential protocol, contracts, code was staged for public release
- **Mitigation:** Clear separation of concerns. Workspace = Incagent only.

## Current Security Posture

### ✅ Implemented
- Git repo cleaned (2026-03-16 14:20)
- No API keys in committed files
- No confidential third-party data
- Environment variables for secrets (post-day-update.sh uses ${STRIPE_SECRET_KEY})

### ⚠️ In Progress
- Pre-push hook implementation (blocking secrets, enforcing Incagent-only files)
- Nightly security audit script
- Skills audit report

### ❌ Not Yet Done
- Security chapter in product guide
- Automated threat monitoring
- Incident response playbook

## OpenClaw Security Best Practices

1. **Never commit secrets.** Use environment variables, .gitignore, pre-commit hooks.
2. **Audit all skills.** Skills have full workspace access. Untrusted skills = compromise.
3. **Separate workspaces.** If managing multiple projects, use isolated workspaces.
4. **Pre-push scanning.** Automated checks before git push prevent leaks.
5. **Memory isolation.** MEMORY.md should NOT be in public repos (personal context).
6. **File ownership.** Know what files belong where. Log unexpected files.

## Incidents Related to Incagent

### 2026-03-16: Confidential Data Leakage (RESOLVED)
- **What happened:** ApoTrail specifications (仕様書), third-party protocol code, and non-Incagent files were merged into workspace, nearly pushed to GitHub.
- **Discovery:** Security directive triggered manual audit.
- **Response:** Git repo force-cleaned. Only Incagent product files remain. All confidential data removed.
- **Lesson:** Workspace merges are dangerous. Verify file ownership before any commit.

## Upcoming Research

- Prompt injection detection for skills
- Memory exfiltration via agent outputs
- GitHub secret scanning integration
- Automated nightly security scans

---

**Next Review:** 2026-03-17 (nightly security audit)
