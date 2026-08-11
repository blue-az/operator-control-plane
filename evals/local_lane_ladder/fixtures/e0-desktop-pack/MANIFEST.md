# E0 — desktop fixture pack (frozen 2026-08-11, corrected 2026-08-11)

**Ledger task:** `front-e0-desktop-fixture-pack`.

**Correction notice.** This pack's original premise was wrong and was caught by peer
review (`front-e0-desktop-pack-review`, `.operator/evidence/front-e0-desktop-pack-review/evidence-0001.md`,
filed by `claude-consultant`). The original text below this notice has been rewritten
to match what actually happened; see "What this pack actually is" for the corrected
claim and "What was wrong" for the record of the mistake. Do not restore the original
"genuinely new data point" framing — it was checked against both machines' ledgers and
did not hold.

## What this pack actually is

**A reproduction, not new evidence.** The 216-cell historical ladder (`RESULTS.md`,
`state.json` in the parent `evals/local_lane_ladder/` directory) ran on **desktop**,
2026-07-21 — not z13 as this pack originally claimed. Desktop's ledger holds 660
`eval-*` task events dated 2026-07-21, all `executor.machine: desktop`; z13's ledger
holds zero. `qwen2.5-coder:32b` was already fully covered in that July run (3/3 on all
three tasks this pack selects) — it was never "structurally unreachable," that gap was
specific to the later z13-only confound-pilot replay, not the base ladder.

E0 reran the same three tasks, same four models, same L2 level, on the same host, and
reproduced July in 11 of 12 (task, model) cells — the one delta
(`config-value-change|llama3.1:8b`: July 2/3, E0 1/3) is a single-trial flip, not a
finding, per MSC-RUL-107.

**The one real result:** July's sweep predates `890d595` (continuation-loop fix) and
`d5eea34` (timeout fix); E0 ran after merging both in. Pass rates on these three tasks
at L2 did not move. **The continuation-loop and timeout fixes changed nothing
measurable here.** That is worth recording — `PILOT_CONFOUND_FINDINGS.md` exists
because those fixes mattered elsewhere — but it is a harness-regression check, not a
routability data point, and does not discharge Front E's "zero verified evidence"
status in `BOTTLENECKS.md`.

## What was wrong (kept for the record, do not delete)

The pack's original "Why this pack, why desktop" section claimed:

1. "Every prior ladder sweep ran on z13" — **false**. Only the confound pilot
   (`PILOT_CONFOUND_FINDINGS.md`) ran on z13; the base 216-cell ladder ran on desktop.
   The mistake: generalizing from the confound pilot's explicit z13 documentation to
   the base ladder, without checking machine provenance in the base ladder's own
   `state.json`/ledger records.
2. "z13 also has a permanent gap: qwen2.5-coder:32b... 9 structurally unreachable
   cells" — true for the z13 confound-pilot replay specifically, misleadingly
   generalized here to imply the base ladder lacked qwen2.5-coder:32b coverage. It
   didn't; July's desktop run covered it fully.
3. "A pack run there is a genuinely new data point, not a rerun" — **false**,
   consequence of (1). It's a rerun on the same host.
4. The power-cap paragraph implied the 2026-07 PSU failure itself destroyed 2 of 4 RAM
   sticks. **Operator-confirmed 2026-08-11: the RAM loss was human error during
   incident response, unrelated to power draw.** The PSU failure and RAM loss were
   temporally coincident (same incident), which this pack's author conflated into an
   implied causal/electrical link that was never checked before writing it down.

## What's frozen (unchanged by the correction — F1 in the review confirmed no drift)

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

Verified 2026-08-11 (review F1): these match both the copies in this directory and
desktop's live `tasks/` directory — no drift.

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
  checkout (`670fada`, 2026-07-24) predated both `890d595` and `d5eea34`. Running
  against the old checkout would have reproduced the exact truncation confound
  `PILOT_CONFOUND_FINDINGS.md` documents. Desktop's own unpushed local commit
  (`670fada`, "Role-scope review briefs...") was preserved via `git merge`, not
  discarded.
- **Power cap:** at run time, desktop's GPU power limit read 320 W, above the 200 W
  ceiling `LOCAL_LANE_CONTRACT_SPEC.md` previously required. Ran uncapped, operator's
  explicit call. **Corrected framing (see `LOCAL_LANE_CONTRACT_SPEC.md` for the
  updated spec text):** the cap protects a long unattended sweep from losing progress
  to a mid-run reset, not the hardware — this runner writes `state.json` and resumes,
  so a crash costs a restart, not data. It ran full uncapped with zero incident: 36/36
  cells completed, GPU returned to 55-61°C / 0% util / idle draw afterward.

## Running

See `RUN.md` in this directory for the exact command.
