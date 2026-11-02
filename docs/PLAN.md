# Neutral calculator implementation plan

Goal: extract reusable calculator mechanics into a separately runnable A/B/C coverage/resource research project and publish to the user-specified repository.

Architecture: Python model protocol, new example model, calculator runtime/storage, local HTTP service and browser UI. Source stays read-only. No imported models or old results.

Spec: DESIGN.md. User authorized immediate execution after clarifying exclusions; no further design approval is required.

- [ ] 1. Preserve source descriptors; extract neutral placement/inventory/Hamming/selection modules with lineage manifest. Verify allowed slots and exact inventory.
- [ ] 2. Implement explicit input contract and coverage/LOS model. Verify independent analytic union/joint/cost/resource witnesses and bad inputs.
- [ ] 3. Adapt generic solver orchestration, initializers, cumulative archive, accounting and checkpoints. Verify deterministic replay, exact tiny reference, NSGA-II/III and all initializers.
- [ ] 4. Add atomic checksummed storage, CLI and asynchronous service. Verify corruption rejection, full fixed-X replay and fresh-process read.
- [ ] 5. Add editable browser workflow and linked maps/results. Verify changes to parameters, run, stop, selected row, checkpoint, export and restoration in real browser.
- [ ] 6. Document reuse, limits and migration; independently review exact files, scan publication tree, verify source unchanged, commit selected paths, push and verify remote SHA.

Review focus: malformed/nonfinite or extreme input; empty feasible sets and all-zero slots; no declared relations; insufficient exact inventory; goal changes and contract identity; fixed-cost objective degeneracy; cancellation/failure during save; stored payload tampering; model/version mismatch; no historical model imports.
