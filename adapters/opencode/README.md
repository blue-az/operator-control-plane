# Operator core adapter for OpenCode

Experimental, source-checkout-only **TUI plugin**, targeting OpenCode **1.18.22**.
This is the OpenCode core slice of POE-FUT-005, not full Pi feature parity.
The Pi `v0.1.0-alpha.1` release and its package allowlist are unchanged.

## Install locally

Prerequisites:

- OpenCode with `@opencode-ai/plugin/tui`, native dialog components, and
  `api.keymap.registerLayer` (target: 1.18.22; older server-only plugin APIs
  are not supported).
- This complete Operator source checkout **containing `adapters/opencode/`**.
  The existing Pi alpha tag/package does not contain this adapter. Do not copy
  just `index.ts`: it imports `controller.ts`, `runner.ts`, and the existing
  carrier-neutral `client.ts` / `core.ts` under `.pi/extensions/operator/`.
- An initialized Operator backend: Python 3.12+, PyYAML, and a checkout
  containing both `operator` and `.operator/`.

Add the following plugin entry to your consumer project's **`.opencode/tui.json`**
(merge it into existing config; do not overwrite other plugins/settings):

```json
{
  "$schema": "https://opencode.ai/tui.json",
  "plugin": ["/absolute/path/to/operator-control-plane/adapters/opencode/index.ts"]
}
```

This is a **TUI** plugin, not a server plugin. Do not put it in `opencode.json`'s
server `plugin` list or auto-discovered `.opencode/plugins/`. No npm publishing,
configuration changes, or installation into your live environment are performed
by this repository's tests.

### Select the ledger

When OpenCode's project directory is in or below the intended backend checkout,
the adapter discovers the `operator` + `.operator/` sibling pair.

For another project, create **`.pi/operator-ledger.json`** in that project:

```json
{
  "schema": "operator-pi-extension-ledger-contract/v1",
  "ledger_root": "/absolute/path/to/operator-control-plane"
}
```

The `.pi` name is intentional: this first adapter reuses the existing
cross-project discovery contract, not a second competing ledger configuration.
No Pi installation is required. A malformed contract or conflicting discovered
ledger fails closed. The adapter does not initialize or copy a ledger.

**Local TUI use only.** The plugin reads the local filesystem and executes the
local Operator CLI, using OpenCode's project directory for discovery. Remote
`opencode attach`/workspace setups are not supported or validated; do not use
this adapter to operate a remote ledger. Paths and confirmation execution refer
to the machine running the TUI, not automatically to its server.

Restart OpenCode, open the command palette, and search for **Operator**.
Start with `/op` and `/op:tasks` against a disposable ledger before authoring.
Commands collect arguments through dialogs; inline slash-command arguments are
not supported. Core authoring never sends a model prompt.

## Commands

| Command | Behavior |
| --- | --- |
| `/op` | Read-only Operator doctor output |
| `/op:tasks` | List all tasks |
| `/op:task` | Inspect a named task |
| `/op:claims` | Inspect claims for a named task |
| `/op:sessions` | Inspect ledger usage sessions for a named task |
| `/op:use` | Confirm changing the ledger's shared current-task pointer |
| `/op:brief` | Confirm generating a brief and recording issuance |
| `/op:export-brief` | Confirm generating an export brief and recording issuance |
| `/op:session-start` | Confirm starting ledger usage for an explicitly chosen registered harness |
| `/op:session-end` | Confirm closing an explicit usage ID with outcome and cost |
| `/op:claim` | Confirm recording an unverified claim |
| `/op:evidence` | Confirm attaching draft evidence, with a required re-runnable verification command |
| `/op:handoff` | Collect six optional structured sections and confirm recording continuity |

Every task-scoped command asks for an explicit task ID. The current task is only
an editable suggestion; `/op:use` also remembers a suggestion separately per
OpenCode session and ledger. It still changes the **shared** ledger pointer.

Claim/evidence/handoff `--by` is `opencode-<full OpenCode session ID>` and cannot be
overridden. Open an OpenCode session before using these three commands. The full
ID is retained rather than truncating the common `ses_` prefix. It is provenance,
not verifier authority.

`--harness` and `--for` are **separate routing identities**: explicitly select an
existing registered harness. Use registered session-derived IDs, not generic
role labels. This adapter does not silently register harnesses or rewrite routing.
The backend's `session-start` **does** assign the selected harness if the task is
unassigned, marks it running, creates usage, and writes an export brief; its
confirmation discloses that behavior. It does not launch another agent.
`session-end` closes exactly the usage ID you enter, so inspect `/op:sessions`
first. It does not mark a task complete or verified. Already-running/closed
errors are shown as errors, not converted into success.

