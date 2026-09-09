# Supervisor review call: the single-card null, the 5.5x at depth, and whether the standard now holds

- **Status:** drafted, not yet issued. Reviewer routing unresolved, see section 5.
- **Proposed ledger task:** `singlecard-ctx-depth-2026-09-08`
- **Author:** `claude` (builder on this work. This is a request for independent
  verification, not a self-verification.)
- **Repo:** `~/operator-control-plane`, branch `master`, uncommitted
- **Verify command:**
  `python3 evals/local_lane_ladder/fixtures/ctx-sweep-27b-2026-09-08/verify.py`
  Fail-closed, exits non-zero on any claim that does not re-derive. **It re-derives
  from committed fixtures, it does not re-measure.** Live reproduction is ~25
  minutes and needs the solo daemon per `GOLD_STANDARD.md` 2b.2.

## 1. Central question for the reviewer

Two results landed today that point opposite directions, and the program has
adopted a standard on the strength of them.

Splitting a model across two cards does **nothing** for decode while it fits one
card (-8.0% to +6.7% across four models). The same comparison on the same model at
a different context depth is **5.5x**. Both are real. The reconciliation offered is
that the second card is not a throughput device but a residency device.

> **Is that reconciliation sound, or is it a story fitted to two measurements
> that were taken for different reasons?**

The builder's position is that it holds because the mechanism is independent of
the data: decode walks layers sequentially, so two cards never contribute
bandwidth simultaneously, and the only thing that changes at depth is whether the
model is resident at all. **That is the claim most worth attacking**, because
`GOLD_STANDARD.md` 2b, 2b.1 and 2b.2 were written on the back of it and now govern
every future measurement in this program.

## 2. Claims to register

| # | Type | Claim | Falsifier |
|---|---|---|---|
| C1 | `numeric_measurement` | `qwen3.8:27b` at ctx131072, loaded regime: dual 61.4 tok/s, solo 11.2, a 5.48x ratio | Ratio outside 5.3-5.7 on re-measurement |
| C2 | `numeric_measurement` | The same comparison at ctx16384 is small and negative: -8.0% and -12.3% across two independent runs | A run outside -13% to -7% |
| C3 | `numeric_measurement` | Solo prefill is flat at 0.872 ms/token across ctx16384, 32768 and 65536 while headroom falls 5,669 to 1,979 MiB | Any depth differing by more than 0.02 ms/token |
| C4 | `numeric_measurement` | Spill costs 27b ~5.5 ms per CPU-resident layer against 1.34 ms measured on `gemma4:26b` | Per-layer cost outside 4.0-7.0 ms |
| C5 | `paper_or_report_claim` | The second RTX 3090 is justified by keeping the seat model resident at the operator's context depth, not by decode throughput and not by capacity for large models | See section 3, this is the contested one |
| C6 | `paper_or_report_claim` | Standard A, the loaded regime, and the four single-card preconditions are the correct measurement standard for this program | Any precondition shown unnecessary, or a necessary one missing |

C1-C4 are mechanical and covered by the verify script. **C5 and C6 are inferences
and are not covered by anything.** They are the reason for the review.

## 3. What the builder wants attacked

In the order I think they are most likely to break.

1. **C4's layer count is inferred, not measured.** The ~13 CPU-resident layers
   come from dividing a VRAM shortfall by total VRAM. Nothing counted layers,
   because the solo arm records `layers: None` -- `layers()` parsed
   `journalctl -u ollama` and the solo daemon does not run under that unit. Fixed
   after the fact by adding `placement()`, which was **not** in the instrument when
   these numbers were taken. **This is the weakest link.**
2. **C3 is flat within the recorded precision, not measured identical.**
   `prompt_s_median` is stored rounded to one decimal. All three depths recorded
   11.2 s, so "0.872 / 0.872 / 0.872" is an artifact of rounding as much as a
   result. The falsification of the headroom hypothesis survives at that precision,
   but the phrase "dead flat" in the fixture FINDING overstates what was captured.
3. **C1 is n=1 configuration.** One model, one depth, one pair of arms, n=3 reps.
   Per `GOLD_STANDARD.md` 2a this is Screen tier, and a 5.5x headline is being
   drawn from it and used in a hardware purchase decision.
4. **C2's two runs disagree by four points** (-8.0% and -12.3%) on the same
   configuration hours apart. That is the honest reproducibility signal for this
   rig and it is larger than several effects this program has reported as findings.
5. **C5 may be unfalsifiable as stated.** "Residency device, not throughput
   device" fits both observations, but so would "the effect is large when the model
   does not fit and small when it does," which is a description rather than a
   mechanism. A reviewer should ask what measurement would distinguish them.
6. **C6 adopts a standard on one night's evidence.** 2b.1 declares the loaded
   regime on the strength of a 293-turn context distribution measured by a
   different session, which I did not verify beyond reading its stated source.
   2b.2 condition 3 generalises from one model at two depths.
7. **The builder's error record on this work.** Tonight I attributed a model to a
   third party from a marketing page, put two scoring scales in one table, proposed
   two pinned daemons without the `cuda_v13` requirement that would have made
   "solo" mean two cards, and wrote a correction into `HANDOFF_2026-09-06.md` that
   inverted the wall-clock arms and had to be withdrawn by a later session. Weight
   the confidence in sections 1 and 2 accordingly.
