# E0 desktop pack — consultant review

**Filed by:** `claude-consultant` (desktop, uid 1000) · 2026-08-11
**Subject:** `evals/local_lane_ladder/fixtures/e0-desktop-pack/` (frozen 2026-08-11 by `claude-supervisor`, z13)
**Posture:** findings only. Nothing in the pack, the spec, `BOTTLENECKS.md`, or git has been
modified by this review. Per MSC-RUL-103, disagreement is filed as a handoff, not an edit.

---

## What holds up

The run itself is sound. Verified independently, not taken on report:

| Check | Result |
|---|---|
| Grid complete | 36/36 `done: true`; `results` holds 36 records |
| Process health | `returncode: 0` on all 36 — no crashes, no timeouts |
| Executor | `machine: desktop` on every record |
| Task provenance | All 3 pinned `sha256` match MANIFEST **and** desktop's live `tasks/` — no drift |
| Ledger hygiene | `session_started` **and** `session_ended`, `ended_at` populated, `outcome: useful`, `harness_id=local-lane-eval`, `lane=local`, `task_class=bounded` |

The last row matters specifically: the July sweep shipped with `session-end` leaving every record
open (`ended_at: null`). That regression is not present here.

A hypothesis this review raised and then **withdrew**: the llama3.1:8b failures cluster at
~1.5 s wall-clock, which looked like empty output rather than genuine attempts.
`config-value-change|llama3.1:8b|t3` **passed** at 1.5 s. Short duration is not a truncation
signature. No confound. The 3/9 is a real result.

---

## F1 — The pack's stated premise is falsified

MANIFEST §"Why this pack, why desktop" rests on three claims. All three fail.

> "Every prior ladder sweep ran on z13."

Desktop's ledger holds **660 eval task events dated 2026-07-21, every one stamped
`executor.machine: desktop`.** z13's ledger holds **zero** eval events.

```bash
# desktop — 660 events, machine=desktop
python3 - <<'PY'
import sqlite3, json, collections
c = sqlite3.connect(".operator/ledger.sqlite3")
rows = c.execute("SELECT payload_json, created_at FROM ledger_events "
                 "WHERE record_type='task' AND record_id LIKE 'eval-%'").fetchall()
by = collections.Counter()
for p, ca in rows:
    d = json.loads(p)
    by[((d.get("executor") or {}).get("machine"), ca[:10])] += 1
print(len(rows), dict(by))
PY

# z13 — same query returns 0
ssh z13 'cd ~/operator-control-plane && ...same query...'
```

> "z13 also has a permanent gap: `qwen2.5-coder:32b` is not installed there, so 9 of the 216
> historical cells were structurally unreachable."

July has complete `qwen2.5-coder:32b` results — 3/3 on all three of this pack's tasks.
`BOTTLENECKS.md`'s own July entry reports its full ladder (0→12→17/18). Nothing was unreachable.

> "A pack run there is a genuinely new data point, not a rerun."

It is a rerun, on the same host, and it reproduced July in 11 of 12 cells (F2).

**Consequence, and the reason this is filed rather than fixed:** Front E's BN entry currently
reads *"the only front with zero verified evidence."* If E0 lands as "first verified data point,
new host, qwen cell newly reachable," that replaces *no evidence* with *false evidence* — in the
front least able to absorb it.

## F2 — E0 reproduces the July sweep

L2, same three tasks, same four models, desktop both times:

| task | model | Jul 2026-07-21 | E0 2026-08-11 |
|---|---|---|---|
| alias-add | gemma4:26b | 3/3 | 3/3 |
| alias-add | gemma4:31b | 3/3 | 3/3 |
| alias-add | llama3.1:8b | 0/3 | 0/3 |
| alias-add | qwen2.5-coder:32b | 3/3 | 3/3 |
| config-value-change | gemma4:26b | 3/3 | 3/3 |
| config-value-change | gemma4:31b | 3/3 | 3/3 |
| config-value-change | llama3.1:8b | 2/3 | **1/3** |
| config-value-change | qwen2.5-coder:32b | 3/3 | 3/3 |
| grep-and-report | gemma4:26b | 3/3 | 3/3 |
| grep-and-report | gemma4:31b | 3/3 | 3/3 |
| grep-and-report | llama3.1:8b | 2/3 | 2/3 |
| grep-and-report | qwen2.5-coder:32b | 3/3 | 3/3 |

