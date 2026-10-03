# One local-lane comparison field: inventory and gap plan

Status: inventory/planning only, 2026-10-01. No campaigns or deployment authorized
by this step. Combine the presentation, not samples from incompatible runs.

## Scope update — 2026-10-01, operator decision relayed at 19:15 UTC

**RTX 2080 + 16 GB-class host: Gemma26 ONLY.** Include this attainable-hardware
configuration in the comparison plan. Withdraw all proposed 2080 Bonsai,
Qwen27 and Qwen35 qualification/campaign work. This is the operator's practical
usefulness decision, not proof those models cannot execute. The reported
~$1,400+ current 3090 price is operator context, not independently verified
market data. No inference is authorized by this scope update.

Correction to the original inventory framing below: historical real-2080 Gemma26
runs already used approximately 15 GB host RAM; 32 GB was NOT a prerequisite.
The same-day September 5 comparison measured 31.02 tok/s on real2080 versus
31.55 on a 3090 capped with num_gpu=12 (7,416 versus 8,099 MiB GPU allocation).
The real2080 historical L2 state contains 15/15 passes. These are old-contract
measurements, not replacements for new common-battery cells. See
`fixtures/rtx2080-8gb-real/FINDING.md`, `testbench-2080-e9-batch1/state.json`,
and `moe-expert-residency-2026-09-12/FINDING.md`.

The later residency investigation showed GPU dense layers plus host-resident
mmap'd experts: 31/31 layers did NOT mean all weights on GPU. On the 15.9 GB
i9/2080, quiet cached execution measured 32.2–34.2 tok/s; an evicted phase with
Chrome resident measured 4.0–4.5 tok/s, heavy major faults and I/O wait with no
swap. Exact peak host working set is not established by those findings.

Latest read-only snapshot: approximately 7.9 GiB MemAvailable, no swap; RTX2080
8,192 MiB total, 7,424 MiB reported free, Chrome GPU use present; Ollama running
with no loaded models. Gemma26 is installed. Disk has about 21 GiB available.
These replace the earlier 4.4 GiB-available snapshot for planning, not a promise
of headroom at launch. No jobs were unloaded or system settings changed.

**Next proposed gate, only after approval:** recheck live headroom, then one
owned/private Gemma26 server at 16K, one slot, common sampler and no speculation.
Allow and label mixed placement. Capture actual CUDA backend, full weight and
auxiliary-blob identity, template/KV settings, expert fitting decisions,
attributed GPU allocation, host RSS/PSS, available RAM, major faults, I/O and
memory pressure. Do not use an API memory ratio or layer count as proof of
full residency. Use a bounded short-generation fit check with a timeout and
headroom stop policy; prefer a supported user-cgroup memory limit to protect
other desktop work. Leave user jobs, swap and caches untouched. Stop only owned
study processes. Follow with loaded-context qualification and separate repair
and native canaries; a short fit probe is not a scored decode result.

If qualified and separately authorized, the new Gemma26/2080 row needs the
common 90 repair cells (30 each L0/L1/L2), 36 native cells, and a separate
loaded-decode measurement. Preserve unproven/timeouts and host-pressure context;
do not silently shorten context or extend deadlines to manufacture completion.
This adds **one configuration / 126 scored cells** to the eight-row core plan,
not a four-model 2080 roster. Existing historical15/15 remains separately labelled
and is not pooled. Hardware usability is the point of this row, not GPU-only
purity. The 3090/Z13 run matrix below describes the original plan; subsequent
completion was verified separately, so do not relaunch it from this document.

## Later-window harness readiness — 2026-10-01

See `2080_GEMMA26_RUNBOOK.md` for the prepared Gemma26-only invocation and stop
criteria. Packet `fixtures/2080-gemma26-ready-20261001-r4` is prepared **without
inference**. Soft memory reclaim is disabled; an independently leased service
watchdog and proper local attributed placement capture are implemented and tested.
Live loaded-context qualification and 3 repair +6 native canaries still require
the later quiet window. No full campaign is authorized by harness preparation.

