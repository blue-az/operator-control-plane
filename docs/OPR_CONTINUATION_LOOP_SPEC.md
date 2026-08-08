# opr Continuation Loop — Implementation Spec

**Status:** proposed, not implemented
**Date:** 2026-08-07
**PBC:** `owners-manual/pbc/appendix-opr-governed-llm-client.pbc.md` (OPR-RUL-010..013, OPR-BHV-005)
**Target:** `opr` `run_agent_loop`, currently lines ~818–884

## 1. Problem

`opr:831` declares:

```python
terminal_tools = {"write_file", "patch_file", "run_command"}
```

and `opr:874` returns as soon as one of those succeeds:

```python
if tool_name in terminal_tools:
    if success:
        return f"[Tool completed: {tool_name}]\n{tool_output}"
```

Consequence: **a dispatch requiring N sequential shell commands completes at
most its first.** Only read-only tools (`list_dir`, `read_file`,
`grep_search`) append to `accumulated_context` and reach `turn += 1`.

This is not a bug in isolation — it is a deliberate safety property. Exiting
after one state change bounds unsupervised chaining of destructive actions.
The defect is that it has no alternative, so multi-step CLI work is
structurally impossible rather than merely gated.

### 1.1 Observed misdiagnosis

On 2026-08-07 a three-step git task (`git add` / `git commit` / verify with
`git status`) was dispatched to `gemma4:31b`. It completed step 1 only. The
transcript showed `[Tool completed: run_command]` and 35 generated tokens,
and this was recorded — in `blind-judge-no-self-favoritism.md` §6 — as the
model truncating or stalling on multi-step work.

That conclusion was wrong. 35 tokens is exactly one well-formed tool call,
which is all the harness ever solicits on this path. The model was never
re-prompted. The paper section has been corrected.

**This matters beyond one task:** any local-model agentic capability
measurement taken through `opr` before this lands is measuring the harness.
Two separate artifacts currently rest on that confusion and are flagged in
the PBC's Open Risks.

## 2. Design constraints

The amendment must not weaken what OPR-RUL-008 was protecting.

| Must preserve | Why |
|---|---|
| Per-call confirmation on every state-changing tool | The only thing standing between a model and an unreviewed `rm -rf` |
| A hard ceiling on state-changing calls per dispatch | Bounds blast radius if the model loops productively but wrongly |
| Existing 10-turn cap | Independent backstop |
| Fingerprint halt (OPR-RUL-009) | Prevents re-running an identical destructive call |
| Default-off | Existing callers must not silently gain chaining |

## 3. Proposed change

### 3.1 Signature

```python
def run_agent_loop(
    ...,
    continue_after_state_change: bool = False,   # OPR-RUL-011 opt-in
    max_state_changes: int = 5,                  # OPR-RUL-011 budget
) -> AgentResult:
```

CLI surface: `--continue-steps N` (0 = current behavior, the default).

### 3.2 Loop change

Replace the unconditional terminal return with:

```python
state_changes = 0
...
if tool_name in terminal_tools:
    if not success:
        return AgentResult(status="failed", ...)          # unchanged: failure still exits
    state_changes += 1
    if not continue_after_state_change:
        return AgentResult(status="completed_single", ...)  # unchanged default
    if state_changes >= max_state_changes:
        return AgentResult(status="halted_budget",
                           steps_run=state_changes, ...)     # OPR-RUL-011
    accumulated_context += f"\n--- Tool Output: {tool_name} ---\n{tool_output}\n"
    turn += 1
    continue                                                 # OPR-BHV-005
```

Failure still exits immediately — a failed state change is exactly when a
human should look.

### 3.3 Explicit completion signal (OPR-RUL-012)

The loop must not treat "model emitted no tool call" as success, because that
is also what a confused model does. Require an affirmative signal. Extend the
tool vocabulary with a no-op terminator:

```json
{"tool": "task_complete", "summary": "<what was done>"}
```

Prompt scaffolding, appended only when `continue_after_state_change` is on:

> You may issue multiple tool calls in sequence. After each one you will see
> its output and may issue the next. When the task is fully done, respond with
> `{"tool": "task_complete", "summary": "..."}`. Do not emit `task_complete`
> until every requested step has actually run.

