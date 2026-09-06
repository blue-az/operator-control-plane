# Cross-project install of the Operator Pi extension

Smallest supported path for using this project-local Pi extension from
**another repository**, without publishing a package and without copying
Operator runtime ledger data.

This helper is opt-in. It does not run `pi install`, does not write
`~/.pi/agent/settings.json`, and does not install into a live consumer unless
you pass that path yourself.

## What is actually discovered today

Inspected against Pi 0.85 docs and the installed loader, plus this repo's
`core.ts` `findLedger`.

### Pi loads the extension from the consumer cwd

Pi auto-discovers extensions from:

| Location | When it loads |
|---|---|
| `<cwd>/.pi/extensions/*.ts` | project-local, **after project trust** |
| `<cwd>/.pi/extensions/*/index.ts` | project-local subdirectory, **after project trust** |
| `~/.pi/agent/extensions/*.ts` and `*/index.ts` | global, every project |
| `settings.json` `"extensions"` array | extra files or directories |
| `settings.json` `"packages"` | npm / git / local pi packages |
| `pi -e <path>` | this run only |

`discoverAndLoadExtensions` joins `cwd` + `.pi/extensions`. It does **not**
walk parent directories. A consumer therefore needs its own
`.pi/extensions/operator/index.ts` (copy or symlink), or an explicit
`extensions` path in **that consumer's** `.pi/settings.json`.

Project-local `.pi/extensions` is a trust-gated resource. Interactive Pi asks
before loading it unless the folder (or a parent) is already in
`~/.pi/agent/trust.json`. Non-interactive runs (`-p`, `--mode json`, `--mode rpc`)
do not prompt; without a saved decision they follow `defaultProjectTrust`
(default `ask` = ignore). `--approve` / `--no-approve` override one run.

This helper does **not** record a trust decision.

### The extension follows an explicit external ledger contract

`core.ts` `findLedger(startDir)` walks **up** from the Pi cwd once and collects
at most:

1. the first sibling pair: a `.operator/` directory **and** a file named
   `operator`
2. the first `.pi/operator-ledger.json` file

Then:

- **Contract only:** require schema `operator-pi-extension-ledger-contract/v1`
  and an **absolute** `ledger_root` that itself has the sibling pair. Return
  that ledger. Malformed JSON, a relative path, or a missing pair fail closed
  — no parent guess.
- **Sibling pair only:** keep the historical walk-up.
- **Both, same canonical root:** return that ledger.
- **Both, different canonical roots:** fail closed as **ambiguous**.

`findLedger` does **not** honor `OPERATOR_DIR`, `OPERATOR_LEDGER_ROOT`, or
`settings.json` as a silent override of an explicit contract. It does not copy
or synthesize a consumer `.operator/`.

`index.ts` `requireLedger` names the contract path when nothing is found, and
surfaces malformed/ambiguous errors from `findLedger`. Completions fail closed
to no suggestions rather than throwing into Pi.

Installing the extension into a consumer makes `/op:*` appear after project
trust, and those commands resolve the recorded control-plane ledger through
the contract. Ledger writes still belong in that control-plane checkout.

The Operator CLI's own `find_operator_dir()` is a different walk: it only
requires `.operator/`, and it runs from the CLI process cwd. Copying or
symlinking the `operator` binary into a consumer without a sibling `.operator/`
does not make the CLI's walk succeed; the extension uses the contract instead.

**`wired_into_findLedger` is `true`.** The contract is the wire, not a note.

## Ledger path / config contract

On a successful install the consumer gets:

```
<consumer>/.pi/extensions/operator/   # copy of runtime files, or a symlink
<consumer>/.pi/operator-ledger.json   # explicit contract read by core.ts findLedger
<consumer>/.pi/operator-extension-starter.md
```

`operator-ledger.json` schema: `operator-pi-extension-ledger-contract/v1`.

| Field | Meaning |
|---|---|
| `ledger_root` | Canonical path of the control-plane checkout (must be absolute) |
| `operator_bin` | `ledger_root/operator` |
| `ledger_dir` | `ledger_root/.operator` |
| `extension_source` | Canonical path of the source `.pi/extensions/operator` |
| `method` | `copy` or `link` |
| `files` | Relative runtime files this helper installed (uninstall allowlist) |
| `installed_by` | `operator-pi-extension-install-helper` (ownership record) |
| `runtime_ledger_copied` | Always `false` |
| `wired_into_findLedger` | `true` (`core.ts` `findLedger` reads this contract) |
| `discovery` | What Pi vs `findLedger` actually do |

No file under `ledger_dir` is copied, linked, or created in the consumer.

## Install

From the Operator control-plane checkout:

```bash
python3 scripts/install-operator-extension.py \
  --target /path/to/consumer-repo \
  --ledger /path/to/operator-control-plane \
  --dry-run

python3 scripts/install-operator-extension.py \
  --target /path/to/consumer-repo \
  --ledger /path/to/operator-control-plane \
  --yes
```

`--ledger` may be omitted only when `--source` (default: this checkout) itself
holds both `.operator/` and `operator`. The helper will not search the
consumer tree or pick among parents.

| Flag | Effect |
|---|---|
| `--target` | Consumer repo root (required). Must already exist. |
| `--source` | Checkout that holds `.pi/extensions/operator` |
| `--ledger` | Control-plane root to record in the contract |
| `--method copy` | Copy runtime files (default) |
| `--method link` | Symlink the extension directory |
| `--dry-run` | Print the plan; write nothing |
| `--yes` | Opt-in without a TTY prompt. Required when stdin is not a TTY |
| `--uninstall` | Remove what this helper installed |