## Reader-facing draft

One table, grouped by hardware; no blended score and no rank number. Configuration
is part of each row, not a hidden footnote. A dash means **not measured under this
profile**, never zero. All new repair columns have /30; native tool-use has /36.
The differing denominators are between named tests, not unexplained differences
between models within a test.

| Hardware | Model / serving configuration | Repair L0 | L1 | L2 | Native tool use | Native median task s | Repair L2 median s | Loaded decode tok/s |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Testbench RTX 3090 | Qwen3.8 27B Q4 / Prism CUDA, F0 | 24/30 | 30/30 | 30/30 | 36/36 | 10.58 | 11.8 | 41.1 |
| Testbench RTX 3090 | Bonsai 2 27B PQ2 / Prism CUDA, F0 | 19/30 | 27/30 | 30/30 | 36/36 | 5.84 | 9.2 | 67.1 |
| Testbench RTX 3090 | Qwen3.6 35B / current seat weights, Ollama, proposed C1 | — | — | — | — | — | — | — |
| Testbench RTX 3090 | Gemma4 26B / Ollama, proposed C1 | — | — | — | — | — | — | — |
| Strix Halo 8050S | Qwen3.6 35B / Ollama, proposed C1 | — | — | — | — | — | — | — |
| Strix Halo 8050S | Qwen3.8 27B Q4 / Prism Vulkan, proposed F1 | — | — | — | — | — | — | — |
| Strix Halo 8050S | Bonsai 2 27B PQ2 / Prism Vulkan, proposed F1 | — | — | — | — | — | — | — |
| Strix Halo 8050S | Gemma4 26B / Ollama, proposed C1 | — | — | — | — | — | — | — |
| Desktop RTX 2080 + 16 GB-class RAM | Gemma4 26B / Ollama, mixed GPU/host experts; qualification pending | — | — | — | — | — | — | — |

The original eight core rows plus the scoped Gemma26/2080 row are not a proposal to publish empty rows as the
finished refresh. Fill the current-seat and Gemma rows next. Gemma4 31B is the
first optional additional contender on both hosts, including mixed placement.
An actual Ollama Qwen27 configuration can get its own bridge row; it must not
replace the populated Prism row or inherit its numbers.

Keep native totals (Qwen 6.50 min; Bonsai 4.08 min for 36 cells) and per-task
breakdowns in expandable row details. Retain all-level repair totals (27.88 versus
45.80 min for 90 cells) there too: a fast L2 median does not describe the whole
ladder. Unproven/timeout counts must remain visible when nonzero. Do not compute
one quality-times-speed score. Sort by hardware/model or a reader-selected metric,
not an invented overall winner.

## Existing cells that can populate the two F0 rows now

Repair source: `fixtures/standard-l012-20260930-r2/quality-<model>/results.json`.
Each row has 90 qualified records: five tasks x three levels x six trials.
Decode source: sibling `<model>-decode/results.json`, discard trial zero,
median of three measured 128-token completions at 12,811 actual prompt tokens.
Native source: `testbench:~/fusion-native-llama-20260930/quality-<model>/results.json`,
36 records per model; separate six-task canaries excluded. All 72 native cells
passed. No qualified-unproven scored cells in these two packets.

**Why the join is justified:** same model GGUF digests, same GPU UUID and Prism
CUDA archive, same controlled sampler/context/output profile. The columns still
name two DIFFERENT workloads/carriers: Pi coding-agent repair and native Fusion
v2 registry/tool use. Joining those measurements in a configuration row is not
pooling the 90 and 36 trials or pretending their timers measure identical work.

F0: Prism `prism-b10743-adfffbe` CUDA 12.8; temperature 0.7, top_p 0.8, top_k 20,
min_p 0, neutral penalties, seed 1234, 16,384 context, 4,096 output cap, thinking
and speculation off. Warm weights; erase conversation cache between cells;
allow prefix reuse within tasks; Pi compaction off. Native task loop: five turns.
Before/after process-attributed placement; this is not continuous residency proof.
Snapshot clocks can read 405 MHz while idle after hashing: do not use them as a
measurement of loaded bandwidth or claim a specific loaded clock from them.

