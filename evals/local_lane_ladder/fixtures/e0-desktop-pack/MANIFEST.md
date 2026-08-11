# E0 — desktop fixture pack (frozen 2026-08-11)

**Front E0** (`docs/handoffs/NEXT_SESSION.md` §E in project-phoenix): first executable
slice of Front E's routability question, using the already-built local-lane-contract
apparatus (`LOCAL_LANE_CONTRACT_SPEC.md`) rather than the separate, still-unbuilt
250-transcript fixturability probe.

## Why this pack, why desktop

Every prior ladder sweep ran on z13. `PILOT_CONFOUND_FINDINGS.md`: "Results are
decode-rate dependent and do not transfer to other hosts." z13 also has a permanent
gap: `qwen2.5-coder:32b` is not installed there, so 9 of the 216 historical cells were
structurally unreachable.

Desktop (verified 2026-08-11 via SSH) has all four ladder models installed, including
`qwen2.5-coder:32b`, and is otherwise idle. A pack run there is a genuinely new data
point, not a rerun.

## What's frozen

Three L2-only (plan-shaped) tasks, pinned as byte-identical copies of the live ladder
task defs in `evals/local_lane_ladder/tasks/`, chosen to cover the three failure
classes the ladder was built to isolate (see `LOCAL_LANE_CONTRACT_SPEC.md` Deliverable
3, task list):

| Task | Failure class isolated | sha256 |
|---|---|---|
| `alias_add.yaml` | anchored append | `8fc729bd...59d960b9` |
| `config_value_change.yaml` | in-place edit | `8d6fffc8...789c89f56a` |
| `grep_and_report.yaml` | read-only discovery (no patch-anchoring involved) | `cf346611...9b53f0dc44b6e` |

Full checksums:

```
8fc729bdc1389d2949bf94c713f09432aacf99a3dae5e7456c5c74f759d960b9  tasks/alias_add.yaml
8d6fffc876aa7c66ef670f0e13c10b90e1eb1eaa2e4e86421dfc50979c89f56a  tasks/config_value_change.yaml
cf34661157302a7970b1fc4f6686d775a9d88d042de90e694e09b53f0dc44b6e  tasks/grep_and_report.yaml
```

**Deliberately excluded from this pack:** `doc_fix`, `function_add`,
`multi_file_rename_reference` — not dropped for cause, just kept out to keep this pack
small per the front's own "never open a ladder without a cost stop" guidance. Nothing
stops a second, larger pack later if the desktop data point looks worth extending.

**L0/L1 excluded on purpose.** This pack asks only "does plan-shaped work on desktop,"
not "how much specificity does desktop need" — that's a bigger question and a bigger
pack.

## Lint verification (2026-08-11, `task_lint.py`)

All three L2 prompts verified `plan-shaped` (all R1-R6 PASS) before freezing:

```
alias_add            -> overall='plan-shaped'  (R1-R6 all PASS)
config_value_change  -> overall='plan-shaped'  (R1-R6 all PASS)
grep_and_report      -> overall='plan-shaped'  (R1-R6 all PASS)
```

## Target environment

- **Machine:** desktop (`desktop.local`), single RTX 3090.
- **Models:** `gemma4:26b`, `gemma4:31b`, `llama3.1:8b`, `qwen2.5-coder:32b` — all
  confirmed installed via `ollama list` over SSH, 2026-08-11.
- **Harness commit:** desktop's `operator-control-plane` checkout was merged to
  `origin/master` (`38e26c9`) on 2026-08-11 specifically for this pack — its prior
  checkout (`670fada`, 2026-07-24) predated both `890d595` (continuation-loop fix)
  and `d5eea34` (timeout fix). Running against the old checkout would have
  reproduced the exact truncation confound `PILOT_CONFOUND_FINDINGS.md` already
  documents. Desktop's own unpushed local commit (`670fada`, "Role-scope review
  briefs...") was preserved via `git merge`, not discarded.
- **Power cap:** at freeze time, desktop's GPU power limit reads 320 W, above the
  200 W ceiling `LOCAL_LANE_CONTRACT_SPEC.md`'s hardware-constraints section
  requires before any sweep (marginal PSU; already failed once, 2026-07,
  destroying 2 of 4 RAM sticks). **Erik explicitly instructed running uncapped and
  accepting the risk** (2026-08-11 session) after this was flagged twice. Recorded
  here so a future reader doesn't mistake the omission for an oversight.

## Running

See `RUN.md` in this directory for the exact command.
