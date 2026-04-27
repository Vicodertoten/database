---
owner: database
status: stable
last_reviewed: 2026-04-27
source_of_truth: docs/runbooks/security-incident-runbook.md
scope: runbook
---

# Security Incident Runbook

This runbook defines the mandatory response for accidental secret exposure in this repository.

## Scope

Use this process when any credential or sensitive token is committed, logged, or published in versioned artifacts.

Examples:

- database URLs with embedded credentials
- API keys
- access tokens
- private certificates

## Immediate Response

1. Identify all exposed secrets and impacted systems.
2. Revoke and rotate all exposed credentials immediately.
3. Stop publishing new artifacts until sanitized output is verified.
4. Open an incident record including:
   - exposure timestamp
   - affected secret types
   - rotation completion timestamp
   - impacted environments

## Repository Remediation

1. Sanitize current files in the working tree.
2. Purge leaked secrets from git history using an approved history-rewrite workflow.
3. Force-push rewritten branches and coordinate consumer rebase/reset.
4. Invalidate stale local clones when required by policy.

## Verification Checklist

Before closing the incident:

1. Run secret scanning on current tree and rewritten history.
2. Confirm rotated credentials are active and old credentials are disabled.
3. Confirm versioned artifacts no longer include raw secrets.
4. Confirm CI secret scan is green.
5. Document root cause and prevention actions.

## Prevention Rules

- Never commit raw credentials in docs, reports, fixtures, or logs.
- Always redact database URLs before output or persistence.
- Keep secret scanning blocking in CI for PRs and default branch pushes.
- Run local pre-check before opening a PR:
  - `gitleaks detect --source . --config .gitleaks.toml --redact --verbose`
