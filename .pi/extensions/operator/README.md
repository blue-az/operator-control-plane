# Operator control plane - pi extension

Project-local [pi](https://github.com/earendil-works/pi) extension that puts the
common Operator moves behind slash commands, so working in this repo does not
depend on remembering flags.

This is **step 4** of the ladder in
`owners-manual/pbc/appendix-pi-operator-extension.pbc.md`: orientation, claim,
evidence, and handoff writes, claim-scoped supervisor-review, and chooser-first
`/op:delegate`. Read-only `/op:next-steps` / `/op:project` and a cross-project
install helper are also present. There is still no `/pbc:*` Pi command. Operator
PBC checking is a **local wrapper** (`scripts/pbc_validate_operator.py`, Route C);
the pinned upstream CLI has no `--profile` flag.

## Commands

| Command | Wraps | Writes to the ledger? |
|---|---|---|
| `/op:doctor` | `./operator doctor` | no |
| `/op:status` | `task-show --id`, `claim-list --task`, `session-list --task`, `task-list`, `doctor` | no |
| `/op:tasks [--all] [filter]` | `./operator task-list` | no |
| `/op:next-steps [mode] [popup]` | `task-list`, `task-show`, `claim-list` ranked into a short action list | no |
| `/op:project <prefix>` | `task-list` plus per-match `task-show` / `claim-list` | no |
| `/op:roadmap [--project <prefix>]` | ladder/issues/futures, or the project dashboard when `--project` is present | no |
| `/op:use [task-id]` | selects a task for this pi session; `./operator task-use <id>` **only after you confirm** | only on confirmation |
| `/op:claim [text]` | `./operator claim-add --task … --by <session>` | only on confirmation |
| `/op:evidence [path-or-url]` | `./operator evidence-attach --task … --verify-cmd … --by <session>` | only on confirmation |
| `/op:handoff` | `./operator handoff-add --task … --by <session>` from an editor draft | only on confirmation |
| `/op:supervisor-review [claim-id]` | `./operator review-delegate` for one named claim | only on confirmation (review bundle, never verification) |
| `/op:delegate [task-id] [alias]` | `task-create --assign` when unrouted, then `session-start` / brief, then `harness_adapter` IMPLEMENTER | only on confirmation; parent routing is never mutated |

There is no `/op:install`, `/op:mode`, or `/pbc:*` command. Cross-project
install is `scripts/install-operator-extension.py`. Workflow strictness is
optional guidance on `/op:next-steps`, not a new gate.

Each command appends a report to the transcript. It renders collapsed by
default; `ctrl+o` expands it to the full detail and the exact `./operator ...`
invocations behind it.

### Agent-visible output

Pi's `appendEntry` custom entries are TUI-only and **do not** enter LLM
context. Orientation commands (`/op:next-steps`, `/op:project`, and
`/op:roadmap --project`) also call `pi.sendMessage` with
`deliverAs: "nextTurn"` so the same action text is queued for the next
prompt without triggering a turn (`display: false` so the TUI renderer is
not doubled). A green `/op:doctor` panel is still terminal output, not
evidence (POE-RUL-105).

### `/op:next-steps` and workflow guidance

Priority is deterministic: empty ledger, then no active task, then current
ledger `next_action`, unverified claims, missing evidence/`review_harness`
gates and quarantined claims, recent dogfood issues (PBC id order, last 3),
then future slices (PBC id order). Stale `next_action` is warned, not
followed blindly. Verification kinds stay distinct: user acceptance,
advisory/same-UID review, and UID-isolated verification.

Optional tokens (combinable with `popup`): `support` / `deliverable`,
`engineering-light` / `light`, `engineering-trust` / `trust`. Guidance only.
Support may close a *deliverable* on user acceptance; it cannot mark a claim
verified or weaken enforced UID policy.

### `/op:project`

Prefix required. Matches lexicographic `task-id` prefixes. Grouping is
labeled “not a project phase order”. Flag-shaped or extra tokens fail closed.
Zero matches are explicit; the prefix is not inferred from the active task.

`/op:use` with no argument opens a chooser over the tasks in the ledger. With an
argument it takes the task id and offers completions from
`.operator/tasks/*.yaml`.

`/op:claim` and `/op:evidence` are guided prompts ending in a confirmation that
shows the exact argv. `/op:handoff` opens an editor with the six closeout
sections; continuity transfer is the mode where a successor is named under
"Next action", not a separate command.

`/op:supervisor-review` is chooser-first over one named claim. The review
target is a model/persona label such as `grok`, `luna`, or `claude`; `pi` is
only the carrier/runtime. The task's `review_harness` may suggest a default
review target, but trusted authority is still a separate Unix verifier identity
such as `operator-verifier`. Trusted UID runs write a `sudo -u` script for
**you** to authorize; this session does not run it and does not silently fall
back to advisory. Broker-enrolled ledgers fail closed as unavailable.

`/op:delegate` is chooser-first over configured model/persona targets in
`targets.json`. Each target shows ledger harness id, carrier/adapter id,
model, isolation, and brief format as separate axes. `pi` itself is not a
normal delegation target because it is the runtime that launches many models.
If the target is already this task's `assigned_harness` and is not also `review_harness`, it
session-starts a builder brief on the parent. If the target is not an
implementer on the parent, you confirm a scoped child task with explicit
`--assign` instead of mutating parent routing. A target that would be both
implementer and reviewer is refused. The primary path invokes
`harness_adapter` in IMPLEMENTER role with the written brief; paste/export is
a labeled fallback.

## Cross-project install and external ledger

Pi loads project-local extensions from **cwd** `.pi/extensions/*/index.ts`
only, after project trust. It does not walk parent directories. A consumer
repo therefore needs its own copy or symlink of this extension.

The helper `scripts/install-operator-extension.py` copies or links the
runtime files and writes `.pi/operator-ledger.json` (schema
`operator-pi-extension-ledger-contract/v1`) with an **absolute**
`ledger_root`. `core.ts` `findLedger` reads that contract. It never copies
`.operator/` runtime data. See `install-guide.md` for the contract fields,
fail-closed discovery rules, uninstall ownership, and the package-test
gate that is a pre-publish checklist rather than an install side effect.

`findLedger` walks up once and collects at most the first sibling pair
(`.operator/` plus a file named `operator`) and the first contract file.
Malformed JSON, a relative `ledger_root`, `..` path segments, a missing
pair, or disagreeing canonical roots fail closed. Env vars and
`settings.json` are not silent overrides.

The helper refuses source-tree symlinks, `..` in owned paths, and
directory-to-symlink overwrite that would rmtree extra files. Copy
overwrite overlays owned files and leaves extra user files in place.
Uninstall requires this helper's ownership record and unlinks owned files
one by one (symlink dest is unlinked, not followed).

Pi project trust is still a human/Pi step. The helper does not write
`trust.json`, does not run `pi install`, and does not publish.

## What it will not do

Step 4 deliberately stops short of the rest of the candidate command set.
The `/pbc:*` commands are **not** implemented here. POE-FUT-014 Route C is a
local wrapper (`scripts/pbc_validate_operator.py`) around the pinned
`pbc-spec` CLI. That is not an upstream `--profile`, not `/pbc:validate`,
and not ratification of `proposed-*` rules.

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
| `orientation/actions.ts` | pure ranking/formatting for `/op:next-steps` and `/op:project` |
| `render.ts` | TUI rendering of a report; the only file needing `@earendil-works/pi-tui` |
| `targets.json` | chooser aliases for `/op:delegate` (harness id + carrier id + optional model/isolation/brief format) |
| `install-guide.md` | external ledger contract, install/uninstall, package-test gate |
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
- **A5** - `/op:next-steps` / `/op:project` ranking and `sendMessage`
  nextTurn payload against throwaway state.
- **A-contract** - `findLedger` contract-only, nested walk-up, malformed /
  missing-pair / ambiguous / `..` / env-ignored cases.
- **B** - `index.ts` loaded through pi's own `discoverAndLoadExtensions`: no
  load errors, the implemented `/op:*` commands, no tools, renderer registered.
- **C** - the registered handlers driven end to end with a stub UI, including
  the load-bearing cases: declining `/op:use`, `/op:claim`, `/op:evidence`,
  `/op:handoff`, `/op:supervisor-review`, or `/op:delegate` must leave the
  ledger untouched.

Installed Pi 0.85's loader statically imports the package root, which pulls
optional `@earendil-works/pi-server` (not a declared dependency). Selftest
installs an isolated temp module via `node:module.registerHooks` so the
**real** loader can import. That is not a mock of the loader. If hooks are
unavailable and the optional package is missing, B/C skip instead of
false-passing.

No LLM call and no network access anywhere in it.

## Current limitations

- `/pbc:*` commands are not implemented.
- POE-FUT-014 compatibility route is not chosen; stock `pbc validate` still
  fail-closes on Operator `proposed-*` (E004). That is expected, not a pass.
- Pi project trust is still required for a consumer `.pi/extensions` tree.
- Tiers B/C need Node `registerHooks` (22.15+) or a real
  `@earendil-works/pi-server` install matching Pi 0.85. The local pi-mono
  `packages/server` tree is unbuilt 0.84.3 and is not a compatible substitute.
- Stale `next_action` detection is conservative string/record matching.
- `findLedger` wiring is contract resolution, not a live trusted-consumer Pi
  session against an external ledger.
