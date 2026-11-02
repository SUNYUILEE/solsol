---
name: solsol-calculator-export
description: Use when extracting or publishing the existing SOLSOL calculator for reuse with new sensor models while preserving its complete calculator, UI, API and evidence-quality capabilities.
---

The product is the existing research calculator and its accumulated engineering, not a new small coverage demo. Neutralizing model names is separate from preserving calculator capabilities. A green test suite for a reduced replacement cannot establish parity.

## Scope and evidence

Keep the source read-only; export to a sibling clone of the user-selected repository. Preserve prior remote history, including rejected exports. Record the latest exact request in research_ops and obtain preflight for the new scope.

Before implementation, run `python tools/calculator_export.py inventory --source SOURCE --output docs/migration/source-inventory.json`. Read `solsol/calculator/COMMON_UI_CONTRACT.md` and the mapped quality contracts. The inventory pins every common engine/web/quality file, its functions/controls and source hashes. It excludes old experiment data; it does not authorize deleting common functionality.

Start from the complete common calculator engine, existing workbench UI, client/API, quality package and research evidence structure. Replace the device-specific evaluator and metadata/form adapters. Do not substitute a minimal new UI, discard detailed analysis pages, or leave preserved files disconnected from execution.

For every source file and capability record a target path, exact hash, disposition, symbol replacements, runtime evidence and limitations in `docs/migration/capability-map.json`. Model-only exclusions must name the discarded physical assumption and confirm that no general calculator capability was removed. Reimplement necessary common functionality behind the new model boundary instead of excluding a coupled file wholesale.

## Required user-facing flows

Verify configuration/scenario editing, candidate/evaluation-area separation, arbitrary sensor types and objectives, random/Greedy/local-MILP/saved initialization, NSGA-II/III, reference directions, run/stop/progress/storage/recovery, generation populations and cumulative sets, history/observed paging/filter/representatives/Hamming, normal/enlarged/paired maps, comparison/parallel objectives, resource/budget studies, quality judgment and fixed-scale set/search metrics, independent reference/local/exact/MILP/refinement jobs with stop/resume/export, and explanation linked to exact raw evidence.

Keep a real callable API and client for other applications/AI. The UI and client must invoke the same configuration, execution, storage, diagnostics and evidence services. Include an API contract, examples, request identity/idempotency, model registration/capabilities, and provenance-bound exports. Do not fabricate unsupported model quality; unsupported capabilities remain explicit and block any affected parity claim.

Copy quality standards/gates/schemas without inheriting historical PASS reports. Separate integrity verification, search/set quality, posthoc diagnostics, and scientific validity. Preserve immutable X/F/G, configuration/evaluator/contract identity, seed/NFE/checkpoints, diagnostic origins and failures.

## Publication gate

`python tools/calculator_export.py check --inventory docs/migration/source-inventory.json --mapping docs/migration/capability-map.json --target . --output docs/migration/parity-report.json` must pass before claiming complete migration. Missing/unverified capabilities block that claim even if a package builds and a short browser smoke passes. Mutation tests must show this gate fails when a quality module/control/API evidence is removed.

Obtain independent scope review against the source inventory, not only code review of the export. Publish after evidence and selected-file secret/size/source-preservation checks. Verify remote SHA and provide the capability map plus explicit residual limits. Uploading a work-in-progress is not full completion; never relabel FAIL/NOT_RUN/BLOCKED as completed.