## Write and trust boundaries

- Each write shows its absolute executable, ledger working directory, and exact
  argv as JSON strings (so embedded newlines and control characters are visible).
  Long confirmations are paged, not truncated. Intermediate confirmations mean
  **continue**; the last one means **execute**. Cancel/Escape on any page prevents
  that write. A terminal smaller than 40×20 cannot authorize writes; resizing
  during confirmation cancels it so the command can be reviewed again.
- The adapter rechecks the session, workspace, ledger discovery, and relevant
  record existence after confirmation. This is not a transaction or protection
  against arbitrary concurrent file edits. Evidence bytes are fingerprinted by
  Operator when it attaches them, not frozen by the dialog.
- There are no model-callable tools, automatic ledger writes at startup/shutdown,
  raw CLI passthrough, provider calls, or sudo. Existing OpenCode shell tools and
  other plugins are outside this boundary; this adapter is not a sandbox.
- Stored verification commands are **not executed**. No verification-status,
  verifier-identity, verdict, or task-completion flags are accepted. Handoff's
  "What was verified" field is prose, not verification.
- Local evidence paths are relative to the **ledger root**, not the consumer
  project. An attached claim must belong to the selected task. Remote evidence
  is not locally snapshotted and may be uncheckable by doctor.
- A nonzero CLI exit can follow partial writes. The report does not promise
  rollback. Inspect the ledger before retrying; no automatic retries occur.
- Output stays in dialogs, not in model context or a durable OpenCode transcript.
  The Operator ledger remains the record. Long reports are paged; Escape stops
  viewing without undoing a command already executed.

## Deliberately excluded

Delegation/review, target registry editing, popup/sudo execution, verifier-account
execution, PBC shortcuts, crystals, automatic usage import, and other carriers.
No full-feature parity or release-readiness claim is made.

## Tests and remaining validation

```bash
node --experimental-strip-types --test tests/opencode_operator.test.ts
python3 -m pytest tests/test_opencode_operator.py -q
```

Tests require Node 22.6+ for TypeScript stripping and the backend prerequisites.
The current focused run passes **39 Node tests**, also exercised by the **one
pytest test** in `tests/test_opencode_operator.py`. They cover registration against a mock TUI API, cancellation, exact argv,
session/ledger guards, terminal-control escaping and paging, cross-project
contracts, failures, and a real Operator round trip in a disposable ledger.
They make no model calls and do not exercise privileged workflows.

A strict TypeScript check against the locally installed SDK API version
`@opencode-ai/plugin@1.18.18` reports no adapter-file diagnostics, but **does not
pass overall**: the unchanged shared Pi `core.ts` has existing type errors.
The automated runtime tests use type stripping, not a clean whole-dependency
typecheck.

**Live checks (2026-09-25), disposable ledger, no provider credentials:** the
first live run on OpenCode 1.18.22 found `mode: "base"` on the command layer hid
all commands although the Plugins dialog showed `operator.core` active. With
that setting removed, all 13 commands appear in the command palette, and each
of these completed against the real TUI: status/doctor, List all tasks,
`/op:use` (cancel wrote nothing; confirm wrote), brief (exit 1 before routing,
correctly surfaced; exit 0 after), export-brief, session-start, claim, evidence
and handoff (in an empty session created through the local server API, so no
model call; `--by`/`produced_by` recorded as `opencode-<session ID>`), and
session-end. Claim/evidence/handoff without an open session were refused. A
final doctor reported all records consistent. On OpenCode 1.18.32 the palette,
status/doctor and a confirmed `/op:use` also worked, including one owner install
into a separate project. The registration mock now rejects any `mode` key and
requires each command's palette namespace, Operator category, and slash name.

**Still not checked live:** slash autocomplete after the fix, the read-only
`/op:task`, `/op:claims` and `/op:sessions`, cancellation of writes other than
`/op:use`, broader keyboard/mouse and rendering/resizing coverage, and other
OpenCode versions or remote/attach setups.

For a **clean-HOME reproduction**, set `OPENCODE_DISABLE_AUTOUPDATE=1` when
launching the 1.18.22 binary. A fresh HOME otherwise auto-updates OpenCode to a
newer version on first launch, invalidating a version-specific reproduction.
Use an absolute path to the intended binary and a disposable project/ledger;
verify the version before the check.

To remove, delete this plugin's entry from `.opencode/tui.json` and restart.
Do not delete shared ledger contracts/configuration if the Pi adapter also uses
it. No ledger data needs to be removed.