### 3.4 Return type (OPR-RUL-013)

Replace the bare string with a structured result so callers can distinguish
outcomes that currently all look like success:

| status | meaning |
|---|---|
| `completed` | `task_complete` received |
| `completed_single` | legacy path: one state change, loop exited (default mode) |
| `partial` | loop ended with no completion signal |
| `halted_budget` | hit `max_state_changes` |
| `halted_repeat` | fingerprint halt (OPR-RUL-009) |
| `failed` | a state-changing call failed |

Carry `steps_run`, `tools_called[]`, and `completion_signal: bool`. Preserve
the current string form in a `.text` field so existing call sites keep working.

## 4. Ledger integration

`partial`, `halted_budget`, and `halted_repeat` are the machine-readable
signal that supervisor substitution is about to happen. Record `status` and
`steps_run` on the session so substitution rate becomes queryable — this is
the completion axis the supervisor review of `claim-0001`
(`agentic-cli-tps-metrics`, handoff-0002) required before any throughput
metric can be trusted. A TPS number computed over dispatches that silently
returned after step 1 is measuring the wrong thing.

## 5. Test plan

Unit (`tests/test_opr.py`):

1. Default path unchanged — one `run_command`, loop exits, `completed_single`.
2. `--continue-steps 3`, model emits three `run_command`s then
   `task_complete` → `completed`, `steps_run == 3`.
3. Budget — `--continue-steps 2`, model wants three → `halted_budget`,
   third never executes.
4. Confirmation still fires on calls 2..N (assert prompt count == state changes).
5. Failed second call → `failed`, loop stops.
6. No completion signal before turn cap → `partial`.
7. Repeated identical call under continuation → `halted_repeat`.

Integration — re-run the exact 2026-08-07 git task against
`gemma4:26b` and `gemma4:31b` with `--continue-steps 3`. This is the
regression case and also the first honest measurement of local-model
multi-step behavior on this harness.

## 5.5 Confirmation waiver ("dangerous mode")

Per-call confirmation (OPR-RUL-010) makes genuine delegation impossible — a
loop that stops for `[y/N]` on every step is not fire-and-forget. A waiver is
required, equivalent to Claude Code's bypass-permissions mode.

### 5.5.1 Existing precedent

`opr` already has one, deliberately constrained. `confirm_model_action`
(`opr:470-480`) is the single choke point for the gate, and
`--eval-auto-confirm` auto-answers `y` — but `main()` refuses to set the flag
unless `--workspace` resolves under `tempfile.gettempdir()`, so it "can only
silently auto-confirm inside a disposable eval fixture, never a real
workspace."

So the question is not whether to build a waiver; it is whether to relax that
tempdir guard or add a sibling flag that trades the guard for something else.
**Recommendation: sibling flag.** Keep `--eval-auto-confirm` exactly as it is
— it is load-bearing for the eval ladder and its guarantee is worth keeping
absolute.

### 5.5.2 Tiers

| Tier | Flag | Gate behavior | Intended use |
|---|---|---|---|
| 0 | *(default)* | confirm every state change | interactive |
| 1 | `--yes-to <prefixes>` | auto-confirm matching commands, prompt otherwise | routine delegation |
| 2 | `--dangerous` | auto-confirm everything | delegation inside isolation |
| — | `--eval-auto-confirm` | auto-confirm, tempdir-locked | unchanged, eval ladder only |

**Tier 1 is likely the one worth using day to day.** Most observed dispatches
are git operations, and confirmation is not really about "is this command
safe" — it is about **"is this recoverable."** `git add`, `git commit`,
`git status` are recoverable via reflog. `rm -rf`, `git push --force`,
`systemctl restart`, and anything touching `~/.ssh` are not. An allowlist
keyed on recoverability gets most of the delegation benefit at a fraction of
the exposure, and unlike full bypass it degrades safely — an unmatched
command prompts rather than runs.

### 5.5.3 Pair Tier 2 with the isolation that already exists

This repo already has a stronger primitive than confirmation:
`.operator-run/run-external-agent` executes as `operator-builder` (uid 971)
and asserts at startup that it *cannot read* `~/.ssh/id_ed25519`,
`~/.ssh/ionos_deploy`, `~/Downloads/SensorDownload`,
`project-phoenix/.operator`, or `~/.operator-usage` — failing closed if any
are readable.

