# Harness Requirements Spec (what a delegation harness must guarantee)

Status: **PROPOSED**, not implemented. Written 2026-08-21.
Companion to `LOCAL_LANE_CONTRACT_SPEC.md` and `GATED_RUNNER_SPEC.md`.
Evidence base: `docs/HARNESS_TURN_COST_ANECDOTES.md` entries 2026-08-20 and
2026-08-23.
`opr` is deprecated; the live local implementer is OpenCode (`opencode run`).

## Purpose

`LOCAL_LANE_CONTRACT_SPEC.md` shapes the **task** so a local model can succeed.
This spec constrains the **harness** that carries the task, which is a different
surface with a different cost structure.

The distinction is load-bearing because the two amortise over different
denominators:

| Investment | Amortises across | Denominator |
|---|---|---|
| A task gate (`tests/test_audio_ports.py`) | delegations within one task class | narrow |
| A harness property (this spec) | every task class ever run | wide |

Both are scaffolding cost in the sense of
`local-models-cost-frontier-tokens.md` §2.4 — frontier tokens spent building
verification apparatus rather than doing the work. Harness properties have the
wider denominator, so they are the higher-leverage place to spend it. That is an
arithmetic claim, not a preference, and it is the reason this spec exists
separately from the task contract.

## Scope boundary

This spec governs the **carrier**: process lifecycle, tool affordances, write
validation, invocation scope, and who is permitted to report an outcome. It does
not govern model choice, task phrasing, or ledger semantics.

It must not weaken the existing boundaries. `doctor` stays read-only and never
executes a stored verification command (`CLAUDE.md`). The harness is the only
component that executes a postcondition, per `GATED_RUNNER_SPEC.md` §3.

## Evidence — 2026-08-20 failure taxonomy

Approximately 22 delegations across `opr` and opencode on one machine in one
session. Failures classified by cause:

| Cause | Count | Attributable to the model? |
|---|---:|---|
| Harness flag bug (`--dir` caused a silent no-op exit) | 1 | No |
| Tool-call encoding (oversized `write_file` JSON did not parse) | 1 | No |
| Process lifecycle (backgrounded runs stayed alive; four agents raced one file) | 2 corruptions | No |
| Timeout producing nothing — invocation scope or prompt-assembly overhead | 3 | No |
| Timeout producing nothing — slow model | 2 | Partly |
| Edit-shaped task failure | 3 | Unclear; likely tool affordance |

**Reading.** The local lane's cost that session was dominated by harness defects,
not model incapacity. Only the last two rows are candidates for a capability
claim, and the edit row is confounded by the absence of an anchored-replace
primitive: a model rewriting a mid-file region without one is regenerating free
-hand. The same three models passed a new-file task on the identical gate.

**Confounds, stated so nobody cites this as a rate.** One session, one machine,
no per-turn token accounting, categorisation by judgement, and the supervisor was
also the reporter. This is an anecdote in the register of
`docs/HARNESS_TURN_COST_ANECDOTES.md`. R6 exists to replace it with measurement.

## Requirements

Each requirement is falsifiable and names the observation that motivated it.

### R1 — An invocation must not return before its agent has exited

`opencode run ... &` returned when the wrapper shell backgrounded, while the
agent and its server kept editing files. Post-state read at that moment is not
the agent's output. Twice a file whose gate had just passed was copied out and
found different, once syntactically broken mid-edit.

*Test:* launch a delegation that writes a file after a delay; assert the file is
complete and stable at the instant the invocation returns.

### R2 — Every write is validated before it is accepted

A delegated edit left `gpu.sh` syntactically invalid and reported success; the
waybar module was dead until a human noticed. `bash -n` would have caught it in
milliseconds.

The harness runs an extension-appropriate check (`bash -n`, `python -c
ast.parse`, `json.load`) on every write and rejects the write on failure,
returning the error to the agent as a turn result.

*Test:* delegate a write of a file with a deliberate syntax error; assert the
write is rejected and the agent is given the parser's message.

### R3 — Anchored replacement is a first-class primitive

Edit-shaped tasks failed 0/3 across `gemma4:26b` and `gemma4:31b` while
new-file tasks passed 6/8 across three models on the same gates. Without a
primitive that takes an anchor, a replacement, and validates both, a mid-file
change is free-form regeneration of surrounding context.

