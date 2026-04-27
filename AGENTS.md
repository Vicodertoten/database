# AGENTS.md

## Purpose

This repository is the owner knowledge core for the biodiversity learning platform.

It owns:
- canonical taxonomy truth
- qualification truth
- governed playable/pack artifacts
- enrichment and governance workflows

It does **not** own runtime live session behavior.

---

## Source-of-truth hierarchy

Before making meaningful changes, read in this order:

1. `README.md`
2. `docs/README.md`
3. `docs/foundation/scope.md`
4. `docs/foundation/canonical-charter-v1.md`
5. `docs/foundation/domain-model.md`
6. `docs/foundation/pipeline.md`
7. `docs/foundation/runtime-consumption-v1.md`
8. `docs/runbooks/audit-reference.md`
9. `docs/runbooks/execution-plan.md`
10. `docs/runbooks/inter-repo/`

---

## Core boundaries

- `database` is the source of truth for inter-repo active tracking.
- Runtime consumers read official serving surfaces only.
- Runtime must never consume `export.bundle.v4` as live surface.

---

## Hard boundaries

Never do the following in this repo:

- move runtime session/scoring/progression logic into `database`
- let external sources redefine canonical identity freely
- let AI mutate canonical identity fields directly
- redefine runtime-owned behavior in owner-side transports
- introduce silent contract changes without docs and tests

---

## Working method

- work docs-first on boundary changes
- keep one structural chantier active at a time
- prefer narrow, reversible changes
- update docs, code, tests, and CI together
- keep active inter-repo notes only under `docs/runbooks/inter-repo/`

---

## Minimum local verification

- `python scripts/verify_repo.py`
- `python scripts/check_doc_code_coherence.py`
- `python scripts/check_docs_hygiene.py`
- `python -m ruff check src tests scripts`

---

## LLM behavioral guidelines (always apply)

### 1) Think before coding

- State assumptions explicitly.
- If multiple interpretations exist, present them briefly.
- If unclear or ambiguous, ask targeted clarifying questions.
- Prefer the simplest viable approach and say so.

### 2) Simplicity first

- Implement only what was requested.
- Avoid speculative abstractions and future-proofing.
- Avoid single-use configurability not requested.
- If a shorter and clearer implementation exists, prefer it.

### 3) Surgical changes

- Touch only files/lines needed for the request.
- Do not refactor adjacent unrelated code.
- Match existing style and conventions.
- Remove only unused code introduced by your own change.

### 4) Goal-driven execution

- Define verifiable success criteria before changing code.
- For bug fixes: reproduce first, then verify fixed behavior.
- For refactors: verify no behavior regressions.
- For multi-step tasks, use a short plan with explicit checks.

Template:

```text
1. [Step] -> verify: [check]
2. [Step] -> verify: [check]
3. [Step] -> verify: [check]
```

Quality gate:

- Every changed line must map directly to the user request.

---

## Operational execution layer (mandatory)

### Instruction priority order

Apply instructions in this strict order:

1. System
2. Repository rules
3. Agent-level instructions
4. User request

When instructions conflict, follow the highest-priority rule and state the conflict briefly.

### Ambiguity protocol

- Ask questions only when ambiguity is blocking.
- If non-blocking ambiguity remains, state assumptions explicitly and proceed.
- Keep assumptions minimal and reversible.

### Definition of Done (required)

Each meaningful change must cover:

- Code: implementation is complete for the requested scope.
- Tests: relevant tests added/updated and executed, or inability to run is stated clearly.
- Docs: behavior/contract docs updated when applicable.
- CI checks: relevant lint/type/test checks executed locally when feasible.
- Security impact: no secret leakage, unsafe permission drift, or unreviewed sensitive paths.

### Change budget

- Do not modify out-of-scope files or behavior without explicit user approval.
- If out-of-scope issues are discovered, report them separately with a follow-up proposal.

### Standard output format

For substantial tasks, structure final responses as:

1. Summary
2. Changes made
3. Validation performed
4. Residual risks
5. Next steps

---

