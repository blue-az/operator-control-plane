# Retoolable Factory Roadmap

**Status: draft.** Companion to
`owners-manual/pbc/appendix-retoolable-research-factory.pbc.md` (also draft).
Written 2026-09-14. Every date below is proposed and owned by the operator.

Governing idea: run the pilots first, extract the spine from what they actually
needed, and ask the product question last.

## Window

90 days: **2026-09-14 to 2026-12-13.** Phases 0-5 fit inside it. Phase 6 is a
dated review after it, with criteria written now (see Phase 6).

| phase | proposed window | weeks |
|---|---|---|
| 0 - Pilot baseline | Sep 14 - Sep 20 | 1 |
| 1 - PPR Data Atlas pilot | Sep 21 - Oct 18 | 2-5 |
| 2 - GPU measurement pilot | Oct 5 - Nov 1 | 4-7 |
| 3 - Extract the spine | Nov 2 - Nov 15 | 8-9 |
| 4 - Adapter infrastructure | Nov 16 - Nov 29 | 10-11 |
| 5 - Longitudinal collection begins | Nov 30 - Dec 13 | 12-13 |
| Day-90 checkpoint | Dec 13 | - |
| 6 - Product-value review | proposed 2027-03-13 | - |

Phases 1 and 2 overlap on purpose. They share no substrate and no hardware.
The binding constraint is operator review attention, so Phase 2 starts once
Phase 1 is in worker execution, not waiting on a human decision. If review
attention runs short, serialize them and record that as the reason.

## Standing requirement: deviation log

Every pilot keeps a deviation log from its first day, attached to its ledger
task as evidence. Phase 3 is built from these logs, not from recollection or
chat recaps.

One row per event:

```text
date | pilot | rule or gate id | followed / bent / skipped / added | why | cost impact
```

Each pilot also records its total cost at exit: wall-clock time, model tokens
or spend, and operator review time.

## Execution tiers

Probe, Study, and Change are defined once, in the PBC section "Pilot Execution
Tiers". Phases 1-2 record a tier and reason per task; Phase 3 revises the
definitions from the deviation logs. This roadmap does not restate them.

---

### Phase 0 - Establish the pilot baseline

Goal: avoid designing ahead of evidence.

- Keep the PBC explicitly draft.
- Use existing Operator task/claim/evidence lifecycle.
- Record chosen execution tier per task, using the tiers defined in the PBC.
- Freeze authority boundaries and terminology **per pilot**, not globally.
  Global terms are a Phase 3 output.
- Start the deviation log for both pilots.
- Clear the known PBC defects (review of 2026-09-12):
  - `pbc_lint.py` fails: move RRF rules from `pbc:rules` to `pbc:proposed-rules`.
  - Create the ledger task and frozen claim the proposed fences must reach
    (lint invariant 2, `--ledger .operator`).
  - Replace the nonexistent `op` command with `./operator`.
  - RRF-RUL-009: invalidate on missing, unlogged, or misreported placement
    evidence, not on mixed placement.
  - Narrow the "repeated trials" non-goal to re-rolling for a different
    verdict, so it stops contradicting reruns, n>1 trials, and longitudinal work.
  - Replace `pbc:gates` (unrecognized fence kind) or register it.

Exit: both pilots have defined tasks, substrates, outputs, and acceptance
checks; tiers are recorded; deviation logs exist; `pbc_lint.py --ledger
.operator` passes on the factory PBC.

---

### Phase 1 - Run the PPR Data Atlas pilot

Tier: Change. Ledger task: `ppr-data-atlas-v1`. Supervisor packet:
`/home/blueaz/Python/ppr-agent/deliver/ppr-data-atlas-v1-supervisor-packet.md`.

- Run the audit under the control-plane task.
- Use identical independent workers.
- Produce evidence ledgers and handoffs.
- Reconcile worker differences.
- Make only human-approved changes. Public deployment stays frozen until then.
- Keep the deviation log.

Exit: one complete example of specification -> implementation -> evidence ->
reconciliation -> human decision, plus the deviation log and cost record.

---

### Phase 2 - Complete the GPU measurement pilot

Tier: Study. Ledger task: `offload-curve-moe-residency`.

**Host boundary.** The original offload curve (~1.34 ms per CPU-resident layer,
`gemma4:26b`) was measured with the RTX 3090s behind the i9 desktop, before the
cards moved. As of 2026-09-11/12 the 3090s are on the i3-9100F testbench and the
desktop runs an RTX 2080. The i9 + 3090 condition cannot be retaken. This pilot
is therefore a new study on a new host, not a continuation:

- Version the protocol at the host change. Do not average across it.
- Run the whole pilot on one host. If the host changes mid-pilot, the pilot
  splits into two studies.

Work:

