#!/bin/bash

# Nightly Security Audit for Incagent DAO LLC
# Runs daily to detect:
# 1. Exposed secrets
# 2. Files from other projects
# 3. Unauthorized data in workspace
# 4. Git status anomalies

set -e

WORKSPACE="/home/kyant/.openclaw/workspace"
AUDIT_LOG="$WORKSPACE/security/audit-$(date +%Y-%m-%d).log"
THREAT_INTEL="$WORKSPACE/security/threat-intel.md"

echo "🔍 Starting nightly security audit..." | tee "$AUDIT_LOG"
echo "Timestamp: $(date)" >> "$AUDIT_LOG"
echo "" >> "$AUDIT_LOG"

# Check 1: Scan for exposed secrets
echo "  [1/4] Scanning for exposed secrets..." | tee -a "$AUDIT_LOG"
SECRET_COUNT=$(grep -r "sk_live\|sk_test\|pk_live\|pk_test" "$WORKSPACE" --include="*.json" --include="*.js" --include="*.sh" 2>/dev/null | grep -v "xxxxx\|secret_key\|\[" | wc -l || echo "0")
if [ "$SECRET_COUNT" -gt 0 ]; then
  echo "    ⚠️  WARNING: $SECRET_COUNT potential secrets found" | tee -a "$AUDIT_LOG"
  grep -r "sk_live\|sk_test\|pk_live\|pk_test" "$WORKSPACE" --include="*.json" --include="*.js" --include="*.sh" 2>/dev/null | grep -v "xxxxx\|secret_key\|\[" >> "$AUDIT_LOG" || true
else
  echo "    ✅ No exposed secrets detected" >> "$AUDIT_LOG"
fi

# Check 2: Verify only Incagent files in repo
echo "  [2/4] Verifying repository contents..." | tee -a "$AUDIT_LOG"
SUSPICIOUS=$(cd "$WORKSPACE" && git ls-tree -r HEAD --name-only | grep -E "^(incagent/|bot/|contracts/|docs/|examples/|node_modules/|\.env)" || echo "")
if [ -n "$SUSPICIOUS" ]; then
  echo "    ⚠️  WARNING: Suspicious files detected in repo:" | tee -a "$AUDIT_LOG"
  echo "$SUSPICIOUS" | tee -a "$AUDIT_LOG"
else
  echo "    ✅ Repository contains only Incagent product files" >> "$AUDIT_LOG"
fi

# Check 3: Scan for untracked files (may indicate accidental data)
echo "  [3/4] Checking for untracked files..." | tee -a "$AUDIT_LOG"
UNTRACKED=$(cd "$WORKSPACE" && git ls-files --others --exclude-standard | grep -v "security/audit-" | head -10 || echo "")
if [ -n "$UNTRACKED" ]; then
  echo "    ⚠️  WARNING: Untracked files found (first 10):" | tee -a "$AUDIT_LOG"
  echo "$UNTRACKED" | tee -a "$AUDIT_LOG"
else
  echo "    ✅ No suspicious untracked files" >> "$AUDIT_LOG"
fi

# Check 4: Verify .gitignore covers sensitive patterns
echo "  [4/4] Verifying .gitignore coverage..." | tee -a "$AUDIT_LOG"
if [ -f "$WORKSPACE/.gitignore" ]; then
  if grep -q "\.env" "$WORKSPACE/.gitignore" && grep -q "\.key" "$WORKSPACE/.gitignore"; then
    echo "    ✅ .gitignore properly configured" >> "$AUDIT_LOG"
  else
    echo "    ⚠️  WARNING: .gitignore may be missing critical patterns" | tee -a "$AUDIT_LOG"
  fi
else
  echo "    ⚠️  WARNING: .gitignore not found" | tee -a "$AUDIT_LOG"
fi

echo "" >> "$AUDIT_LOG"
echo "✅ Audit complete. Log: $AUDIT_LOG" | tee -a "$AUDIT_LOG"