8. **The handoff is not readable top-down.** It is now ~800 lines with seven
   correction and finding sections appended, and line 77 still states a superseded
   comparison. A reviewer starting at the top gets the wrong instruction before
   reaching any correction.

## 4. Commands to issue the call

```bash
cd ~/operator-control-plane

./operator task-create \
  --id singlecard-ctx-depth-2026-09-08 \
  --objective "Verify that dual-card splitting is neutral for decode while a model fits one card and worth 5.5x when it does not, and confirm the measurement standard adopted on that basis." \
  --assign claude \
  --review "<REVIEWER -- see section 5>" \
  --assumption "The ~13 CPU-resident layers in C4 are inferred from a VRAM shortfall; the instrument did not capture placement on the solo arm at measurement time." \
  --assumption "prompt_s_median is stored rounded to 0.1s, so C3 is flat within recorded precision rather than measured identical." \
  --assumption "C1 is one model at one depth, n=3. Screen tier per GOLD_STANDARD.md 2a."

./operator claim-add -t numeric_measurement --task singlecard-ctx-depth-2026-09-08 \
  -x "qwen3.8:27b at ctx131072 loaded: dual 61.4 tok/s vs solo 11.2, a 5.48x ratio" \
  --gate evals/local_lane_ladder/fixtures/ctx-sweep-27b-2026-09-08/FINDING.md \
  --verify-cmd "python3 evals/local_lane_ladder/fixtures/ctx-sweep-27b-2026-09-08/verify.py"

./operator claim-add -t numeric_measurement --task singlecard-ctx-depth-2026-09-08 \
  -x "The same comparison at ctx16384 is -8.0% and -12.3% across two independent runs" \
  --gate evals/local_lane_ladder/fixtures/singlecard-rank-2026-09-08/FINDING.md \
  --verify-cmd "python3 evals/local_lane_ladder/fixtures/ctx-sweep-27b-2026-09-08/verify.py"

./operator claim-add -t numeric_measurement --task singlecard-ctx-depth-2026-09-08 \
  -x "Solo prefill is flat at 0.872 ms/token from ctx16384 to ctx65536 while headroom falls from 5669 to 1979 MiB, falsifying the headroom hypothesis for the dual prefill advantage" \
  --gate evals/local_lane_ladder/fixtures/singlecard-rank-2026-09-08/FINDING.md \
  --verify-cmd "python3 evals/local_lane_ladder/fixtures/ctx-sweep-27b-2026-09-08/verify.py"

./operator claim-add -t paper_or_report_claim --task singlecard-ctx-depth-2026-09-08 \
  -x "The second RTX 3090 is justified by seat residency at the operator's context depth, not by decode throughput or capacity for large models" \
  --gate evals/local_lane_ladder/fixtures/ctx-sweep-27b-2026-09-08/FINDING.md \
  --verify-cmd "python3 evals/local_lane_ladder/fixtures/ctx-sweep-27b-2026-09-08/verify.py"

./operator claim-add -t paper_or_report_claim --task singlecard-ctx-depth-2026-09-08 \
  -x "Standard A, the loaded regime, and the four single-card preconditions in GOLD_STANDARD.md 2b/2b.1/2b.2 are the correct measurement standard for this program" \
  --gate evals/local_lane_ladder/GOLD_STANDARD.md

# Then, for each paper_or_report_claim (substitute the IDs claim-add printed):
./operator review-delegate <CLAIM_ID> \
  --task singlecard-ctx-depth-2026-09-08 \
  --reviewer "<REVIEWER>" \
  --mode advisory-agent \
  --verify-cmd "python3 evals/local_lane_ladder/fixtures/ctx-sweep-27b-2026-09-08/verify.py"
```

**Known blocker:** `task-transition` refuses with "only supported in enrolled
repositories". The authority broker is running (`authority_broker.py serve`, pid
1206) but the only registration in
`/etc/operator-control-plane-registry.json` is a dogfood path in `/tmp` from
2026-07-20. Whether `task-create` and `claim-add` are affected has not been
tested. **Test with one claim before issuing the whole block.**

## 5. Unresolved: reviewer routing

The reviewer must not be `claude` -- `doctor` errors when a claim is verified by an
identity issued a builder brief for that task (`operator:5699`), and I am the
builder.

Candidates:

- **`qwen3.6:35b` or `qwen3.8:27b` local** -- free, no quota cost, and genuinely
  independent of the frontier lane. But both are **subjects of C2 and C3**, and
  neither is likely to land section 3 items 5 and 6, which need judgment about
  whether a claim is falsifiable.
- **`gemma4:26b` local** -- also a subject, and it is the control model in the rank
  fixture. Self-review by a measured party.
- **A frontier seat** -- strongest on the inference claims and the error-record
  discount. Costs quota, which is the resource this whole program exists to
  economise.
- **Defer** -- register C1-C4, leave C5 and C6 explicitly unverified and marked,
  and route when a reviewer is available.

**Recommendation: route C5 and C6 to a frontier reviewer, or defer them.** C1-C4
re-derive mechanically and anyone can run the script later. C5 and C6 are the two
that changed how this program will measure everything from here, and a weak
sign-off on those is worse than an open claim -- the same argument the 2026-09-05
call made, and it applies more strongly here because C6 is a standard rather than
a result.

This is Erik's call: his ledger, his reviewer budget, and his hardware decision
sitting downstream of C5.
