# Local Lane Contract

A task prompt routed to a local-model lane is **contract-compliant** when it
satisfies R1–R6. Compliance is not a quality judgment on the task — it is a
prediction: contract-compliant tasks convert an open-ended search problem
into a lookup problem, which is the one thing local models reliably do well.

Full background and evidence: `LOCAL_LANE_CONTRACT_SPEC.md`. This file is the
short, citable rule text; `task_lint.py` implements it as a deterministic
checker.

## R1 — Exact paths

Every file to be read or modified is named by exact repo-relative path. No
"my alias file", no "the config".

**Failure mode prevented:** discovery loops. A model given "my alias file"
with no path has to guess where to look, and a local model's guess-then-list
loop is exactly the failure this contract exists to close (`gemma4:26b`
repeated an identical `list_dir` call and was stopped by the loop guard
without reaching step 2). Naming the path removes the guess.

## R2 — Anchored edits

Every modification specifies an anchor: a unique, verbatim fragment of
existing file content to patch against (maps directly to `patch_file`
`target_content`). Appends specify the anchor line to append after, or state
"append at end of file".

**Failure mode prevented:** misplaced edits. Without a verbatim anchor, a
model has to decide *where* in a file its change belongs — a second
degree-of-freedom hop on top of *which* file. An anchor converts "figure out
where this goes" into "find this exact string and act relative to it."

## R3 — One tool call per step

The task is an ordered list of steps, each executable as a single tool call.
No step requires the model to choose between tools or invent a substep.

**Failure mode prevented:** discovery loops and tool-choice thrashing,
alongside R1. A step that secretly bundles two actions ("update the alias
and verify it") forces the model to decide how to split the work; a
single-tool-call step has no such choice to get wrong.

## R4 — Explicit success criterion

The task states a machine-checkable postcondition ("the file now contains
the line X"; "command Y exits 0") so the model can self-terminate and the
grader can verify.

**Failure mode prevented:** non-termination wandering. A model with no
stated stopping condition either stops too early (misses the actual change)
or keeps "double-checking" indefinitely. A checkable postcondition gives it
— and the grader — a shared, unambiguous stop signal.

## R5 — Imperative, closed vocabulary

Commands, not goals. No negations doing load-bearing work, no "figure out",
"appropriately", "as needed", "somehow", "etc."

**Failure mode prevented:** re-introducing the degrees of freedom R1–R4 just
closed. A task can name exact paths and anchors and still hide a decision
inside a vague verb — "update it appropriately" asks the model to invent the
very substep the rest of the contract is designed to remove.

## R6 — Bounded scope

The task enumerates every file that may be touched. Anything else is out of
bounds.

**Failure mode prevented:** scope creep from a model treating an
under-specified task as license to "helpfully" touch adjacent files. Bounded
scope is also what makes a task's postcondition (R4) and grading safe to
automate — the grader only has to check the files the task admits to
changing.

## Reading a verdict

`task_lint.py` scores a prompt against R1–R6 and returns one of three
verdicts:

- **plan-shaped** — all six rules pass. Route to a local lane with
  confidence.
- **semi-shaped** — R1 passes but other rules are mixed. Local models may
  still flail; tighten the weakest rule before trusting the lane.
- **goal-shaped** — R1 fails. Treat as evidence the task needs either a
  frontier lane or a rewrite into plan-shaped form before a local lane sees
  it.

The linter is heuristic, not NLU, and is deliberately biased toward WARN
over FAIL when a rule's signal is ambiguous — see
`LOCAL_LANE_CONTRACT_SPEC.md` Deliverable 2 for the exact per-rule checks.
