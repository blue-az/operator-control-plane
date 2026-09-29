# Qwen3-Next / Nemotron dual-card L2 retest — takeover audit

**Mode:** retrospective artifact audit, not a new benchmark or stress run.
**Scope/stop criterion:** reconcile the completed A/B states with all 120 saved
traces; execute the five untouched fixture baselines in disposable directories;
check the August comparator's provenance; recompute selected hardware tables.
No inference, live-ledger mutation, service/model configuration change, or
publication is part of this audit. Crystals remain ignored, uncommitted context,
not the authority for the results below. Original states/traces/reports are kept
unchanged.

## 1. Group B has finished

`run.log` ends with `GROUP_B_DONE 00:02:57Z` (following the September 28 evening
run). `state_A.json` contains 90 completed cells; `state_B.json` contains 30.
All 120 result records agree with their corresponding traces on task, level,
model, trial, pass flag, outcome, and proof flags. No duplicate cell keys or
state/done mismatches were found.

These are the **recorded grader outcomes**, not controlled cross-model rankings:

| Seat | Recorded passes | Unproven | Excluding the pre-solved booking task |
|---|---:|---:|---|
| Nemotron Lightning, thinking off | 30/30 | 0 | 24 passes / 24 cells |
| Qwen3.6 35B control, thinking off | 30/30 | 0 | 24 passes / 24 cells |
| Qwen3-Next Instruct, thinking off | 26/30 | 4 | 20 passes + 4 unproven / 24 cells |
| Qwen3-Next Thinking, thinking on | 26/30 | 4 | 20 passes + 4 unproven / 24 cells |

The last column is a descriptive exclusion, **not a newly validated score**.

Per-task profiles, in order Nemotron / control / Instruct / Thinking:

- ambiguous-anchor: 6 / 6 / 6 / 6 passes of six each.
- booking-off-by-one: 6 / 6 / 6 / 6, but all start solved; exclude as repair evidence.
- constant-and-callers: 6 / 6 / 6 / 5; Thinking trial 2 is unproven
  (`dispatch`, `placement`).
- csv-summarize-repair: 6 / 6 / 5 / 3; Instruct trial 1 is unproven
  (`placement`); Thinking trials 1, 2, and 5 time out at approximately 600 s.
- strict-log-format: 6 / 6 / 3 / 6; Instruct trials 1, 4, and 6 are unproven
  (`placement`).

Thus the crystal's **20/24 in-progress Thinking result** is superseded by the
completed 26-pass/4-unproven record. There are **three**, not two, final Thinking
CSV timeouts. Unproven cells must not be called confirmed model failures.

## 2. Newly reproduced instrument defect: the booking fixture starts solved

The run revision is `2b63be163ff5e2a3514f83331ccd64f23bd3f06a`, recorded in
`evidence/prerun.txt`. Its `tasks/booking_off_by_one.yaml` seeds:

```python
return start1 < end2 and start2 < end1
```

But its L2 prompt still instructs the model to replace the buggy `<=` expression.
Commit **`617c652adea98d94d20eebbfb1d0bfc94fb196c2`**, September 15, changed the
fixture from `<=` to `<`, thereby putting the answer in the initial substrate.
This is committed source state, not contamination inferred from a final score.

Independent checks in this audit:

1. **24/24 booking traces** show the already-correct expression in the first
   `read` result for `src/bookings.py`.
2. All 24 booking records have `attempted_edit: false`.
3. Reconstructing the untouched fixture from the recorded run revision and
   calling the actual deterministic grader returns **all 3 checks passed**,
   without invoking any model.
4. Restoring `<=` in a disposable copy makes the boundary battery fail.
5. The other four untouched fixtures from the same revision fail their graders
   as intended.

These 24 passes show checking already-correct code, not repairing the advertised
bug. Do not silently edit the archived results to make the battery look clean.
Repair the source fixture and add an initial-state failure gate before rerunning.

## 3. The comparison with August is not a controlled configuration ablation

The older `qnext-80b-e9-ceiling/traces/` recount gives Qwen3-Next **10/30** and
Qwen3.6 **27B** **20/30**, at revision
`3e495641589fe445c72a359f38e5d03401ec4185`.

Unlike the crystal's “every ladder run dispatched through Pi” wording, those
August traces actually invoke **`opr`**, with `--think off`, `--num-ctx 16384`,
`--temperature 0.8`, and the old continuation controls. September invokes Pi.
The August booking source still contains the intended bug. Parsed task files,
prompts, and postconditions match for the other four tasks; booking's initial
file differs. Excluding booking, August Qwen3-Next recorded 8 passes / 24 cells,
but the carrier and configuration differences still prevent causal attribution.

The documented Thinking/Instruct identity mismatch is a legitimate configuration
concern. Historical argv confirms thinking-off dispatch. However:

- Instruct is a different weight variant, not the same model with one flag fixed.
- Thinking-on also changes context (16k to 32k) and temperature (0.8 to 0.6).
- `prerun.txt` confirms unequal sampler settings across all four seats: Instruct
  top_p 0.8 vs 0.95, control presence_penalty 1.5, absent vs explicit top_k, etc.
- The comparator is 35B now, not August's 27B.
- The run artifacts do not independently bind August's mutable `latest` tag to
  the digest identified in September's `QWEN3NEXT-VARIANT-001` narrative.

The defensible conclusion is **better observed task outcomes under changed
variant/configuration/carrier conditions**, not “thinking off caused the entire
10/30” or a fair Nemotron-versus-Qwen ranking. Vendor support for the documented
variant behavior was not independently fetched in this audit.

## 4. Placement evidence is absent in this retest

**120/120 records have `proofs.placement: false`; placement evidence is null.**
`run.sh` passes neither a placement profile nor a residency requirement. It also
sets `LOCAL_LANE_SKIP_PIN=1`; parameter snapshots document differences, but do
not enforce a complete pin.

The runner deliberately accepts grader passes despite missing proof flags and
labels nonpasses unproven when proofs are missing (`classify_outcome`). This
explains the asymmetry; it is not a counting error. Preserve that historical
semantics, but do not describe this packet as placement-validated dual-card
capability evidence. A prospective remote dual-card placement gate must inspect
the serving testbench, not the desktop tunnel process. The supplemental direct
Ollama throughput probe is not task-completion speed.

## 5. Hardware audit: arithmetic mostly reproduces; some wording is too broad

The optional hardware audit recomputes existing TSV/JSONL data under
`/home/blueaz/Python/project-phoenix/docs/domain_runs/`. It does **not** repeat GPU
runs or independently validate every raw device/daemon observation.

Reproduced from the saved tables:

- Qwen3-Next single/pair: **25.6433 → 72.6033 tok/s**, about **+183.1%** from the
  unrounded saved values (the report says +184%).
- Filled 31B at ~118k: **1.205 → 17.665 tok/s**, about **14.66×**; two-card decode
  at ~185k is **13.725 tok/s**.
- Forced-spread 26B decode losses are about **51.5–70.8%**.
- Nemotron two-card decode is **87.98 tok/s** near 1k and **75.37 tok/s** near
  115k. Its saved one-to-two-card gains span about **49–73%** across the paired
  lengths, rather than uniformly +55–60%; one-card measurements are noisy.
- The preloaded starvation JSONL records contain **158.9 s** and **938.7/938.8 s**
  long completions. The saved empty-start files contain **seven bursts** (six
  gemma plus one qwen), all completing within 83 s. “0/6” is the gemma-only
  denominator, not all saved empty-start bursts. “3/4 preloaded” includes the
  earlier manually stopped morning observation, not four completed trigger runs.
- The card comparison reproduces means of **36.1933/34.5**, **79.4533/69.9656**,
  and **199.63/179.84 tok/s** for GPU0/GPU1.

**Causal limitation:** the cross-model speed pattern challenges the proposed
*fixed per-token link-overhead* explanation. It does not, by itself, prove that
PCIe width contributes nothing or that the difference is intrinsic to the card.
Card, slot, and thermal conditions remain coupled without a controlled card/slot
or link-width intervention. Keep the measured GPU0 preference; narrow the causal
wording.

The approved `LOCAL_INFERENCE_DUAL_CARD_REPORT.md` still calls Qwen3-Next the
“weakest model” and says two cards “do not make it a good seat.” That paragraph
needs an explicit correction incorporating the changed configuration and
instrument evidence. This audit does not silently rewrite the approved report.

## 6. Takeover order

1. **Group B completion/recount: done.** Preserve the completed packet and this
   audit; do not restart it as though the last six cells were missing.
2. Repair the booking initial state and add a fail-closed baseline gate for
   repair tasks. Retain a check that known fixes pass, so an always-failing
   grader cannot satisfy the baseline requirement by accident.
3. Define the full sampler contract and named variant/context/thinking profiles;
   verify model digests, effective request settings, provider routing, and remote
   placement before dispatch. Identical parameters and per-model recommended
   parameters answer different questions; predeclare which comparison is wanted.
4. Freeze a corrected task/runner/config manifest. Keep a comparable same-run
   control. Set timeout/context budgets up front and report censored/unproven
   cells separately, per task first.
5. Only then authorize a new comparison run. No new benchmark, sampler-tag
   rebuild, deployment, or live service/config change was made during this audit.

## Reproduce this audit (no inference)

From the Operator repository:

```bash
python3 evals/local_lane_ladder/fixtures/qnext-nemotron-dual-l2-20260928/audit_results.py \
  --hardware-root /home/blueaz/Python/project-phoenix/docs/domain_runs
```

The captured output is `evidence/takeover-audit.json`, including source hashes,
state/trace checks, untouched-fixture grade results, and hardware aggregates.
Re-execution creates only disposable fixture directories and prints JSON; grader
tracebacks contain their temporary paths and therefore are not byte-stable.