- Finish the MoE offload analysis.
- Capture placement, host RAM, page cache, faults, I/O, and timing.
- **Control host memory state, don't just capture it.** Define a host-state
  precondition (free RAM floor, no competing resident processes, page cache
  state) that is checked before each run. A run that misses it is recorded as
  invalid with a structured cause. Basis: at identical placement, decode swung
  from 32-34 tok/s to 4.0-4.5 tok/s on page-cache eviction alone
  (`evals/local_lane_ladder/fixtures/moe-expert-residency-2026-09-12/FINDING.md`).
- Convert discovered instrument faults into checks.
- Do not require two workers unless the adapter justifies it.
- Separate observed curves from generalized claims.
- Keep the deviation log.

Known instrument faults to seed the checks with:

| fault | source |
|---|---|
| `offloaded N/N layers to GPU` counts layers, not MoE experts; reads as full residency while experts sit in system RAM | `fixtures/moe-expert-residency-2026-09-12/FINDING.md` |
| Page-cache eviction changes decode ~8x at identical placement, with `si=0` (not swap) | same |
| `RESULTS.md` producer label names the runner host, not the inference host, when `:11434` is an SSH tunnel | `fixtures/testbench-parity-gated-20260912/PROVENANCE.md` |

Exit: one reproducible research study with valid and invalid runs preserved.
"Reproducible" means a rerun under the same protocol version and host-state
precondition lands within a tolerance stated before the rerun.

---

### Phase 3 - Extract the actual factory spine

Only after Phases 1 and 2. Input is the two deviation logs and cost records.

- compare what both pilots truly needed;
- remove rules that only belonged to one adapter;
- retain common lifecycle conventions;
- formalize the minimal adapter contract;
- revise the draft PBC;
- add tiered execution and stop rules based on experience;
- check that nothing in the spine duplicates an existing ledger record type
  (`docs/PROPOSAL_LIFECYCLE.md` section 5).

Exit: evidence-backed v1 factory contract, ratified by the operator.

---

### Phase 4 - Build adapter infrastructure

Create a small adapter registry: a directory of adapter files in this repo,
not a service. Each adapter declares:

```text
  adapter ID
  authority substrate
  runner/tools
  brief format
  evidence schema and status vocabulary
  known instrument faults
  acceptance checks
  execution tier and worker count
  host-state preconditions (where applicable)
  stop conditions
```

Initial adapters:

```text
  ppr-data-atlas
  local-inference-placement
```

Possible later adapters:

```text
  software change
  document/research extraction
  data-quality audit
  visual/public-surface review
```

**Holdout adapter.** The two pilot adapters produced the spine, so they cannot
also prove it transfers. Pick the smallest adapter from the "later" list,
one that played no part in Phase 3, and build it against the ratified spine.

Exit: the holdout adapter runs one task end to end without any change to the
factory spine. If the spine has to change, record why and return to Phase 3
for that rule.

---

### Phase 5 - Begin longitudinal research collection

For the GPU adapter:

- schedule bounded studies;
- retain raw telemetry;
- record model/runtime/hardware digests;
- capture host memory state, and enforce the Phase 2 precondition;
- preserve failed and invalid runs;
- version every protocol, including at every host or hardware change;
- publish only reviewed summaries.

**Hardware continuity.** The second RTX 3090 was bought on a sell-if-no-revenue
basis with no date or dollar threshold. A longitudinal series needs host
continuity. Before Phase 5 starts, either:

- set the sell decision date at or after the Phase 6 review, or
- scope the collection to hardware that is certain to stay (single 3090, or
  the 2080 desktop).

Operator decision: sell-decision date `____`, revenue threshold `____`.

Exit (at day 90): scheduled collection is running and producing a growing,
provenance-rich dataset rather than isolated benchmark anecdotes.

---

### Phase 6 - Evaluate whether it has product value

Proposed review date: **2027-03-13** (about three months of collection).

Assess:

- what measurements are unique;
- which findings replicate, **across hosts** (2080 desktop and 3090 testbench
  are two independent hosts after the move, not repeats on one machine);
- whether users make better placement decisions;
- whether the data supports consulting, reports, or tooling;
- whether the dataset is valuable enough to expose externally.

The product question comes after evidence accumulation, not before. **The
criteria come before the evidence**, so sunk cost does not write them.
Proposed starting criteria, to be set by the operator in Phase 0:

Continue if at least two hold:

- at least one finding replicates across both hosts;
- at least one instrument-fault check automatically invalidated a run that
  would otherwise have been accepted;
- at least one external demand signal (consulting conversation, inbound
  request, cited use of a published summary);
- cost per study fell between the first and last scheduled studies.

Stop or shrink to a personal tool if none hold, or if the second 3090 sell
condition has triggered with no dataset-driven revenue.

---

## Immediate order

```text
  1. Clear Phase 0 (PBC lint, ledger claim, tiers, deviation logs)
  2. Run PPR Atlas pilot
  3. Run MoE offload pilot on the testbench (overlapping, one host)
  4. Reconcile both pilot experiences from the deviation logs
  5. Revise and ratify the factory PBC
  6. Add the adapter registry and prove it with a holdout adapter
  7. Start controlled longitudinal collection
  8. Phase 6 review on the date and criteria set in Phase 0
```