`--dangerous` as `blueaz` and `--dangerous` under uid 971 are different
propositions. The first waives review over a process that can read every
secret on the box; the second waives review over a process that provably
cannot. The P0/P2/P3 airlock work already built the safer one.

**Recommendation:** `--dangerous` prints which identity it is running as and
whether the deny-read set holds. Do not hard-block it outside isolation —
it is the operator's machine — but make the distinction visible at the moment
of use rather than in a doc.

### 5.5.4 Constraints on the waiver

1. **Per-invocation only, never from config.** A waiver that can be set in
   `~/.config/operator/opr.yaml` will eventually be left on and forgotten.
   Command-line flag only; reject it if it appears in a config file.
2. **Does not widen the workspace boundary.** OPR-RUL-003 still applies —
   waiving *review* must not also waive *bounding*. Do not stack waivers.
3. **Does not waive the step budget.** `max_state_changes` still caps the
   loop; the waiver removes the prompt, not the ceiling.
4. **Recorded in the ledger, and it taints provenance.** This is the
   constraint specific to this system: `operator` exists to make claims
   auditable. Work produced under an unreviewed loop has different trust than
   work a human approved step by step. The session record must carry
   `confirmation_mode: interactive | allowlist | bypassed`, and evidence
   attached from a bypassed session should surface that at verification time.
   Without this, `--dangerous` silently launders unreviewed output into the
   claims ledger.

Constraint 4 is the one that does not exist in other tools' YOLO modes and
is non-optional here.

## 6. Open questions for the supervisor

1. **Default budget.** 5 proposed. Lower is safer, higher is more useful.
2. **Should `write_file` continue by default but `run_command` not?** Writes
   are workspace-bounded (OPR-RUL-003); shell is not. A split default is
   defensible and slightly more complex.
3. ~~**Does `task_complete` need verification?**~~ **Resolved by measurement,
   and the failure mode is the opposite of the one anticipated.** The concern
   was a model emitting `task_complete` while lying. Measured on
   `gemma4:26b`, n=5, the three-step git task: the commit landed and the tree
   was clean in **5/5** trials, but `task_complete` was emitted in only
   **1/5**. The model reliably *does* the work and unreliably *announces* it.

   So requiring an explicit signal (OPR-RUL-012) produces **false negatives**
   at a 4-in-5 rate here — it reports failure on work that succeeded. Trusting
   "no more tool calls" instead would produce false positives on a confused
   model. Neither bare option is sound.

   **Recommendation: caller-supplied success predicate**, with the explicit
   signal demoted to a hint. This is exactly the `phoenix-gate-verify`
   pattern — deterministic post-condition check rather than agent
   self-report — and `trust-the-validator.md` already argues the general case.
   OPR-RUL-012 should be amended accordingly before implementation hardens
   around the signal.
4. ~~**Auto-confirm for continuation?**~~ **Resolved** — the operator has
   called for a waiver. See §5.5. Remaining sub-question: adopt Tier 1
   (`--yes-to` recoverability allowlist) as the everyday default and reserve
   Tier 2 (`--dangerous`) for isolated runs, or ship Tier 2 alone and skip
   the allowlist? Tier 1 is more code but degrades safely; Tier 2 alone is
   simpler and matches the Claude Code model the operator already works in.
5. **Does `confirmation_mode: bypassed` block verification, or just annotate
   it?** OPR-RUL-016 requires the mode be recorded and surfaced. Whether a
   bypassed session's evidence can still reach `verified` status, or is
   capped at `advisory`, is a trust-model decision that belongs to the
   supervisor, not this spec. Note `doctor` currently reports
   `verification_authority: advisory` on this host anyway.

## 7. Effort and sequencing

| Item | Size | Risk |
|---|---|---|
| Loop change + budget (3.2) | small | low — additive, default-off |
| `task_complete` + prompt scaffold (3.3) | small | low |
| Structured return (3.4) | medium | medium — touches call sites |
| Ledger fields (§4) | small | low |
| Tests (§5) | medium | low |

Recommended split: land 3.2 + 3.3 + tests first behind the flag; do 3.4 and
§4 as a second change, since the return-type refactor is the only part that
touches existing callers.
