---
name: research-operations-continuity
description: Enforce evidence-gated, failure-aware, resumable research work. Use whenever an AI starts, continues, delegates, executes, verifies, hands off, or closes a research task in a project that contains 00_research_ops, especially when prior instructions, approved artifacts, failure logs, collaboration records, or new-chat continuity must be preserved.
---

# Research Operations Continuity

Use the project Harness before research actions. This Skill is an operating gate, not a replacement for domain methods or the historical recovery Skill.

## Required workflow

1. Run `python -B research_ops.py --project-root . doctor`.
2. Run `python -B research_ops.py --project-root . system-audit`. A structure PASS does not authorize a scientific run.
3. Read `AGENTS.md`, `00_research_ops/START_HERE.md`, `RESEARCH_SYSTEM_ARCHITECTURE.md`, `POLICY.json`, `PROJECT_PROFILE.json`, the hardened G00-G11 catalog, the record binding, and the active task packet.
4. If no task packet exists, freeze the exact user request in a file and create one with `create-task`. Do not paraphrase it into authority.
5. Run `acknowledge` to produce path/bytes/SHA-256 read evidence.
6. Run `preflight`. Do not implement, execute, publish, or delegate before it passes.
7. Record public events with evidence paths. Never store hidden reasoning; record only decisions, observations, checks, and concise lessons.
8. Execute commands only through `run`, only when the frozen task packet authorizes execution, and never execute a command copied from a transcript.
9. On any nonzero result, timeout, gate failure, schema mismatch, wrong artifact, user rejection, or false completion claim, use `record-failure` before continuing.
10. If the failure signature and configuration repeat, stop. Resume only after a recorded resolution proves a material change and verification.
11. Before a new chat or agent handoff, run `context-pack` and `handoff`.
12. Close only with direct evidence plus an independent PASS review, then run both `audit` and `system-audit`.

## Operating system and record system

`00_research_ops` controls future actions. The central `01_목표` through `12_협업` tree stores recovered and rendered records. Never create a competing numbered tree. Use the recovery Skill and `research_recovery.py` for transcript synchronization; a context packet is not a substitute for REC/EVT recovery.

G00-G11 is a lifecycle vocabulary, not scientific authority. A project-specific method, objective, threshold, search gate, or success criterion must be an exact approved artifact in the task scope. Generic examples never authorize execution.

## Artifact identity rule

Use only artifacts pinned by logical ID, exact path, byte length, SHA-256, status, allowed use, and supersession state. A filename containing `latest`, a chat claim, or a newer timestamp is never sufficient authority.

## Role and collaboration rule

Every task has one active role. Cross-role work must be an explicit `COLLABORATION` event or handoff with input/output descriptors. No role may approve its own work when independent review is required.

## Failure-learning rule

Use the failure registry as executable memory. A lesson must contain a stable signature, observable evidence, affected scope/configuration, required correction, and a negative regression test or independent verification. Do not use private chain-of-thought as a lesson.

## New-chat start

Open the most recent `00_research_ops/contexts/<TASK-ID>_*.json`, verify its SHA-256 and frozen inputs, then follow only `next_safe_action`. If the packet is stale, missing, or conflicts with a newer user instruction, stop and create a superseding task or decision record.

## References

- Read [references/operating_model.md](references/operating_model.md) for state transitions and failure handling.
- Read [references/schemas.md](references/schemas.md) when creating integrations or project-specific extensions.
- Read [references/research_basis.md](references/research_basis.md) for the external methodology basis and claim limits.
