# SOLSOL reusable calculator

This repository is a neutral research baseline. The source workspace is separate and must never be modified through migration scripts. Do not import old sensor projects or inherit their result values, coordinates, defaults or scientific PASS claims.

Calculator owns initialization, search, ledger, archive, storage, replay and presentation. Model owns objectives, cost, constraints and coverage semantics. Use the public EvaluationModel boundary. Preserve candidate/sensor/axis order, config and implementation identity, raw X/F/G, all checkpoint and evaluation counters. Historical data is immutable; new contracts require new IDs.

Use apply_patch for text changes. Test analytic witnesses and failure cases before claiming correctness. Keep diagnostics/reference outputs separate from optimizer observations. Exact small-instance reference is not larger-problem global optimality. Do not represent browser automation as human usability validation.

Run tests and the real browser workflow after relevant changes. Keep migration lineage and verification evidence accurate. Publish only selected source/docs/test files; exclude secrets, runtime data, caches and environments. Never force-push or overwrite a stored run identity.
