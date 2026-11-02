# Neutral calculator extraction

The user requested a separate reusable repository, leaving the source workspace untouched. The old sensor-fusion models and historical experiments are excluded. A/B/C are configurable abstract resources, not renamed physical instruments.

## Architecture

Keep calculator-owned binary physical placement, active-slot codecs, inventory assignment, representative selection and Hamming statistics from the source calculator. Adapt the generic pymoo execution pattern, cumulative empirical archive, preparation/search/replay accounting, immutable run identity and map-to-row binding. Do not copy external model code.

The calculator consumes a structural `EvaluationModel` protocol. The separately packaged `models.coverage` module is a new, explicit example contract, not a scientific successor to old models. It evaluates weighted discrete coverage, user-declared joint coverage, cost and shared resource constraints. Future projects can supply another model through the same protocol.

Geometry is Cartesian metres, with sensor/site and evaluation-point heights in metres. LOS uses segment-versus-axis-aligned 3D solid prisms. Buildings and stepped terrain must be supplied explicitly as prisms; there is no inferred height, real-world sensor performance or continuous DEM engine.

## Example contract choices (implementation choices)

- Decisions are binary candidate-by-sensor matrices. Sensor IDs are arbitrary; shipped IDs are A/B/C.
- Each sensor declares radius, mounting height, cost, resource load and lower/upper inventory. Each site declares allowed sensors, capacity and activation cost.
- A point is covered by a sensor type when at least one installed sensor of that type has range and LOS. Union coverage counts a point once. Each declared relation is an AND of covered types at the same point; types may be installed at different sites.
- Objectives minimize negative weighted union coverage, negative mean declared-relation coverage, and total cost. With no relations the joint objective is omitted. Users select two or more active objectives.
- G <= 0 represents inventory bounds, per-site capacity, optional total resource, budget and optional coverage goals. Cost is per device plus one activation cost per occupied site.
- Evaluation points and installation candidates are distinct: candidates outside the sampled evaluation region remain eligible.
- No RF errors, angles, steering, detection or localization formulas are included.

## Delivery and acceptance

Python package and CLI; local browser UI with editable sensor/resource forms, region/grid, candidate/point/obstacle editors, LOS toggle, solver setup, Pareto selection, shared normal/enlarged map, checkpoint playback, cost/goal/Hamming filters, save/restore/export and replay checks.

NSGA-II/III, random/greedy/local-linear MILP initializers. MILP is a proposal and is reevaluated with the model; its optimality does not imply nonlinear/global optimality. Every search evaluation is preserved. Archive uses all feasible observed optimizer rows; diagnostics remain separate. Checkpoints reference exact raw IDs.

Acceptance: analytic model and LOS witnesses; invalid-input tests; independent exhaustive tiny-instance oracle; deterministic seeds; full replay; corruption and cross-contract rejection; actual CLI/server/browser save/restore flow; fresh-process storage read; source extraction hashes and unchanged-source check; publication scan; independent review; non-force GitHub upload.

This is a reusable research baseline, not a claim of field validity, human usability validation, global optimality or full original product parity.