Refuses without `--yes` or an interactive `yes` when:

- this would write any file (first install is still opt-in)
- the destination extension directory or contract already exists

Always fails closed (no write) when:

- `--ledger` is missing and `--source` is not a control plane
- `--ledger` lacks `.operator/` or a file named `operator`
- the consumer already has a **different** `.operator/` (ambiguous: `findLedger`
  would see the local ledger, not the recorded one)
- `--target` **is** the control-plane root (the extension is already here)
- a dry-run was requested (by design: no write)

Copy method takes the extension tree under `.pi/extensions/operator/` except
`selftest.ts` and any `.operator/` / `node_modules/` path. That includes
subdirectory modules such as `orientation/actions.ts` when present, so a
consumer copy stays loadable if `index.ts` imports them. `selftest.ts` stays
in the control-plane checkout.

Safety (fail-closed):

- Source files that are symlinks, that contain `..`, or that resolve outside
  the extension directory are refused. The helper will not follow a planted
  symlink into unrelated files.
- Copy overwrite overlays owned files. It does **not** `rmtree` the dest
  tree, so extra user files under the extension directory survive reinstall.
- `--method link` will not replace an existing real directory with a
  symlink (that would delete extras). Uninstall first.
- Uninstall still requires the ownership record and still unlinks owned
  files one by one. `..` in the owned `files` list is refused.

## Uninstall

```bash
python3 scripts/install-operator-extension.py \
  --target /path/to/consumer-repo \
  --uninstall --dry-run

python3 scripts/install-operator-extension.py \
  --target /path/to/consumer-repo \
  --uninstall --yes
```

Refuses unless `<consumer>/.pi/operator-ledger.json` is this helper's
ownership record (`schema` + `installed_by` + a relative `files` list). An
unrelated `.pi/extensions/operator` tree without that record is left
untouched.

When the record matches, removes only the owned extension files listed in
the contract (or unlinks a symlink), then the contract and starter files.
Does **not** `rmtree` user trees. Extra files the user added under the
extension directory are left in place. Removes `.pi/extensions` only if it
is then empty. Leaves every other `.pi` file, and never touches `.operator/`.

To drop Pi's project-trust prompt after uninstall, also delete an empty
`.pi/` if you created nothing else, and/or remove the folder from
`~/.pi/agent/trust.json` via Pi's `/trust` UI. This helper does not edit
trust.json.

## Constrained subagent starter

A copy is written to `<consumer>/.pi/operator-extension-starter.md`. Use it as
the first paragraph of a subagent prompt:

```
Work only inside this consumer repository. The Operator Pi extension files
under .pi/extensions/operator are a local copy or symlink; do not edit the
control-plane sources unless that path is your assigned ownership.

The intended Operator ledger is the ledger_root recorded in
.pi/operator-ledger.json. Do not copy, symlink, or initialize .operator/ in
this consumer. Do not run git commit, push, publish, model pulls, GPU jobs,
or server changes. Do not claim verification and do not change identity
policy.

Pi will load .pi/extensions/operator/index.ts only after this project is
trusted. /op:* resolve the ledger by walking up from cwd for a sibling
.operator/ plus a file named operator, and by reading
.pi/operator-ledger.json. A valid v1 contract with an absolute ledger_root
that has that pair is used. Malformed JSON, a relative path, a missing pair,
or disagreeing canonical roots fail closed.

Do not run pi install, do not write ~/.pi/agent/settings.json, and do not
publish this extension.
```

## Package test gate (not a publish step)

This helper is not a publisher. Before anyone even considers `pi install`
(npm/git) or a gallery listing:

1. `python3 -m pytest tests/test_install_operator_extension.py -q`
2. `python3 -m pytest tests/test_pi_operator_extension.py -q`
3. `node --experimental-strip-types .pi/extensions/operator/selftest.ts`
4. Confirm no consumer `.operator/` was created by the installer
5. Confirm `wired_into_findLedger` is true and that two throwaway consumers
   resolve `findLedger` to the recorded external `ledger_root` without a
   copied `.operator/`

Do not run those as a side effect of install. Do not execute a stored
`--verify-cmd` from a ledger record to “prove” the install.

## Exact `findLedger` contract (implemented)

`findLedger(startDir)`, after resolving `startDir`:

1. Walks upward once, collecting at most:
   - the first sibling control plane (directory with both `.operator/` and a
     file `operator`)
   - the first `.pi/operator-ledger.json`
2. If **both** exist and their canonical roots differ: fail closed as
   **ambiguous**. Does not pick one.
3. If only the contract exists: requires `schema` to be
   `operator-pi-extension-ledger-contract/v1`, requires `ledger_root` to be an
   absolute path whose directory contains both `.operator/` and `operator`,
   and returns that `Ledger`. Malformed JSON, a relative path, or a missing
   pair fail closed — no parent guess.
4. If only a sibling control plane exists: historical walk-up.
5. Does not treat `OPERATOR_DIR`, `OPERATOR_LEDGER_ROOT`, or settings.json as a
   silent override of an explicit contract.
6. Does not copy or synthesize a local `.operator/` in the consumer.

`index.ts` `requireLedger` mentions the contract path in its missing-ledger
message. `selftest.ts` covers a contract-only pair of consumers and an
ambiguous fixture.

## What this is not

- Not a pi package, not `pi install npm:` / `git:`, not a gallery publish
- Not a global install under `~/.pi/agent/extensions/`
- Not automatic trust of the consumer project
- Not a second ledger, and not an alternate authority path
- Not a way to mark claims verified
