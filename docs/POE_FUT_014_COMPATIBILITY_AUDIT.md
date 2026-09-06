# POE-FUT-014 Compatibility Audit

**Status:** audit complete; **Route C recorded** as a compatibility-route
choice (local wrapper `scripts/pbc_validate_operator.py`). This document
does not ratify rules, blocks, trust values, or an upstream profile. Stock
CLI still has **no** `--profile` flag.
**Task:** `pi-operator-extension-pbc-profile`
**Date:** 2026-09-05
**Scope:** document Operator PBC dialect versus the local upstream `pbc-spec`
CLI, exercise fixtures, and recommend a route. Implementation of a profile,
PBC edits, extension commands, and publishing wait on an explicit user choice.

## 1. What this audit is for

POE-FUT-014 asks whether Operator-authored `.pbc.md` files can be checked with
the upstream Product Behavior Contract CLI before any publish path
(POE-FUT-012). The future-slice text names three routes:

1. upstream lifecycle support for `proposed-*` blocks
2. portable block names only (avoid custom fences)
3. an explicit Operator dialect/profile that accepts
   `proposed-rules` / `proposed-behavior` / `proposed-outcomes` and local trust
   vocabulary while still catching real YAML and frontmatter errors

The slice command sketch (`/pbc:validate` or `pbc validate --profile operator`)
is not implemented here. Official Pi docs treat custom slash commands as
`pi.registerCommand` handlers on a project-local extension, loaded only after
project trust. They are not model-callable tools. This audit does not add that
command.

## 2. Pinned upstream

Observed local checkout, read-only, no install, no network:

| Field | Value |
|---|---|
| Path | `/home/blueaz/Python/Evaluation/pbc-spec` |
| Origin | `https://github.com/blue-az/pbc-spec.git` |
| Upstream remote | `https://github.com/stewie-sh/pbc-spec.git` |
| Branch | `fix/fail-closed-validation` |
| Commit | `ca97caf63329cee5ecf2b92dfe1120374ab90a81` |
| Describe | `v0.6.0-20-gca97caf` |
| Committed | 2026-08-28 00:09:42 -0700 |
| Subject | `fix(cli): fail closed on malformed PBC blocks` |
| Spec version | `0.6.0-draft` (`docs/specs/pbc-spec-v0.6.md`) |
| CLI package | `@pbc-spec/cli@0.1.0` |
| CLI binary used | `cli/dist/bin/pbc.js` (already built) |
| Node | v22.22.2 |
| `--profile` flag | **absent** |
| Working tree | clean at audit time |

The CLI README states it is local reference tooling, not published to npm.
`STATUS.md` still calls the CLI a reference implementation, not production
tooling. Known block types and trust enums are in `cli/src/parser/types.ts`.

Pi documentation read for the future command surface (not executed):
`/home/blueaz/Python/Evaluation/pi-mono` at
`e86823096c5bad39e1ca282ec24bc5eb9bec745b`, especially
`packages/coding-agent/docs/extensions.md`, `usage.md`, and `security.md`.

## 3. Method

- Read `pbc_lint.py`, `docs/PROPOSAL_LIFECYCLE.md`, Operator PBC files, and
  upstream parser/validator sources.
- Invoke the **already-built** CLI with `node cli/dist/bin/pbc.js validate`.
  No `npm install`, no `npm test`, no model pulls, no GPU jobs.
- Copy audit fixtures into temporary directories before lint/validate.
- Do not execute stored verification commands.
- Do not edit `owners-manual/pbc/`, the Pi extension, README, or the upstream
  repository.

Re-run:

```bash
python3 -m pytest tests/test_poe_fut014_compatibility.py -q
python3 scripts/poe_fut014_audit.py
```

Optional: `POE_FUT014_PBC_SPEC=/path/to/pbc-spec` if the default checkout is
absent. Tests skip CLI assertions rather than false-pass when the binary is
missing.

## 4. Operator dialect as actually authored

Inventory of `owners-manual/pbc/*.pbc.md` (read-only):

