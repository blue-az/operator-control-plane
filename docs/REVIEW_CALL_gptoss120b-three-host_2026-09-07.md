# Supervisor review call: gpt-oss:120b across three hosts, as a harness-effect isolator

- **Status:** drafted, not yet issued. **This is a design review, not a results
  review** - the experiment has not been run. The call is for permission to spend
  the time, and for the design to be attacked before it produces numbers that
  would have to be retracted.
- **Proposed ledger task:** `gptoss120b-three-host-2026-09-07`
- **Author:** `claude` (proposer, not yet builder). The idea arose in an
  unstructured session. See §3.6 for why that matters.
- **Repo:** `~/operator-control-plane`, branch `master`
- **Verify command:** none exists. Nothing here is reproducible yet. That is the
  point of reviewing it now.

## 1. Central question for the reviewer

Every local-vs-frontier comparison this program has published varies **model and
hosting at the same time**. `gemma4:26b` on a 3090 against `gemini-3.7-flash-low`
on Google's infrastructure cannot separate "the model is worse" from "the serving
stack is different."

`gpt-oss:120b` is the one model in the roster that can be run on all three:

| host | status |
|---|---|
| desktop, 2x RTX 3090 | measured: **33.8 tok/s**, 45,378 MiB across the pair |
| free Antigravity (Starter Quota) | listed in the model switcher as `GPT-OSS 120B (Medium)`, unmeasured |
| hosted API providers | cited: Artificial Analysis median **207.9 tok/s**, TTFT 0.78s |

Holding the weights constant should make every remaining difference attributable
to serving and harness.

> **Is the "same weights" premise strong enough to carry that conclusion, and if
> it is not, does the design degrade gracefully or become worthless?**

The proposer's position is that pass rate on the existing E9 fixtures is the
measurement worth taking, not decode - because if identical weights produce
different pass rates across hosts, the delta is harness with the model variable
eliminated. **That is the claim most worth attacking**, because the entire value
of the experiment rests on it.

## 2. Claims to register

Only C1 is measured. C2 is cited from a third party. C3-C5 are design
propositions and should be registered as such or not at all - that is part of
what the reviewer is being asked.

| # | Type | Claim | Falsifier |
|---|---|---|---|
| C1 | `numeric_measurement` | `gpt-oss:120b` decodes at 33.8 tok/s on the desktop dual 3090 at e9pin, occupying 45,378 MiB across both cards | `preswap-baseline-2026-09-05/baseline.json` says otherwise, or a re-run disagrees |
| C2 | `external_citation` | Artificial Analysis reports a 207.9 tok/s median output speed for hosted `gpt-oss-120b`, TTFT 0.78s | The AA model page reports different figures |
| C3 | `paper_or_report_claim` | Running one model across three hosts isolates the serving and harness effect, because the weights are held constant | Quantization or checkpoint differs across hosts, so weights are not constant |
| C4 | `paper_or_report_claim` | Pass rate, not decode, is the measurement that carries the isolation, since decode is not comparable across these three instruments | Pass rate saturates at 3/3 everywhere and discriminates nothing |
| C5 | `numeric_measurement` | `gpt-oss:120b` and `qwen3-next` both require both cards (45,378 MiB), so the second 3090 has live MoE tenants today | Either fits one 24 GB card under matched pinning |

## 3. What the builder wants attacked

In the order I think they are most likely to break.

1. **Quantization kills the premise, and I have not checked it.** The local build
   is a GGUF at unrecorded quant. Hosted `gpt-oss` ships MXFP4 natively. If those
   differ, "same weights" is false and C3 collapses - this stops being a
   harness isolator and becomes another confounded comparison with a nicer story.
   **This is the weakest link and it is checkable before any run.** What Agy
   serves is a third unknown and may not be discoverable at all.
2. **The AA number is a different instrument.** 207.9 is a median across
   providers, measured over a network API at whatever batching they use. The 33.8
   is local batch-1, `num_predict 128`, `temperature 0`, think off. Putting them
   in one table is precisely the cross-arm pairing that Corrections #1-#4 of
   `evals/local_lane_ladder/HANDOFF_2026-09-06.md` were written to stop. The
   proposer already drafted them side by side once.
3. **Agy cannot produce a comparable decode number.** No `num_predict`, so the
   third host contributes wall clock and pass rate only. A three-host decode
   table is not obtainable. Only a three-host *pass rate* table is.
