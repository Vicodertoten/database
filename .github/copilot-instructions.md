# Copilot Instructions

Primary source of guidance for this repository:

- `AGENTS.md`

Always apply these behavioral rules:

1. Think before coding.
2. Prefer the simplest implementation that solves the request.
3. Make surgical changes only.
4. Define verifiable success criteria and validate them.

Operational requirements:

1. Instruction priority: System > repository rules > agent instructions > user request.
2. Ambiguity protocol: ask only if blocking; otherwise state assumptions and proceed.
3. Mandatory DoD: code + tests + docs + relevant CI checks + security impact.
4. Change budget: no out-of-scope edits without explicit approval.
5. Standard output format for substantial tasks: summary, changes, validation, residual risks, next steps.

Do not silently introduce scope creep, architecture drift, or unrelated refactors.

When planning a phase, use the prompt template in `AGENTS.md` under:

- `Prompt template - phase planning`
