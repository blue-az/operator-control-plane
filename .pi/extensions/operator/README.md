# Operator control plane - pi extension

[Pi](https://github.com/earendil-works/pi) shortcuts for a separately installed
Operator control plane. The implementation includes the original ladder steps
1–4 plus later orientation, PBC, crystal and target-registry work. This is an
alpha implementation inventory, not completed dogfood or independent acceptance.

The repository now declares a Git-first `pi-operator@0.1.0-alpha.1` package;
`private: true` prevents accidental npm publication. No release/tag has been
created by adding that manifest. See `docs/releases/pi-operator-0.1.0-alpha.1.md`
for the exact file list, prerequisites and deferred validation. The existing
copy/link installer remains an alternative, not something to install alongside
a second copy of the same extension.

## Alpha scope: core plus optional capabilities

**Core:** local doctor/status/tasks, task selection, and confirmed
claim/evidence/handoff shortcuts. These require an Operator checkout, a local
ledger, Python >=3.12 and PyYAML. Repo-specific orientation (`/op:next-steps`,
`/op:roadmap`) also reads the extension PBC appendix from the control-plane
checkout. A frontend-only package is not a replacement for that backend.

**Optional:** delegation/target editing and supervisor review (configured harnesses,
carriers and models); PBC draft/validation commands (pinned external validator);
crystal workflows (capture requires installed crystallize 0.1.16); and experimental
GUI/UID reviewer launchers (Unix verifier policy, askpass, account permissions and
provider authentication). They are registered commands, not separate plugins;
missing dependencies are handled when those commands are invoked. Do not use
optional workflows to establish basic installation readiness.

The alpha compatibility target is Pi **0.87.1**, the installed package version
observed during static release preparation, with Node **>=22.19.0** (that Pi
version's minimum). Earlier local test output recorded Node **22.22.2**; it does
not establish a tested matrix for this release. Pi peer dependencies use `*` per
Pi's packaging convention, not a claim that every Pi version is supported. Crystal
capture and supported-platform acceptance are deferred to the tagged release.
No workflow validation was run for this packaging pass.

## Commands

| Command | Wraps | Writes to the ledger? |
|---|---|---|
| `/op:doctor` | `./operator doctor` | no |
| `/op:status` | `task-show --id`, `claim-list --task`, `session-list --task`, `task-list`, `doctor` | no |
| `/op:tasks [--all] [filter]` | `./operator task-list` | no |
| `/op:next-steps [mode] [popup]` | `task-list`, `task-show`, `claim-list` ranked into a short action list | no |
| `/op:project <prefix>` | `task-list` plus per-match `task-show` / `claim-list` | no |
| HTML boards | `python3 scripts/operator_project_board.py` writes `docs/boards/` from the local ledger | no |
| `/op:roadmap [--project <prefix>]` | ladder/issues/futures, or the project dashboard when `--project` is present | no |
| `/op:use [task-id]` | selects a task for this pi session; `./operator task-use <id>` **only after you confirm** | only on confirmation |
| `/op:claim [text]` | **experimental** `./operator claim-add --task … --by <session>` (defaults: `file_exists`, gate `tests/test_operator.py`, pytest verify; `/op:claim edit` for the full form) | only on confirmation |
| `/op:evidence [path-or-url]` | **experimental** `./operator evidence-attach --task … --verify-cmd … --by <session>` (defaults: latest unverified claim, `run_log`, `./operator doctor`; `/op:evidence edit` for the full form) | only on confirmation |
| `/op:handoff` | `./operator handoff-add --task … --by <session>` from an editor draft | only on confirmation |
| `/op:supervisor-review [claim-id]` | **experimental** `./operator review-delegate` for one named claim | only on confirmation (review bundle, never verification) |
| `/op:delegate [task-id] [alias]` | **experimental** `task-create --assign` when unrouted, then `session-start` / brief, then `harness_adapter` IMPLEMENTER | only on confirmation; parent routing is never mutated |
| `/op:popup` | **experimental** GUI `sudo -A` askpass for the **latest** uid-isolated launch (`/op:popup sample` → `sudo -A true`; `/op:popup credentials` → `sudo -A -v`; `/op:popup list` to choose) | no ledger write; does not verify |
| `/pbc:validate [path]` | pinned Route C wrapper; defaults to cwd `owners-manual/pbc` | no |
| `/pbc:define [file.pbc.md]` | edit structured product-shape draft; validate, preview, confirm | document only |
| `/pbc:feature [file.pbc.md]` | edit structured feature candidate; validate, preview, confirm | document only |
| `/op:crystal` | installed `agent-crystallize@0.1.16 now` with reviewed current-session notes | artifact only |
| `/op:crystal-attach [path]` | `operator crystal-attach` with explicit task, session author, hash, strict provenance comparison | only on confirmation |
| `/op:crystal-import [path]` | `operator crystal-import`; draft claims, no open-loop tasks | only on confirmation |
| `/op:targets [list\|add\|edit <alias>\|remove <alias>]` | delegation target registry UI | config only, after confirmation |
| `/op:verify-run [review-bundle-id]` | **experimental** distinct-UID launcher; author-writable code runs with verifier permissions | helper attachment path is decision-gated; launched code is not sandboxed |

There is no `/op:install` or `/op:mode` command. Cross-project
install is `scripts/install-operator-extension.py`. Workflow strictness is
optional guidance on `/op:next-steps`, not a new gate.

Carrier-neutral integrations may import `client.ts` (`OperatorClient` or
`CarrierNeutralOperatorClient`) without importing Pi UI modules. Carriers provide
an `exec` function; argv remains fixed and allowlisted. Session lifecycle retries
report already-running/already-closed records as idempotent, while status
transitions and arbitrary usage passthrough remain out of scope.

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

## Experimental verifier run

Create a UID-isolated bundle with `/op:supervisor-review`, then use
`/op:verify-run` to choose it (or pass its exact bundle ID). The shortcut previews
claim/task, model, proposed verification command and exact GUI `sudo -A -H`
invocation. It selects the verifier's HOME and does not explicitly forward author
credentials; actual environment isolation also depends on sudo/account configuration.
There is no root, same-author-UID, single-user-policy or advisory fallback.

The separate `scripts/operator_verify_run.py` helper requires an enforced policy
and registered verifier role, binds the preview to input hashes, and reconstructs
fixed Pi argv rather than executing the stored bundle shell command. It launches
a model review; this can incur usage charges. Logs remain in the verifier's
private `~/.operator-verifier-runs/<session-id>/` directory.

Exit zero alone does not trigger this helper's attachment path. That path requires
a decision file approving the named claim before it attaches the closed log through
Operator's identity/gate checks. The slash command accepts no verdict/status inputs.

**This is not a boundary against author-controlled code.** The helper, Operator
CLI and verification command run from the author-writable checkout with the
verifier's permissions and credentials. That code can write verifier evidence
without following this helper's decision path. Input hashes check only freshness
since confirmation, not code trust. A resulting `uid_isolated` record establishes
a distinct executing UID, not independence from author code or correctness of the
review. Rejection/failure stops this helper's automatic attachment; it cannot
promise that launched code made no ledger changes.

See `docs/specs/VERIFY_RUN_SPEC.md` for the decision schema and trust boundary.
This is not an OS sandbox. Automated tests do not replace a human-authorized
live GUI/cross-UID/provider acceptance run; no privileged run is performed during
installation or testing.

### Known optional-review limitations

- A reviewer label is not a provider/model guarantee. The backend uses an explicit
  model, then a configured harness model, then persona defaults; unrecognized or
  placeholder-only labels fall back to `openai-codex/gpt-5.6-luna`. A label such as
  `claude-supervisor` alone does not select Anthropic. Inspect the bundle/model
  before authorizing. This alpha documents the fallback rather than changing it.
- The generated legacy review script's auth preflight checks only whether
  `auth.json` is readable or a mapped provider environment variable is non-empty.
  It does not establish a valid credential for the selected provider, expiry,
  refresh success or account entitlement. Do not copy the author's credentials
  to repair reviewer setup implicitly.
- The owner confirms the GUI popup worked in the reported incident. Pi then
  failed because `openai-codex` authentication was unavailable in that launch
  environment. This is an execution/setup failure, not a demonstrated popup
  failure or a completed end-to-end verifier run. External Claude review is an
  acceptable temporary workflow; it is not automatically ledger verification.

## Delegation target editor

`/op:targets` opens an action chooser; `/op:targets list` is read-only and also
works without a UI. Use `/op:targets add`, `/op:targets edit <alias>`, or
`/op:targets remove <alias>` for direct actions. Omitting an alias on edit/remove
opens a target chooser. Add/edit use field prompts, not a JSON editor.

The registry is **the control-plane ledger root's**
`.pi/extensions/operator/targets.json`, the same file `/op:delegate` reads—even
when invoked from an external consumer project. Confirmation names this shared
path and previews before/after settings plus the complete proposed registry.

New/edited targets must resolve to an existing registered harness with a model
(or provide an explicit model). Carrier, isolation and brief format use the
existing allowlists. Launch hints remain display-only; no command is executed.
Unavailable existing targets remain visible and can be repaired or removed.
Removing the last target is refused because an empty registry is invalid.

Writes require a UI and live session identity. Symlink destinations, malformed
registries, duplicate aliases, changed preview snapshots and changed harness/model
resolution fail closed. A writer lock and atomic replacement guard config saves;
a stale lock must be inspected manually, never silently stolen. No task routing,
harness registration, identity policy, ledger evidence or verifier authority is
changed. `/op:delegate` continues enforcing its author/reviewer separation.

## PBC and crystal shortcuts

`/pbc:validate` accepts one file/directory path, not arbitrary CLI flags. It reports
upstream findings and local allowlists without equating validation with ratification.
It requires the control-plane checkout's wrapper and its separately installed pinned
`pbc-spec` CLI. Set `POE_FUT014_PBC_SPEC` to your installed pinned checkout: the
legacy default `/home/blueaz/Python/Evaluation/pbc-spec` is host-specific, not a
portable install location. The extension never installs this dependency.

`/pbc:define` edits JSON fields for definition, scope, non-goals, actors and proposed
rules. `/pbc:feature` edits name, description, source links and next steps. Both
serialize a **draft `pbc:grounding` proposal**, validate a temporary candidate, then
show the exact addition before confirmation. New files get draft frontmatter;
existing files get an appended proposal, never an in-place rewrite of accepted rules.
Proposed rules remain draft product-shape text, not canonical `pbc:rules`.
Concurrent edits, invalid drafts, unsafe paths and missing validator dependencies
refuse the write. Destinations must be workspace-local `.pbc.md` files outside
runtime/config directories; no symlink destinations. These are guided authoring
flows, not upstream `pbc define`/`pbc feature` subcommands or a lifecycle wizard.

`/op:crystal` directly captures the current session after an editor review and
confirmation—no chooser. The seed contains bounded user/assistant text from the
active branch, not thinking or tool results. Review/redact it before saving. Live
session/task and available model/provider labels are supplied explicitly. Capture
writes under cwd `.agent-crystals/sessions/` and never auto-attaches evidence.

Capture uses installed `@stewie-sh/agent-crystallize@0.1.16` only: workspace
`node_modules`, a PATH binary's package, or the local npm execution cache. Override
discovery with `OPERATOR_CRYSTALLIZE_PACKAGE=/absolute/package/directory` (still
version-checked). Missing/wrong versions fail closed; no network, `npx`, setup,
hooks, or automatic upgrade. The Operator parser's older compatibility pin is not
changed; the test suite checks the installed capture output against that parser.

Attach/import take a direct path. Only omitting the path opens a chooser over
existing cwd session crystals. Both show content and exact argv before confirming;
the selected task and session-derived author are explicit. Attachment includes a
hash and strict comparison of available live model/provider labels. Import uses
the backend's fingerprint idempotency and **draft-only** claim extraction; it does
not create open-loop tasks. Crystal contents remain untrusted narration.

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
The PBC shortcuts do not perform lifecycle transitions or ratification.
POE-FUT-014 Route C remains a local wrapper (`scripts/pbc_validate_operator.py`)
around the pinned `pbc-spec` CLI, not an upstream `--profile`.

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
  `task-create`, `session-start`, `brief`, `export-brief`, `crystal-attach`,
  `crystal-import` (confirmed writes). PBC validation and capture use separate,
  fixed launchers, not arbitrary command passthrough.
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
| `workflows/commands.ts` | PBC draft/validation and crystal capture/attach/import handlers |
| `workflows/targets.ts` | target registry chooser, validated config edits and atomic saves |
| `workflows/verify.ts` | confirmed distinct-UID verifier launcher; no author-side verdict inputs |
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
node --experimental-strip-types tests/pi_operator_workflows.ts
node --experimental-strip-types tests/pi_operator_targets.ts
node --experimental-strip-types tests/pi_operator_verify.ts
python3 -m pytest tests/test_pi_operator_extension.py tests/test_operator_verify_run.py -q
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

Historical Pi 0.85 loader tests encountered a package-root import of optional
`@earendil-works/pi-server`. The selftest includes an isolated temp import fixture
via `node:module.registerHooks` for that case, not a mock loader. If hooks are
unavailable and the optional package is missing, B/C skip instead of false-passing.
This historical workaround is not a validation result for the alpha's Pi 0.87.1
target.

No LLM call and no network access anywhere in it.

## Current limitations

- PBC authoring appends draft proposals; it does not rewrite/ratify existing rules.
- Stock `pbc validate` still rejects Operator `proposed-*` (E004); `/pbc:validate`
  labels these as local Route C allowances, not upstream support.
- Capture needs the checked installed CLI version; capture/validator smoke checks
  explicitly skip when their optional dependencies are absent.
- Pi project trust is still required for a consumer `.pi/extensions` tree.
- Historical loader selftests use Node `registerHooks` (22.15+) for an optional
  server import fixture. Do not infer release compatibility or install old local
  Pi server checkouts from those historical test notes.
- Stale `next_action` detection is conservative string/record matching.
- `findLedger` wiring is contract resolution, not a live trusted-consumer Pi
  session against an external ledger.