Source: `evals/local_lane_ladder/state.json` (July, 71 KB, mtime 2026-07-20) vs
`fixtures/e0-desktop-pack/state.json`. The single delta is one trial on the model that flips.
Per MSC-RUL-107 no finding here rests on that one cell.

## F3 — Salvage: E0 is a valid result under a different claim

July's sweep predates `890d595` (continuation-loop fix) and `d5eea34` (timeout fix) — MANIFEST
says so itself, which is why the checkout was merged before running. So E0 is an unintended but
clean before/after:

> **The continuation-loop and timeout fixes moved L2 pass rates on these three tasks by zero.**

Given that `PILOT_CONFOUND_FINDINGS.md` exists precisely because truncation confounded earlier
results, "the fix changed nothing measurable here" is worth recording. It is not a routability
data point, and it does not discharge Front E.

## F4 — MANIFEST's hardware rationale is factually wrong

MANIFEST §"Target environment" states the 320 W cap was exceeded against a *"marginal PSU;
already failed once, 2026-07, destroying 2 of 4 RAM sticks"* and logs the operator's decision as
*"explicitly instructed running uncapped and accepting the risk."*

Operator correction, 2026-08-11:

- The RAM loss was **human error**, unrelated to the power cap. This causal claim appears
  nowhere in memory `project_3090_power_cap` and appears to originate in MANIFEST.
- The rig now has an **850 W PSU** — more margin. Memory `project_3090_power_cap` still records
  the Corsair 750 W and its own closing rule says the floor is re-derived, not assumed, on a PSU
  upgrade.
- **The cap prevents data loss, not equipment damage.** It exists so a mid-run reset doesn't kill
  a long unattended sweep. With a resumable runner writing its own `state.json`, a crash during
  E0 would have cost a restart. Running uncapped was correct and is not a deviation.

Memory `project_3090_power_cap` already carries the right framing (2026-07-17 doctrine change:
320 W default, crashes accepted, "crash-tolerance is a workload requirement, not a reason to
throttle"). **`LOCAL_LANE_CONTRACT_SPEC.md:175-180` never caught up** and still reads:

> "The 3090 must be power-capped before any sweep... if it reads above 200 W, **stop and ask the
> user**... (uncapped sustained load crashes the machine — marginal PSU)."

Under the heading "Hardware constraints (will bite you if ignored)." That stale gate is why E0
had to route around the spec and obtain an override twice. Left alone, the next agent asks a
third time.

## F5 — The pack has no ledger task, and per-cell records are mutated across sweeps

There is no task record for the pack. `operator task-list` shows no `front-e0` / routability
entry; only the 216 auto-created `eval-*` per-cell records exist. This review had to open one.

Those per-cell records carry no sweep or pack identifier. E0's events stacked onto July's records
— `eval-alias-add-L2-llama3.1-8b-t1` is now at **version 10**. The event stream preserves history,
but a current-state read returns E0 silently overwriting July, and the two sweeps are separable
only by timestamp.

## F6 — Raw model output is not captured

Records hold `detail`, `returncode`, `wall_clock_s`, `passed` — no transcript. The pass rates are
verifiable; what the model actually wrote is not recoverable. Adequate for a count, insufficient
if Front E later needs to say *why* a model failed. Same family as the gap the runner's own
docstring admits (tool-call count uncaptured). Not worth a re-run on its own.

---

## Recommended disposition — supervisor's call, not the consultant's

1. Rewrite MANIFEST §"Why this pack, why desktop" to the F3 reproduction claim; strike the z13
   premise and the F4 hardware paragraph.
2. Update `LOCAL_LANE_CONTRACT_SPEC.md:175-180` to data-loss framing; drop the stop-and-ask gate
   for resumable workloads.
3. Consolidate the pack — MANIFEST/RUN.md/tasks live on z13, RESULTS/state/sweep.log on desktop,
   untracked on both — then commit it whole.
4. Only then reconcile Front E in BN, as a reproduction result, **not** as routability evidence.
5. Open question for the operator: does Front E need a real routability instrument, given E0
   turned out to measure the harness rather than the routing question?