GGUF identities:
- Qwen27: `f5f1dd8920d417aac2718b0bda3403da274301efdd6760b4f0f4b864ff2ad57d`.
- Bonsai: `3907dc1658db1f78a9826bf8d5bcb8dc65db0d466388937af57f2294fae62ec1`.
- Engine archive: `43b73a24d5cd83c4482750ee52e59afac497c669c008a319e44e43a0033757e2`.

C1 should retain the same tasks, trial counts and explicit quality sampler, while
recording Ollama version, full pin, model/projector blobs and daemon cache dtype.
It measures the **seat's weights at the controlled profile**, not its everyday
32K/speculative configuration. F1 is the same task contract on Vulkan, not an
assertion CUDA and Vulkan have identical execution characteristics. Capture KV
dtype, templates, backend flags, clocks/power and carrier versions explicitly.
If an adapter/fixture change alters measurement, use a new profile and a bridge,
not a retrospective claim that old cells were produced by the new code.

## Live hardware inventory and availability

Read-only checks performed 2026-10-01:

- **Testbench:** two RTX 3090s, each 24,576 MiB; GPU0 UUID
  `GPU-22b9dafe-e97d-dbb2-50ba-2f1f1dea61f9`, GPU1
  `GPU-102e9c9e-f883-58fa-6119-8c72f81fd88e`. Snapshot usage 61/21 MiB.
  About 31 GiB host RAM, 30 GiB available; 975 MiB swap, 282 MiB occupied.
  Ollama HTTP endpoints 11434/11435/11436/11437 report 0.32.12. The interactive
  shell name `ollama` was absent from noninteractive SSH PATH; the APIs work.
- **Current desktop with RTX 2080:** about 15 GiB host RAM, 4.4 GiB available,
  no swap in this snapshot. It is not a 32 GB spill host. Leave the old 2080 row
  explicitly historical. A new light/mixed configuration is not forbidden,
  but needs a real memory budget and a new row, not inheritance from the old
  headless i3 system. Do not rerun a 17–22 GB model on the assumption of 32 GB RAM.
- **Strix Halo/Z13:** `ssh z13` failed resolving `z13.local` during this inventory.
  That is a reachability/DNS failure, not evidence the model cannot run. Current
  RAM, storage, AC/power profile, runtime and installed weights are unverified.
  Last verified Bonsai study used the 8050S, 4 GiB carve-out plus GTT; last
  inspected /home was 95% full. Recheck before copying model files or launching.

**Mixed placement stays eligible.** Record the executing device(s), attributed
GPU allocation, CPU/expert placement where available, host RAM/pressure and
swap/page-fault telemetry. Label mixed explicitly; do not require >=90% weight
allocation as a universal admission rule. Refuse wrong-host/wrong-process or
missing evidence, not legitimate CPU offload. UMA GTT is not discrete GPU spill.
No clearing someone else's workload or privileged clock/service changes is
included in this inventory authorization.

## Installed contenders and identity traps

Testbench API inventory confirms current tags:

| Model | Tag digest | Main weight blob from /api/show | Config fact |
|---|---|---|---|
| Qwen3.6 35B | `096fdbd02fe620fc10cbeb6537e080f8041aece851e5d696aed024d4f70f2e47` | `d372de8e934898a59e6ccfabc3368474711384d8f1fd4d22d87a3f0a45400cdc` | Auxiliary blob present; shipped draft_num_predict=2, temperature=1, presence_penalty=1.5 |
| Qwen3.8 27B | `22130167c4c20e20c7b71454612966ca8e8171e9b3cc8ab6ce8aa6cbfec79643` | `f5f1dd8920d417aac2718b0bda3403da274301efdd6760b4f0f4b864ff2ad57d` | Auxiliary blob present; shipped draft=4; Prism F0 used main GGUF without projector |
| Gemma4 26B | `08ae7ec1744bd7f451c4a530afb39d2673ad9d07a8369b8a33a3613b41212a68` | `dfd98d2734212d0c128e128e5d88edac764aaa4f4af2f4c196941f2354aab8da` | Auxiliary blob present; shipped draft=3, top_k=64 |
| Gemma4 31B | `6316f0629137b426c9d9b853ffc4c8209589f30ee39aebede6285096c0ff47e7` | `280af6832eca23cb322c4dcc65edfea98a21b8f8ab07dc7553bd6f7e6e7a3313` | Installed Q4_K_M contender; fit/performance not yet qualified for this packet |