### 4.1 Block types in use

| Fence | Upstream known? | Role in Operator |
|---|---|---|
| `pbc:actors` | yes (stable) | used |
| `pbc:behavior` | yes (stable) | used |
| `pbc:outcomes` | yes (stable) | used |
| `pbc:rules` | yes (stable) | ratified / verified facts |
| `pbc:grounding` | yes (experimental) | supporting context |
| `pbc:provenance` | yes (stable supporting) | evidence notes |
| `pbc:proposed-rules` | **no** | lifecycle Shape A proposals |
| `pbc:proposed-behavior` | **no** | lifecycle Shape A proposals |
| `pbc:proposed-outcomes` | **no** | lifecycle Shape A proposals |

`pbc_lint.py` only special-cases `rules` and the three `proposed-*` kinds.
Every other fence is ignored by the linter.

### 4.2 Trust, status, provenance

Operator trust values observed in live files:

- `proposed` (lifecycle; forbidden on `pbc:rules` by invariant 1)
- `verified` (used as a local “this is a live CLI fact” label)
- `provisional`
- `trusted`
- `agreed`
- `agreed-pending-operator`

Upstream `VALID_TRUST_LEVELS`: `trusted`, `provisional`, `scaffolding`.

Frontmatter `status` observed: `draft`, `deprecated`, `active`.
Upstream recommended statuses: `draft`, `review`, `agreed`, `deprecated`.
`status: active` is an Operator `pbc_lint` invariant-4 trigger, not an
upstream recommended value (CLI emits W011).

Provenance `confidence: measured` appears in Operator files. Upstream allows
only `verified`, `inferred`, `assumed` and fails closed (E011).

### 4.3 What `pbc_lint.py` actually checks

Fail-closed on four fence invariants (`docs/PROPOSAL_LIFECYCLE.md` §4):

1. no `trust: proposed` inside `pbc:rules`
2. every `pbc:proposed-*` is named from a frozen claim (**only** with `--ledger`)
3. no rule id in both proposed and ratified fences
4. `status: active` requires a `pbc:rules` block

It is a regex over fences, not a YAML parser. It does not require frontmatter
`id`/`title`, does not parse block YAML, does not reject unknown block types,
and does not check provenance confidence. CI without `--ledger` checks 1, 3,
and 4 only.

Fence regex difference versus upstream:

- Operator: `` ^```pbc: `` at column 0
- Upstream: GFM `` ^ {0,3}```pbc:([^\s`]+) `` (`docs/specs/pbc-spec-appendix-gfm.md`)

## 5. Upstream CLI as actually implemented

Commands: `validate`, `list`, `stats`, `init`. No profile, no plugin hook.

`validate` checks (from `cli/README.md` plus source; W013 is implemented but
not listed in that README table):

| ID | Severity | Meaning |
|---|---|---|
| E001 | error | missing YAML frontmatter |
| E002 | error | frontmatter missing `id` |
| E003 | error | frontmatter missing `title` |
| E004 | error | unrecognized `pbc:*` block type |
| E005 | error | YAML parse failure or unclosed `pbc:*` fence |
| E006 | error | duplicate semantic IDs |
| E007/E008 | error | `pbc:behavior` missing `id`/`name` |
| E009/E010 | error | unknown state/actor references |
| E011 | error | invalid provenance `confidence` |
| W011 | warning | non-standard frontmatter `status` |
| W013 | warning | trust not in `trusted\|provisional\|scaffolding` |

Exit 0 if there are no errors. Warnings do not fail the process.

Unknown block types are **parsed then rejected** (E004). They are not dropped.
That fail-closed behavior is the property a compatibility route must keep.

## 6. Live Operator tree versus stock CLI

Read-only `pbc validate --format json owners-manual/pbc` at the pinned CLI,
2026-09-05. Process exit 1. `python3 pbc_lint.py owners-manual/pbc` exit 0.

| File | CLI errors | CLI warnings |
|---|---:|---:|
| `01-what-operator-is-for.pbc.md` | 0 | 2 |
| `02-how-work-moves-through-the-ledger.pbc.md` | 0 | 2 |
| `03-the-surfaces-and-records-you-actually-operate.pbc.md` | 0 | 2 |
| `04-trust-identity-and-verification.pbc.md` | 0 | 2 |
| `05-sessions-usage-and-accountability.pbc.md` | 0 | 2 |
| `06-running-a-multi-harness-workflow.pbc.md` | 0 | 2 |
| `product-overview.pbc.md` | 0 | 1 |
| `appendix-local-implementer-dispatch.pbc.md` | 2 | 4 |
| `appendix-local-routing-corpus.pbc.md` | 11 | 4 |
| `appendix-multi-session-coordination.pbc.md` | 1 | 6 |
| `appendix-opr-governed-llm-client.pbc.md` | 3 | 0 |
| `appendix-pi-operator-extension.pbc.md` | 7 | 5 |
| `appendix-prime-agent-evidence-ingestion.pbc.md` | 1 | 7 |

Totals: **25 errors, 39 warnings** across 13 files.

Check ID counts:

| ID | Count | Cause |
|---|---:|---|
| E004 | 21 | `proposed-rules` (4), `proposed-behavior` (10), `proposed-outcomes` (7) |
| E005 | 2 | YAML parse errors in `appendix-pi-operator-extension.pbc.md` `pbc:grounding` at lines 378 and 436 |
| E011 | 2 | `confidence: measured` in `appendix-local-routing-corpus.pbc.md` |
| W013 | 24 | `trust: verified` on `pbc:rules` |
| W011 | 1 | `status: active` |
| W002 | 8 | missing `updated` |
| W008 | 6 | behavior without companion blocks |

The two E005 hits are real YAML errors in a live draft. `pbc_lint.py` does not
see them. That is the load-bearing gap: Operator’s current linter is not a
substitute for the upstream fail-closed YAML/frontmatter checks. This audit
does not edit those PBC files.

Chapter-level contracts that stay on known blocks (`pbc:actors`,
`pbc:behavior`, `pbc:grounding`, `pbc:provenance`) already validate with
**zero CLI errors**. The blocking dialect is concentrated in appendix files
that use `proposed-*`, plus provenance confidence and two YAML defects.

## 7. Fixture matrix (temporary directories)

Fixtures live under `tests/fixtures/poe_fut014/` with a `poe_fut014_` prefix.
`scripts/poe_fut014_audit.py` and `tests/test_poe_fut014_compatibility.py`
copy them into temp dirs before running tools.

| Fixture | CLI | `pbc_lint` | Notes |
|---|---|---|---|
| `poe_fut014_valid_upstream_core.pbc.md` | 0 (W010) | 0 | portable subset |
| `poe_fut014_valid_proposed_lifecycle.pbc.md` | 1 / E004 | 0 | proposed fences reported, not dropped |
| `poe_fut014_valid_local_trust.pbc.md` | 0 (W010, W013) | 0 | `trust: verified` is warning-only |
| `poe_fut014_invalid_yaml.pbc.md` | 1 / E005 | 0 | CLI fail-closed; linter gap |
| `poe_fut014_invalid_frontmatter_missing.pbc.md` | 1 / E001 | 0 | linter gap |
| `poe_fut014_invalid_frontmatter_no_id.pbc.md` | 1 / E002 | 0 | linter gap |
| `poe_fut014_invalid_frontmatter_no_title.pbc.md` | 1 / E003 | 0 | linter gap |
| `poe_fut014_invalid_frontmatter_broken.pbc.md` | 1 / E001 | 0 | linter gap |
| `poe_fut014_invalid_unclosed.pbc.md` | 1 / E005 | 0 | linter gap |
| `poe_fut014_invalid_unknown_block.pbc.md` | 1 / E004 | 0 | `pbc:not-a-block` not dropped |
| `poe_fut014_invalid_rules_trust_proposed.pbc.md` | 0 (W013) | 1 | Operator invariant 1; CLI warning only |
| `poe_fut014_invalid_provenance_confidence.pbc.md` | 1 / E011 | 0 | `measured` is an error upstream |

No fixture silently dropped an unsupported block. Proposed lifecycle fixtures
are **not** treated as ratified by either tool.

## 8. Compatibility findings

1. **Stock `pbc validate` cannot accept current Operator appendix contracts.**
   `proposed-*` is E004. That is fail-closed, which is correct, but it means
   “just run the upstream CLI” is not a publish gate today.
2. **Local trust is not the blocking error.** `trust: verified` and
   `trust: proposed` on known blocks are W013 warnings. A file that only uses
   known blocks and `trust: verified` still exits 0.
3. **`status: active` is a warning (W011), not an error.** Operator invariant 4
   still depends on that non-standard status.
4. **`pbc_lint.py` will not catch YAML/frontmatter defects the CLI already
   catches.** Live proof: two E005 errors in
   `appendix-pi-operator-extension.pbc.md` while `pbc_lint` exits 0.
5. **There is no `--profile` surface to hang an Operator dialect on.** A
   profile is a new flag or a local wrapper, not a hidden CLI switch.
6. **Operator invariant 1 is stricter than the CLI** for
   `pbc:rules` + `trust: proposed` (linter error vs W013).
7. **Provenance `confidence: measured` is a hard CLI error (E011)** and is
   invisible to `pbc_lint`.
8. A wrapper that “makes Operator files pass” by discarding E004/E005/E001
   would be silent suppression. That is out of bounds for any later
   implementation.

## 9. Routes (none chosen)

### Route A — upstream lifecycle support

Contribute `proposed-rules`, `proposed-behavior`, and `proposed-outcomes` to
`pbc-spec` as experimental blocks, and optionally extend trust/status enums.

- Fits CONTRIBUTING.md “additive” spec changes.
- Lets stock `pbc validate` read Operator files without a profile.
- Out of this repo’s ownership; requires a spec PR and a pinned CLI upgrade.
- Must still keep E004 for *other* unknown types and E005 for bad YAML.
- Does not by itself encode Operator invariants 1–4.

### Route B — portable block names

Stop using `proposed-*`. Keep proposals in `pbc:rules` / `pbc:behavior` /
`pbc:outcomes` / `pbc:grounding` with a field such as `lifecycle: proposed`.

- Stock CLI would then see only known types.
- Breaks the fence-based lifecycle that `pbc_lint.py` and
  `PROPOSAL_LIFECYCLE.md` already enforce.
- Requires editing live PBC files (not done here) and rewriting the linter.
- Easy to accidentally leave `trust: proposed` inside `pbc:rules`, which is
  exactly the half-ratification case invariant 1 exists to stop.

### Route C — explicit Operator profile (selected as compatibility route)

Keep Operator lifecycle fences. Add a **named** local profile or wrapper
that:

- uses the upstream parser/validator
- allowlists `proposed-rules`, `proposed-behavior`, `proposed-outcomes`
- allowlists documented Operator trust/status/confidence values by name
- still emits E004 for any other unknown type
- still emits E001–E003 and E005
- still runs `pbc_lint.py` invariants 1–4
- never moves `proposed-*` into `pbc:rules`

Today that would be a local wrapper (the CLI has no `--profile`). A later
upstream `--profile operator` would be Route A+C, not a substitute for
recording the choice.

### Why Route C is the recommendation

`proposed-*` is load-bearing in this repository. Route B is a contract rewrite,
not a compatibility shim. Route A is the right long-term shareable language
change, but it is a different repository and is not required to start catching
the YAML/frontmatter errors Operator currently misses. Route C is the only
option that preserves the lifecycle fence, keeps fail-closed YAML/frontmatter
checks, and does not pretend stock `pbc validate` already understands Operator.

A future `/pbc:validate` Pi command, if ever added, should wrap that profile
as a human slash command (`pi.registerCommand`), not a model tool, and must
not execute stored verification commands.

## 10. What is not ratified

- No `proposed-*` block is accepted as a canonical upstream type.
- No Operator trust value is added to the upstream enum.
- No PBC file was edited.
- No extension command was added.
- No identity policy changed.
- Passing these audit tests does not mean Operator PBCs are publishable.

## 11. Next steps (blocked on user choice)

1. Choose Route A, B, or C in writing. **Done:** Route C recorded 2026-09-05
   after the user replied “Proceed as suggested” to the Route C
   recommendation. Compatibility-route choice is not PBC ratification.
2. Only then implement the chosen route (profile wrapper, spec PR, or PBC
   rewrite). **Done for C:** local wrapper
   `scripts/pbc_validate_operator.py` plus regression tests. No upstream
   `--profile` was added or claimed.
3. Independently, the two live E005 YAML defects in
   `appendix-pi-operator-extension.pbc.md` were quoted in closeout (semantics
   unchanged). `confidence: measured` in
   `appendix-local-routing-corpus.pbc.md` was inspected and left as local
   empirical vocabulary; the wrapper allowlists that value by name and does
   not relabel it to `verified`.
4. POE-FUT-012 publishing remains gated: the wrapper is now the documented
   Operator check, but npm/git/`pi install` publication is still not
   authorized.

## 12. Evidence commands

```bash
python3 -m pytest tests/test_poe_fut014_compatibility.py -q
# 21 passed

python3 scripts/poe_fut014_audit.py
# exit 0; fixture matrix matches §7; route not chosen

NO_COLOR=1 node /home/blueaz/Python/Evaluation/pbc-spec/cli/dist/bin/pbc.js \
  validate --format json owners-manual/pbc
# exit 1; 25 errors / 39 warnings as in §6

python3 pbc_lint.py owners-manual/pbc
# exit 0

python3 scripts/pbc_validate_operator.py
# Route C local wrapper (after the 2026-09-05 recorded choice)
```

## 13. Closeout re-run (still not a route choice)

2026-09-05 closeout quoted unquoted `: ` scalars in the two
`pbc:grounding` blocks that had been E005. Semantics unchanged. Live tree
after that quoting:

| ID | Count | Kind |
|---|---:|---|
| E004 | 21 | unsupported `proposed-*` (genuine dialect mismatch, not YAML) |
| E005 | 0 | previous YAML defects gone |
| E011 | 2 | `confidence: measured` in `appendix-local-routing-corpus.pbc.md` (untouched; not a quoting bug) |

`pbc_lint.py owners-manual/pbc` still exits 0. Fixture matrix for the
**stock CLI** is unchanged. Route C was later recorded and implemented as
a local wrapper; see §14.

## 14. Route C recorded (compatibility wrapper, not ratification)

2026-09-05 human ruling: user replied “Proceed as suggested” to the
recommendation to choose Route C, implement, record in the ledger, and run
a disposable consumer smoke test. That choice is **not** ratification of
`proposed-*` rules or of local trust/confidence enums.

Implemented local wrapper: `scripts/pbc_validate_operator.py`.

| Property | Value |
|---|---|
| Upstream `--profile` | **absent**; wrapper does not claim it |
| Pinned commit | `ca97caf63329cee5ecf2b92dfe1120374ab90a81` |
| Allowlisted E004 types | `proposed-rules`, `proposed-behavior`, `proposed-outcomes` |
| Allowlisted E011 value | `measured` only (empirical; not relabeled to `verified`) |
| Still fail-closed | other E004 types, E001–E003, E005, other E011, `pbc_lint` 1–4 |
| Silent drop | forbidden; allowlisted rows remain in the report |
| `/pbc:validate` | still not implemented |

`confidence: measured` in `appendix-local-routing-corpus.pbc.md` sits next
to `review_status: unverified` and cites study documents. Relabeling it to
`verified` would invent established provenance. The wrapper keeps the
string `measured`.

```bash
python3 -m pytest tests/test_pbc_validate_operator.py -q
python3 scripts/pbc_validate_operator.py
# local wrapper; not `pbc validate --profile operator`
```
