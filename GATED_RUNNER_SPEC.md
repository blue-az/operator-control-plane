# Gated Runner — enforcing postcondition gate for delegated agent work

**Status:** P0, in build (`gated-runner-p0`)
**Date:** 2026-08-20

## 1. Problem

The historical `opr` client recorded that a session happened and what it cost
(`opr:408-436` called `task-create`, `session-start`, `session-end`). It never
called `claim-add` or `evidence-attach`. `opr` is now deprecated; OpenCode is
the local implementer. An agent's *assertion* is still not captured unless the
wrapper writes it, and `--verify-cmd` is recorded but deliberately never
executed — `doctor` is read-only and must stay that way.

Consequence: a delegated run can narrate success it did not achieve, and
nothing in the system contradicts it without a human or a frontier model
reading the prose. On 2026-08-20 a local run reported creating a wireplumber
rule that was never written; catching that cost frontier tokens.

## 2. Position

The runner **enforces**. It executes an author-pinned, read-only state query
before and after the agent runs, and decides pass/fail by comparison.

This mirrors what the frontier harnesses already do — Claude Code hooks are
commands the *harness* runs from `settings.json`, which the model cannot skip
or rewrite; Codex's `workspace-write` sandbox constrains rather than annotates.
It also mirrors this repo's own precedent: `delegate-brief`'s `--freeze` paths
are hashed before and after, and drift fails the run.

## 3. Boundaries

| Rule | Why |
|---|---|
| `doctor` stays read-only and never executes a gate | It is the auditor; auditors do not execute |
| Gate command comes from the cell file, never from agent output | A gate the agent can author is not a gate |
| Gate command must be a read-only state query, not a repair | A gate that fixes things cannot detect whether the agent fixed them |
| Gate runs outside the agent's workspace and permission scope | The agent must not reach its own judge |
| `evaluate()` never receives the agent transcript | Structural guarantee that prose cannot influence the verdict |
| Ledger writes are made by the wrapper, not the agent | An agent that writes its own claim can narrate into the ledger |

## 4. Verdicts

| Verdict | Condition |
|---|---|
| `pass` | pre-state did NOT satisfy the gate, post-state does |
| `fail` | post-state does not satisfy the gate |
| `vacuous` | pre-state already satisfied the gate — the cell proves nothing |
| `error` | the gate command itself failed to run (non-zero rc, missing binary) |

`vacuous` is a distinct verdict on purpose. A cell whose postcondition was
already true before the agent started awards credit for nothing, and silently
scoring it `pass` would inflate every ranking built on this runner.
