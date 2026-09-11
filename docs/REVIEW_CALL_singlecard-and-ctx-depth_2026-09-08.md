# Review call: single-card comparison and configured context capacity

- **Status:** corrected draft; not issued or independently verified.
- **Proposed ledger task:** `singlecard-ctx-depth-2026-09-08`
- Historical measurement author: `claude`. Route review to a distinct, registered
  session-derived identity; do not infer verification from this document.
- **Separate review:** `REVIEW_CALL_gptoss120b-three-host_2026-09-07.md`
  remains pending. This packet neither verifies nor closes it.

## 1. Scope

The sweep varied **configured capacity (`num_ctx`)**, not prompt length. The
sweep recorded **12,837–12,838 actual prompt tokens** (two dual rows have 12,837). A 131,072-token capacity is not a
131,072-token prompt, nor evidence of throughput at the operator's reported
72,113-token median turn. That workload distribution needs separate review.

Observed: dual/solo decode is 61.4/11.2 = 5.48x at capacity 131072 with that approximately fixed-length
prompt. At capacity 16384 the solo-relative-to-dual differences are -8.0% (rank)
and -12.3% (sweep). These screen-tier observations do not establish a universal
null, a hardware purchase conclusion, or the cause of the large ratio.

## 2. Claim map (local labels, not ledger IDs)

| # | Type / status | Scoped claim | Verification route |
|---|---|---|---|
| C1 | numeric measurement | At `num_ctx=131072`, 12,838-token prompt, n=3: dual 61.4 and solo 11.2 tok/s; ratio 5.48x | Fixture arithmetic only; independent live confirmation pending |
| C2 | numeric measurement | At `num_ctx=16384`, `(solo/dual - 1)*100` is -8.0% in rank and -12.3% in sweep | Both fixture pairs; not a universal equivalence claim |
| C3 | numeric measurement | Solo prefill at capacities 16384/32768/65536 is about 0.872 ms/token within recorded 0.1-second precision; nominal headroom (24576 minus recorded VRAM) falls 5669 to 2339 MiB; the prior 1979 endpoint does not rederive | Rounded fixture values only; not exact equality or universal mechanism falsification |
| C4 | provisional inference | A proportional-VRAM layer estimate yields about 13 CPU layers and 5.5 ms/layer for 27b | Arithmetic diagnostic only; actual CPU-layer count and causal cost unverified |
| C5 | provisional explanation | Capacity-induced placement changes may explain the large ratio | Placement-captured controlled comparison required; no present mechanism or purchase verification |
| C6 | proposed standard component | Standard A (as-shipped settings) is appropriate for a stated operator-comparison question | Independent review of purpose and confounds; not established by fixture arithmetic |
| C7 | proposed standard component | A loaded-prompt regime is appropriate, with actual prompt length explicitly reported separately from capacity | Review workload provenance and representativeness; 12,838 tokens does not represent all interactive turns |
| C8 | proposed standard component | Single-card isolation and placement preconditions are adequate | Review daemon isolation, per-trial capture, and missing-evidence handling against the protocol below |

C6 replaces the old bundled C6 with C6–C8. C4 must not be silently omitted when
registering claims. Register using session-derived builder/reviewer IDs and retain
the returned ledger-ID mapping. No registration or verification is performed by
this document; the former executable block incorrectly attached an arithmetic
verifier to an explanatory claim and has been removed.

## 3. Verifier scope

```bash
python3 evals/local_lane_ladder/fixtures/ctx-sweep-27b-2026-09-08/verify.py
```

This checks local fixture consistency for C1–C3, reports C4's conditional
arithmetic, and checks the recorded solo-placement gap as **GAP1**, not C5.
It does not remeasure, attest fixture provenance, count CPU layers, validate
C5–C8, or produce independent ledger verification. Arithmetic tolerances are
checks against this stored dataset, not prospective acceptance bands.

## 4. Corrected confirmation protocol — prerequisite to a live run

1. Freeze the protocol, script revision, model digest/quantization, backend build,
   and claim-to-check mapping before launch. Review C6–C8 separately; do not use
   a passing arithmetic script as approval of the protocol.
2. Capacity experiment: hold the exact prompt fixed (retain text/hash and actual
   `prompt_eval_count`, target approximately 12,838; record and investigate any count variation), vary only `num_ctx` across the original
   four capacities and solo/dual placement arms. A prompt-length experiment is
   separate: vary tokenized input with explicit capacity headroom, no truncation,
   and no relabeling of capacity as prompt length.
3. Pin device UUIDs, daemon endpoints and effective CUDA/backend visibility;
   record parallelism, KV type, flash attention, sampling, output limit, power
   caps and thermal state. Prevent unrelated inference and retained-model
   contamination without interrupting another user's workload.
4. Capture placement **during each measured model residency** on both arms:
   daemon-specific load/offloaded N/M layer logs plus per-device `nvidia-smi`
   process/memory snapshots, timestamps and request identity. A solo daemon may
   not log to `journalctl -u ollama`; capture its actual log. `/api/ps` alone is
   insufficient given known reporting defects. Missing or mismatched placement
   invalidates causal confirmation; do not estimate layers from a VRAM ratio.
5. Predeclare repetition count, interleaving/randomization, warmup/cache policy,
   and uncertainty summary. Retain individual full-precision timings, prompt and
   generated counts, failures, load times and placement; do not keep only rounded
   medians. Use at least six measured repetitions per cell for confirmation;
   review whether observed variance warrants more before promoting conclusions.
6. Recompute rates and uncertainty before interpreting cause. Placement correlation
   supports but does not isolate CPU-layer cost: a cost estimate needs a controlled
   layer-placement sweep with other settings fixed, not division by inferred layers.

**Execution gate:** no live placement-captured confirmation until the corrected
protocol and its capture implementation are reviewed and ready. This correction
pass runs only the offline verifier. Live confirmation remains pending.

## 5. Reviewer questions

- Does the proposed residency mechanism survive direct placement evidence?
- Does the prefill result only weaken the tested headroom hypothesis, rather than
  establish a general mechanism?
- Is the four-percentage-point variation between the two low-capacity runs
  adequately reflected in confidence and future sample size?
- Which of C6–C8 are justified for which question, and what evidence is missing?

Historical benchmark claims and GOLD_STANDARD adoption are not retroactively
validated here. Reviewer routing and any hardware decision remain the operator's
call; no new GPU run or paid reviewer is launched by this packet.