The primitive must fail closed when the anchor is absent or matches more than
once, and must not apply a partial edit.

*Test:* delegate an edit whose anchor appears twice; assert the harness refuses
rather than guessing.

### R4 — One artifact per invocation

A three-file prose task timed out producing nothing, twice. The same three files
delegated one per invocation all succeeded. Separately, having the agent read
`AGENTS.md` rather than receiving the instruction inline was the difference
between finishing and timing out on an otherwise identical single-file task.

The harness bounds an invocation to one declared output artifact and assembles
the instruction directly rather than requiring a discovery read.

*Test:* assert an invocation declaring two output artifacts is refused at
dispatch.

### R5 — The agent never reports the outcome

Both fabricated reports in the session — an audio fix that wrote no file, and
the `gpu.sh` edit — came from asking a model to describe its own work. An agent
that cannot report success cannot fabricate it.

The harness executes the postcondition itself, from the task definition, outside
the agent's workspace and permission scope, and derives pass/fail from state
rather than from prose. Per `GATED_RUNNER_SPEC.md` §4 the verdict vocabulary is
`pass` / `fail` / `vacuous` / `error`; agent narration is recorded as a claim,
never as a verdict.

*Test:* delegate a task whose agent reports success without acting; assert the
recorded verdict is `fail`.

### R6 — Every invocation emits a machine-readable outcome record

The taxonomy above was reconstructed by hand from scrollback, which is why it is
an anecdote rather than a measurement. The harness emits, per invocation: task
id, harness, model, declared artifact, wall-clock, tool-call count, exit cause,
gate verdict, and whether any author-pinned file changed hash.

*Test:* assert a completed invocation produces a record containing every field,
and that a timed-out invocation produces one with `exit_cause: timeout`.

### R7 — Git write is not a local-seat default

On 2026-08-23 `gemma4:31b` was given git on `operator-control-plane` as an
experiment and asked to clean the tree and stabilize claim state. It reported
three collapsed commits and an Active Draft. Git showed three same-timestamp
commits that did not rewrite history, an Operator paper copy set to
`FROZEN (Published)` (Phoenix 1.45 remained an active draft), “laim” in the
commit subjects, a leftover `opr` test that breaks pytest collection, and a
still-dirty tree. Record: `docs/HARNESS_TURN_COST_ANECDOTES.md` 2026-08-23.

Local implementer seats do not receive `git commit`, rebase, or history
rewrite unless the human is explicitly running a git experiment. A recap of
hygiene is narration. `git status` and `git log` are the gate. Paper
lifecycle is not the implementer's to advance.

*Test:* a local-seat invocation whose task is not a git experiment must not
be able to `git commit`. A recap that says the repo is clean must not be
recorded as the verdict.

## Non-goals

- Choosing models, or ranking them. That is `evals/local_lane_ladder/`.
- Phrasing tasks. That is `LOCAL_LANE_CONTRACT.md`.
- Executing verification anywhere except the harness. `doctor` stays structural
  and read-only.
- Eliminating supervision. R1–R7 reduce the supervisor's *reading*, which is the
  recurrent cost; they do not remove the need for a human to decide whether the
  postcondition was the right one.
- Giving local seats git by default. R7 forbids it; an experiment that grants
  it is scored against `git log`, not against the recap.

## Open questions

1. **Does R3 actually close the edit gap?** The claim that edit failures are tool
   affordance rather than capability is the spec's least supported. R3 plus R6
   makes it measurable: run the same edit tasks with and without anchored
   replacement and compare.
2. **Where does the contract stop being delegation?** Drafting prose for the cost
   paper reached a point where the instruction precise enough to gate was
   materially the text itself, and the model returned it transcribed. For code
   the gate specifies behaviour and the model supplies implementation, so the
   boundary is further out. Where it sits per artifact type is unmeasured.
3. **Is the wide denominator real?** The amortisation argument assumes harness
   fixes carry across task classes. Two classes were exercised in one session.
   R6's records over more classes would confirm or refute it.

## Relationship to existing specs

| Spec | Governs |
|---|---|
| `LOCAL_LANE_CONTRACT_SPEC.md` | task shape — what the agent is asked |
| `GATED_RUNNER_SPEC.md` | the gate — how a verdict is reached |
| **this spec** | the carrier — how the invocation is executed |
| `EXECUTOR_IDENTITY_SPEC.md` | who is permitted to record the verdict |
