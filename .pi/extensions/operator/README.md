# Operator control plane - pi extension

Project-local [pi](https://github.com/earendil-works/pi) extension that puts the
common Operator moves behind slash commands, so working in this repo does not
depend on remembering flags.

This is **step 4** of the ladder in
`owners-manual/pbc/appendix-pi-operator-extension.pbc.md`: orientation, claim,
evidence, and handoff writes, claim-scoped supervisor-review, and chooser-first
`/op:delegate`. PBC commands are still out of scope.

## Commands

| Command | Wraps | Writes to the ledger? |
|---|---|---|
| `/op:doctor` | `./operator doctor` | no |
| `/op:status` | `task-show --id`, `claim-list --task`, `session-list --task`, `task-list`, `doctor` | no |
| `/op:tasks [--all] [filter]` | `./operator task-list` | no |
| `/op:use [task-id]` | selects a task for this pi session; `./operator task-use <id>` **only after you confirm** | only on confirmation |
| `/op:claim [text]` | `./operator claim-add --task … --by <session>` | only on confirmation |
| `/op:evidence [path-or-url]` | `./operator evidence-attach --task … --verify-cmd … --by <session>` | only on confirmation |
| `/op:handoff` | `./operator handoff-add --task … --by <session>` from an editor draft | only on confirmation |
| `/op:supervisor-review [claim-id]` | `./operator review-delegate` for one named claim | only on confirmation (review bundle, never verification) |
| `/op:delegate [task-id] [alias]` | `task-create --assign` when unrouted, then `session-start` / brief, then `harness_adapter` IMPLEMENTER | only on confirmation; parent routing is never mutated |

Each command appends a report to the transcript. It renders collapsed by
default; `ctrl+o` expands it to the full detail and the exact `./operator ...`
invocations behind it.

`/op:use` with no argument opens a chooser over the tasks in the ledger. With an
argument it takes the task id and offers completions from
`.operator/tasks/*.yaml`.

`/op:claim` and `/op:evidence` are guided prompts ending in a confirmation that
shows the exact argv. `/op:handoff` opens an editor with the six closeout
sections; continuity transfer is the mode where a successor is named under
"Next action", not a separate command.

`/op:supervisor-review` is chooser-first over one named claim. The reviewer
harness and the review path (trusted uid-isolated vs same-UID advisory notes)
are explicit; neither is taken from the session or from `review_harness`. A
verify command must already be on the claim or be supplied. Trusted UID runs
ask for a Unix user and write a `sudo -u` script for **you** to authorize;
this session does not run it and does not silently fall back to advisory.
Broker-enrolled ledgers fail closed as unavailable.

`/op:delegate` is chooser-first over configured targets in
`targets.json`. Each target shows ledger harness id, carrier/adapter id,
model, isolation, and brief format as separate axes. If the target is already
this task's `assigned_harness` and is not also `review_harness`, it
session-starts a builder brief on the parent. If the target is not an
implementer on the parent, you confirm a scoped child task with explicit
`--assign` instead of mutating parent routing. A target that would be both
implementer and reviewer is refused. The primary path invokes
`harness_adapter` in IMPLEMENTER role with the written brief; paste/export is
a labeled fallback.

## What it will not do

Step 4 deliberately stops short of the rest of the candidate command set.
The `/pbc:*` commands are **not** implemented here.

There are also no model-callable tools. These commands are human ergonomics
(POE-RUL-103); the model still has `bash` and runs `./operator` under its own
rules, with no shortcut through this extension for authoring claims about its
own work or marking them verified.

`/op:evidence` will not accept or set `--status`, `--verified-by`, or
`--verdict`. Attaching evidence never verifies a claim.

`/op:supervisor-review` writes a bundle under `.operator/review_delegations/`
and nothing else. It does not verify, does not attach evidence, and does not
offer a verifier-only draft attach path (a verifier-only identity cannot
attach no-status evidence). Same-UID advisory notes and verifier-owned
status-setting evidence are different kinds of record.

## Authority boundaries

The point of this extension is to be convenient without becoming a second
authority. Concretely:

- **Fixed allowlist, no passthrough.** Every argv is built by `core.ts` from a
  named builder. The allowlist is `doctor`, `task-list`, `task-show`,
  `claim-list`, `claim-show`, `session-list` (read-only) plus `task-use`,
  `claim-add`, `evidence-attach`, `handoff-add`, `review-delegate`,
  `task-create`, `session-start`, `brief`, `export-brief` (confirmed writes).
  Adapter invoke is a second fixed launcher (`python3 -c` of
  `harness_adapter.invoke` in IMPLEMENTER role); it is not a shell string.
  There is no raw `operator <anything>` surface (POE-RUL-104), and `pi.exec`
  spawns without a shell.
- **No lifecycle flags.** `--status`, `--verified-by`, and `--verdict` are
  rejected by `assertSafeArgv`, not validated. Verdict authority is not an
  extension input (POE-RUL-113). Nothing here can mark a claim verified.
- **`--task` is always explicit.** Every task-scoped invocation names its task
  (POE-RUL-112). The extension reads `current_task` only to *display* it, and
  the authoring writes use the session selection (or the ledger value as a
  visible fallback) rather than omitting `--task`.
- **`--by` is provenance only.** Claim, evidence, and handoff writes derive
  `--by` from the pi session id (`pi-<short session>`). That label is not a
  harness id and is never offered as `--verified-by` (POE-RUL-102, POE-RUL-003).
  A write whose session id cannot be derived is refused rather than recorded
  unattributed.
- **The session selection is not ledger state.** `/op:use` sets a selection
  scoped to the pi session. `/op:status` always prints the session selection and
  the ledger's `current_task` side by side, and says which one it is showing.
  Changing Operator's `current_task` takes a confirmation dialog; declining
  leaves the ledger untouched (POE-RUL-101).
- **Output is not evidence.** A green `/op:doctor` is terminal output. It
  becomes evidence only through an explicit `/op:evidence` (or a hand-run
  `evidence-attach`) that records the artifact (POE-RUL-105).
- **Evidence carries a rerunnable `--verify-cmd`.** `/op:evidence` refuses to
  attach without one. The command is stored, not executed, and does not change
  verification status.
- Task ids are validated against `[A-Za-z0-9][A-Za-z0-9._-]*` and must have a
  record on disk, so a typo or a flag-shaped argument fails closed instead of
  reaching argparse. Free-text fields are passed as `--flag=value` so a claim
  of `--status=verified` stays claim text.

## Layout

| File | Role |
|---|---|
| `index.ts` | the extension pi loads: command registration and wiring |
| `core.ts` | ledger discovery, argv allowlist and builders, output parsers - imports nothing from pi |
| `render.ts` | TUI rendering of a report; the only file needing `@earendil-works/pi-tui` |
| `targets.json` | chooser aliases for `/op:delegate` (harness id + carrier id + optional model/isolation/brief format) |
| `selftest.ts` | the verification path (see below) |

pi auto-discovers `.pi/extensions/*/index.ts`, so only `index.ts` loads as an
extension; the rest are its imports. Project-local extensions load only after
you trust this project in pi.

## Verifying it

```bash
node --experimental-strip-types .pi/extensions/operator/selftest.ts
python3 -m pytest tests/test_pi_operator_extension.py -q      # same thing, in the repo suite
```

The selftest runs in three tiers and skips rather than false-passes when a
dependency is missing:

- **A** - `core.ts` against a throwaway ledger built by the real `./operator`,
  which pins the argv builders and the output parsers to actual CLI output.
- **A2** - the step 2 claim/evidence/handoff builders against that same ledger,
  including that attaching evidence does not verify the claim.
- **A3** - the step 3 `review-delegate` builder against that same ledger,
  including broker-enrollment classification, required reviewer/verify-cmd,
  uid-isolated human-auth `--review-user`, and that the bundle does not
  verify the claim.
- **A4** - the step 4 delegate builders against that same ledger, including
  parent-routed vs child-task classification, dual-role refusal, and that a
  child `--assign` does not mutate the parent task's routing.
- **B** - `index.ts` loaded through pi's own extension loader: no load errors,
  exactly the nine `/op:*` commands, no tools, renderer registered.
- **C** - the registered handlers driven end to end with a stub UI, including
  the load-bearing cases: declining `/op:use`, `/op:claim`, `/op:evidence`,
  `/op:handoff`, `/op:supervisor-review`, or `/op:delegate` must leave the
  ledger untouched.

No LLM call and no network access anywhere in it.