4. **Pass rate may not discriminate.** The E9 fixtures currently return 3/3 for
   most cells. If all three hosts pass everything, the experiment produces no
   signal and the design should say in advance what result would count.
5. **Effort settings are an uncontrolled variable.** Agy lists the model as
   `(Medium)`. Local runs under e9pin with think off. Unless these are matched,
   the comparison varies reasoning mode as well as host, which is the same class
   of error as #2.
6. **The provenance of this proposal.** It came out of a long unstructured
   session in which the proposer made a documented run of errors: attributed a
   model to a third party from a marketing page, put two scoring scales in one
   table, misread an image, invented a paper number, filed a document in the
   wrong directory, and **wrote a correction into the handoff that inverted the
   wall-clock arms and had to be withdrawn by a later session**. A reviewer
   should weight the proposer's confidence accordingly and assume the framing
   above is more polished than it is verified.
7. **Whether it is worth the time at all.** The free Agy tier makes the third
   host cheap, but not free - it consumes quota that is currently the seat for
   real work, and the desktop is mid-experiment with a GPU swap pending.

## 4. Commands to issue the call

```bash
cd ~/operator-control-plane

./operator task-create \
  --id gptoss120b-three-host-2026-09-07 \
  --objective "Determine whether running gpt-oss:120b on the dual 3090, on free Antigravity, and against published hosted figures isolates the serving/harness effect with the model held constant. Design review before execution." \
  --assign claude \
  --review "<REVIEWER - see section 5>" \
  --assumption "Local quantization is unrecorded and may differ from hosted MXFP4; the same-weights premise is unverified." \
  --assumption "Antigravity provides no num_predict, so it contributes wall clock and pass rate only, not decode." \
  --assumption "The AA figure is a cross-provider median over a network API and is not the same instrument as local batch-1 decode."

./operator claim-add -t numeric_measurement --task gptoss120b-three-host-2026-09-07 \
  -x "gpt-oss:120b decodes at 33.8 tok/s on the desktop dual RTX 3090 at e9pin, occupying 45,378 MiB across both cards" \
  --gate evals/local_lane_ladder/fixtures/preswap-baseline-2026-09-05/baseline.json

./operator claim-add -t numeric_measurement --task gptoss120b-three-host-2026-09-07 \
  -x "gpt-oss:120b and qwen3-next both occupy ~45,378 MiB across two cards and do not fit a single 24 GB card" \
  --gate evals/local_lane_ladder/fixtures/preswap-baseline-2026-09-05/baseline.json

./operator claim-add -t paper_or_report_claim --task gptoss120b-three-host-2026-09-07 \
  -x "Holding gpt-oss:120b constant across local, Antigravity, and hosted providers isolates the serving and harness effect, provided quantization is verified identical" \
  --gate docs/REVIEW_CALL_gptoss120b-three-host_2026-09-07.md

# Only after the quantization check in section 3.1 passes:
./operator review-delegate <CLAIM_ID> \
  --task gptoss120b-three-host-2026-09-07 \
  --reviewer "<REVIEWER>" \
  --mode advisory-agent
```

## 5. Unresolved: reviewer routing

The subject is `gpt-oss:120b`, so it cannot review itself. Antigravity is one of
the three hosts under test, which makes any Agy-routed reviewer a participant
rather than an observer.

Candidates:

- **`qwen3.6:35b` local** - free, currently being trialled in the interactive
  seat, cross-family from the subject, and not on any host under test. Cheapest
  credible option and newly available since the 2026-09-05 call.
- **`gemma4:26b` local** - same properties, faster, but weaker at the kind of
  reasoning §3 requires, and it is also the model with a documented habit of
  ignoring instructions in interactive use.
- **Frontier via a paid seat** - strongest on §3.1 and §3.6, but spends the
  budget the experiment exists to avoid spending.
- **Defer** - register C1, C2 and C5, leave C3 and C4 explicitly unverified, and
  do the quantization check first, since a failed check makes the review moot.

**Recommendation: run the quantization check before routing anything.** It is a
`ollama show` and a look at what Antigravity reports, it costs minutes, and it
decides whether there is an experiment here at all. If the quants differ, this
call should be withdrawn rather than reviewed.

This is Erik's call: his ledger, his quota, and his machine is mid-swap.
