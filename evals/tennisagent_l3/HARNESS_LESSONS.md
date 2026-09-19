# Harness lessons — Fusion L3 frontier and local lanes

This file records harness findings separately from model capability claims.

## H-001 — text CLI is not a custom tool executor

Direct Claude Haiku CLI rejected the external JSON executor framing as a
behavior override. A single accidental parseable response was not reproducible.
Native tool registration or a staged planner/executor/synthesis design is
required.

## H-002 — compact results are necessary but insufficient

Full swing telemetry reinjected into the frontier transcript caused noisy,
variable synthesis. Removing large arrays and retaining counts improved the
path, but did not solve the CLI contract boundary by itself.

## H-003 — staged protocol separates failure classes

The stable path is:

```text
planner JSON → deterministic local executor → compact evidence → synthesis
```

This made Haiku and Luna usable for bounded probes while exposing planner
formatting, placeholder, and synthesis failures independently.

## H-004 — semantic graders must recognize truthful negative states

Luna's phrase `no synchronized evidence` was initially marked wrong because the
grader only accepted a narrow list of missing-data phrases. The grader was
broadened and the same run became 6/6. Strict wording failures must remain
separate from semantic failures.

## H-005 — fixture claims must be instantiated

The L3.1 contradiction, metric-conflict, and ambiguity tasks were sometimes
run against live data without an actual contradiction/conflict/ambiguity. A
model cannot satisfy a positive-state grader when the substrate does not contain
the claimed state. Fixture manifests must include a preflight assertion that
the expected state exists before model execution.

## H-006 — turn limits create false capability failures

The first successor run scored 18/36 because a three-turn budget ended after
valid tool chains and before final synthesis. Completion budget and chain
completion must be measured separately.

## Operating rule

No frontier or local result is promoted until protocol validity, fixture-state
preflight, semantic grading, and final synthesis are independently evidenced.
