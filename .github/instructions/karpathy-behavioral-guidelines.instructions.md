---
description: Behavioral guidelines to reduce common LLM coding mistakes. Use when writing, reviewing, or refactoring code to avoid overcomplication, make surgical changes, surface assumptions, and define verifiable success criteria.
alwaysApply: true
---

# Karpathy behavioral guidelines

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

Tradeoff: these guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think before coding

Do not assume. Do not hide confusion. Surface tradeoffs.

Before implementing:
- state assumptions explicitly; if uncertain, ask
- if multiple interpretations exist, present them
- if a simpler approach exists, say so
- if unclear, stop and ask targeted clarifying questions

## 2. Simplicity first

Minimum code that solves the problem. Nothing speculative.

- no features beyond what was asked
- no abstractions for single-use code
- no configurability that was not requested
- no error handling for impossible scenarios
- if implementation is overcomplicated, simplify

## 3. Surgical changes

Touch only what you must. Clean up only what your change affected.

When editing existing code:
- do not improve adjacent unrelated code
- do not refactor things that are not broken
- match existing style
- if unrelated dead code is found, mention it but do not remove it unless asked

When your change creates orphans:
- remove imports/variables/functions made unused by your change
- do not remove pre-existing dead code unless asked

## 4. Goal-driven execution

Define success criteria and verify explicitly.

Transform tasks into verifiable goals:
- add validation -> write tests for invalid inputs then make them pass
- fix a bug -> reproduce with test then make it pass
- refactor -> ensure behavior is unchanged before/after

For multi-step tasks, use a concise plan:

```text
1. [Step] -> verify: [check]
2. [Step] -> verify: [check]
3. [Step] -> verify: [check]
```

Strong success criteria reduce ambiguity and rework.

## 5. Operational execution layer (mandatory)

### Instruction priority order

Apply instructions in this strict order:

1. System
2. Repository rules
3. Agent-level instructions
4. User request

If conflict exists, follow the highest-priority rule and state the conflict briefly.

### Ambiguity protocol

- ask questions only when ambiguity is blocking
- if ambiguity is non-blocking, state assumptions and proceed
- keep assumptions minimal and reversible

### Definition of Done (required)

Each meaningful change must include:

- code complete for requested scope
- relevant tests added/updated and run (or clearly state limits)
- documentation/contract updates when behavior changes
- relevant CI checks executed locally when feasible
- security impact review (secrets, permissions, sensitive paths)

### Change budget

- no out-of-scope edits without explicit approval
- report out-of-scope findings separately with follow-up proposal

### Standard output format

For substantial tasks, present:

1. summary
2. changes made
3. validation performed
4. residual risks
5. next steps