There is ALSO a working official Qwen35 GGUF at
`testbench:~/q36/Qwen3.6-35B-A3B-Q4_K_M.gguf`, 20,419,565,568 bytes, digest
`671e47e0ec53c665d048b98c3ecbfd5236b5ca9c3e02ed19fc8f81f7b85140c7`.
The simulated-3060 branch already ran it in Prism with experts on CPU. Thus the
old Z13 Ollama-blob/fork load failure does NOT mean no Qwen35 can run in Prism.
But this alternate GGUF is not the current Ollama seat's weight blob. It needs
its own configuration row; do not silently use it to fill the current-seat row.
No fresh model load was attempted in this inventory.

## Existing work to preserve, not rerun blindly or import into F0

| Packet / primary evidence inspected | Existing measurements | Why not fill the new profile's blanks with them |
|---|---|---|
| `fixtures/pinned-l2-20260929` | Qwen35 29/30 L2; Nemotron30/30; Next Instruct27/30; Thinking29/30 | Dual-card cohort, 0.8/0.95 A versus different B; placement preflight only; no L0/L1/native under C1 |
| `fixtures/bonsai-l2-20260929` | Qwen27 30/30; Bonsai28/30, two context-exhausting CSV loops | No explicit per-cell cache reset/placement; preserve separately, no adding its 30 to F0 |
| `fixtures/sim3060-l2-20260929` | Recounted Qwen35 alternate Q4 cap12:30/30, median16.35s; Bonsai27/30+3unproven, median10.7s | 3090 clock5001MHz, memory ceiling11,500MiB, Qwen -ncmoe22/-t4; not stock3090, not real3060, different Qwen weights. Preserve as mixed-placement branch; no pooling its loop rates with the other cohort |
| `testbench:~/screening-campaign-20260926T200055Z` | Raw quality-L1: Qwen35 18/18, Qwen27 18/18, Gemma26 14/18. Separate L2 wall legs | Three tasks, old0.8/as-shipped defaults, different carrier/build/cache regime. Do not convert to /30 or treat scope/truncation exclusions as demonstrated correct answers |
| `testbench:~/l0-n16-20260927T044354Z` | Raw L0 Qwen35 32/48, Qwen27 42/48, Gemma26 21/48 | Three tasks x16, different regime. Valuable higher-n historical quality evidence, not five-task C1 cells |
| `testbench:~/native-fusion-l3-v2-matrix-20260921T2220Z` plus reconciliation directory | 18/18 reconciled for Qwen35/Qwen27/Gemma26; three trials per task | Native Ollama, old0.8/defaults and fixture binding/proof differences; no appending 18 new trials to reach36 under changed settings |
| Z13 historical E9 and Fusion pointers in dashboard registry | Reported native18/18,18/18,16/18; various three-task E9 results | Not independently re-opened this turn because Z13 is unreachable; preserve as historical pointers, not current verified cells |
| `BONSAI-Z13-001` | Vulkan microbench/deep-context fit and later Ollama32K correction | Not repair/native quality. Different depth/engine/probe types; do not insert23.3/18.7 into the new loaded12.8K decode column |

Raw state counts above were read directly, not taken solely from the dashboard.
For historical Fusion, inspected `RECONCILED_RESULT.json` and recounted original
trace timings: Qwen35 mean **7.1347s**, Qwen27 **12.9309s**, Gemma26 **6.2261s**.
The dashboard currently labels Qwen35's mean **6.23s**, apparently borrowing
Gemma's value. Flag this transcription error; it is not a reason to rerun models.
No dashboard source or historical result was modified by this inventory.

## Minimal run matrix and priorities

Reuse the two complete F0 rows. Do NOT rerun all 252 scored cells simply because
the page now has one table. New rows require these missing blocks:

| Priority | Hardware/configurations | Missing scored blocks | Additional qualification |
|---|---|---:|---|
| P0 | Restore/verify Z13 connectivity; inventory both hosts; freeze C1/F1 contracts | 0 | No inference needed for metadata; sampler/transport, explicit fixture binding and mixed/UMA placement adapters need model-free tests before a canary |
| P1 | 3090 Qwen35 current weights/Ollama + Gemma26/Ollama | 2 x (90 repair +36 native) = **252** | Each: 3 repair +6 native canaries, separate loaded-decode warmup+3. No assumption the existing Prism-only launcher works unchanged |
| P2 | Z13 Qwen35/Ollama, Qwen27/Prism Vulkan, Bonsai/Prism Vulkan, Gemma26/Ollama | 4 x126 = **504** | Same task/profile discipline; native tool/data stack must execute on Z13; verify power and host-memory state; no full-residency rule |
| P3 optional | Gemma31 on both hosts | 2 x126 = **252** | Mixed placement allowed and labelled; measured memory/timeout feasibility first |
| Bridge optional | 3090 Qwen27/Ollama, if we want a direct engine comparison instead of labelled config rows | **126** | Same weight blob alone is not enough: projector/template/KV/speculation and cache policy must be declared. A brief canary is routing validation, not a quality equivalence test |

Core completion: **six new configurations, 756 scored cells**, plus **54 canary
cells** and **24 decode calls** (six discarded warmups +18 measured calls).
No inferential comparison requires a blended score. If a model legitimately
cannot complete the declared context/output contract on the available host,
show a bounded failed/ineligible configuration with cause, not a smaller hidden
context/denominator. Do not reject it merely for mixed execution.

Cheap timing/routing anchors on an existing F0 control can detect environment
changes before new work; they are separate qualification observations, not extra
samples silently appended to old scores. If input semantics change, a real
bridge/new-version decision replaces automatic reuse.

## Runtime and scheduling

The completed two-model repair packet took **236.0 minutes elapsed**, while its
actual task timers totalled **73.68 minutes**. Native Fusion took **83.22 minutes
elapsed**, while native task timers totalled **10.57 minutes**. Rehashing whole
GGUFs before/after each cell dominates much of the difference. Do not promise
new-seat completion from tok/s alone.

At the unchanged verification cadence, even the two new3090 rows should be
budgeted as a multi-hour block, not a quick L2 refresh. Z13 runtime cannot be
estimated responsibly until reachable and canaries have measured it; keep a
per-cell600s safety limit and explicit stop conditions. No whole-roster ETA from
old host timing multipliers.

A separately tested optimization could hash immutable/owned model files once per
load and check file identity/metadata plus daemon lineage each cell, rehashing on
change; this weakens mutation detection unless immutability is actually enforced.
Do not silently remove the current identity gate mid-campaign just to improve ETA.

Current validators reject significant unrelated compute on either card, so
parallel GPU0/GPU1 campaigns are NOT ready merely because two3090s exist. Serial
execution is the validated baseline. Any two-seat scheduler must scope process
ownership per card and log shared CPU/RAM/I/O pressure. No new scheduler or long
run is authorized by this planning step.

## Next decision

Approve the eight-row core and whether controlled current-seat/Ollama rows are
preferred over alternate-GGUF Prism rows. The recommendation is to include the
actual seat weights first, with runtime plainly labelled, keep the alternate
Qwen35 cap study as historical/config-specific evidence, and run P1 before P2.
No website edit, publication, model download, server start, inference, commit or
push was performed for this inventory.
