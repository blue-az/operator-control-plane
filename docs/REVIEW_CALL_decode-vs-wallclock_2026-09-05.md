# Supervisor review call: decode tok/s vs task wall clock, and the ctx-default card split

- **Status:** drafted, not yet issued. Reviewer routing is unresolved — see §5.
- **Amended 2026-09-05, later same day.** After drafting, the stub's headline was
  re-verified and a second claim in it was corrected. Claims C6–C8 and §3 items 6–7
  below are new; commit `36b1b49`, fixture
  `evals/local_lane_ladder/fixtures/45gb-class-footprint-pinned/`.
- **Proposed ledger task:** `decode-vs-wallclock-2026-09-05`
- **Author:** `claude` (builder on this work; this call is a request for
  independent verification, not a self-verification)
- **Repo:** `~/operator-control-plane`, branch `master`, commits `c0a1a7a`,
  `1f2d7e5`, `1708f71`
- **Verify command:** `python3 evals/local_lane_ladder/fixtures/roster-walltime-2026-09-05/verify.py`
  — fail-closed, exits non-zero on any claim that does not reproduce. Runs live
  (~4 min); re-measures the decode claims and re-derives the wall-clock claim
  from committed traces.

## 1. Central question for the reviewer

Two findings landed on 2026-09-05 that between them **invalidate a column this
program has been reporting for weeks**. Both are being sent up because the
consequence is retrospective: past "model X is faster than model Y" claims
resting on decode tok/s are unsupported for agentic work.

> **Is that consequence correctly scoped?** Specifically: is decode tok/s still
> valid for the fixed-model hardware comparisons (the 8 GB card work, the
> single-vs-dual work) that the corrections deliberately left standing?

The builder's position is yes — those hold one model constant and vary the
hardware, so token economy cancels. **That is the claim most worth attacking**,
because it is the one protecting the rest of the program's published numbers
from the same retraction.

## 2. Claims to register

| # | Type | Claim | Falsifier |
|---|---|---|---|
| C1 | `numeric_measurement` | `gemma4:26b`'s default context length is 262,144 | `ollama show` reports otherwise |
| C2 | `numeric_measurement` | Pinning `num_ctx` 16384 raises decode from ~140 to ~214 tok/s, non-overlapping ranges | Any interleaved run where base max >= pinned min |
| C3 | `numeric_measurement` | Base tag occupies two cards (18,010 + 21,325 MiB); pinned occupies one | Base fits one card, or pinned spans two |
| C4 | `numeric_measurement` | `gemma4:26b` decodes 2.9x faster than `qwen3.8:27b` and completes the same E9 tasks 20% slower, emitting 4.3x more tokens | Wall-clock ordering matches decode ordering |
| C5 | `paper_or_report_claim` | Decode tok/s does not predict task wall clock; it remains valid only for fixed-model hardware comparisons | See §3 — this is the contested one |

| C6 | `numeric_measurement` | The 80B/120B footprint convergence holds under matched pinning: 45,384 vs 45,302 MiB, 0.2% apart, all four configs 100% GPU-resident (49/49, 37/37) | Either model moves materially between unpinned and `ctx16384` |
| C7 | `numeric_measurement` | Matched pinned decode is 79.1 vs 34.1 tok/s = **2.32x**, not the 1.9x previously published from mismatched configs | Matched interleaved measurement returns ~1.9x |
| C8 | `numeric_measurement` | `qwen3-next` gains 46% decode from context pinning (54.3 -> 79.1) at 0.1% footprint change and unchanged layer count | Footprint or layer count moves with the speed |

C1–C4 and C6–C7 are mechanical; the verify script covers C1–C4, and C6–C7 are
reproducible from the fixture's recorded method. **C5 is an inference from C4 and
is not covered by any script.** It is still the reason for the review.

**C8 is not a claim I can explain**, only one I can reproduce. It is listed so a
reviewer sees it, not because it is ready to be ruled on.

## 3. What the builder wants attacked

Listed in the order I think they are most likely to break:

1. **Attribution.** I attributed the wall-clock inversion to token count. **I did
   not separate tool-execution time from model time** — both sit inside
   `wall_clock_s`. Effective tok/s ranges 1.5x–3.5x below decode across the
   roster, which means overhead is *not* proportional to token count, so token
   economy cannot be the whole story. If tool time dominates, C5's mechanism is
   wrong even though C4's numbers stand. **This is the weakest link.**
2. **C5's carve-out.** Fixed-model hardware comparisons are claimed safe. But the
   ctx-split finding shows the *same* model tag changes card topology depending
   on `num_ctx`. If a past hardware comparison used unpinned tags on machines with
   different VRAM, the model was not held constant and the carve-out leaks.
3. **Sample size.** C4 is n=2, two tasks, one machine, all 20 cells passing. Both
   tasks happened not to discriminate. Per `GOLD_STANDARD.md` §2a this is Screen
   tier, and I am drawing a directional conclusion from it.
4. **Generality of 35%.** One model, one card pair, one context size. I called it
   "the cost of splitting this model," not a constant, but the stub language may
   still read as general.
5. **Task selection.** I chose the two tasks. A different pair could reverse the
   ordering, and I picked one known-fast and one known-slow rather than sampling.
6. **The pattern of my own errors.** Three of the corrections issued today were
   the *same mistake*: comparing measurements taken under different
   configurations (unpinned base vs pinned tag; unpinned 80B vs pinned 120B;
   morning re-baseline vs afternoon roster). Each was caught only because
   something else prompted a re-measurement. **A reviewer should assume more of
   this exists in the fixtures and sample for it**, rather than take today's three
   as the complete set.
7. **Whether the corrections went far enough.** I corrected the numbers I
   re-measured. I did not sweep the fixtures for other unpinned-vs-pinned
   comparisons, and the four mid-size roster models — where the ctx trap is most
   likely, since it scales with how small the model is — remain unchecked.

## 4. Commands to issue the call

```bash
cd ~/operator-control-plane

./operator task-create \
  --id decode-vs-wallclock-2026-09-05 \
  --objective "Verify that decode tok/s does not predict agentic task wall clock, and that gemma4:26b's 262144 default context splits it across both cards at a 35% decode cost. Confirm the scope of the resulting retraction." \
  --assign claude \
  --review "<REVIEWER — see section 5>" \
  --assumption "Tool-execution time is inside wall_clock_s and was not separated from model generation time." \
  --assumption "C4 is n=2 across two tasks on one machine; Screen tier per GOLD_STANDARD.md 2a." \
  --assumption "The 35% split penalty is measured for one model on one card pair at one context size."

./operator claim-add -t numeric_measurement --task decode-vs-wallclock-2026-09-05 \
  -x "gemma4:26b default context length is 262144, which sizes the KV cache to 39.3 GB and splits the model across both RTX 3090s" \
  --gate evals/local_lane_ladder/fixtures/gemma4-26b-ctx-default-split/FINDING.md \
  --verify-cmd "python3 evals/local_lane_ladder/fixtures/roster-walltime-2026-09-05/verify.py"

./operator claim-add -t numeric_measurement --task decode-vs-wallclock-2026-09-05 \
  -x "Pinning num_ctx to 16384 keeps gemma4:26b on one card and raises decode from 139.9 to 214.4 tok/s (n=6 interleaved, non-overlapping ranges)" \
  --gate evals/local_lane_ladder/fixtures/gemma4-26b-ctx-default-split/FINDING.md \
  --verify-cmd "python3 evals/local_lane_ladder/fixtures/roster-walltime-2026-09-05/verify.py"

./operator claim-add -t numeric_measurement --task decode-vs-wallclock-2026-09-05 \
  -x "gemma4:26b decodes 2.9x faster than qwen3.8:27b and completes the same two E9 tasks 20% slower, emitting 4.3x more output tokens (3366 vs 788)" \
  --gate evals/local_lane_ladder/fixtures/roster-walltime-2026-09-05/FINDING.md \
  --verify-cmd "python3 evals/local_lane_ladder/fixtures/roster-walltime-2026-09-05/verify.py"

./operator claim-add -t paper_or_report_claim --task decode-vs-wallclock-2026-09-05 \
  -x "Decode tok/s does not predict agentic task wall clock and must not be used for model-vs-model speed claims; it remains valid for fixed-model hardware comparisons" \
  --gate docs/VRAM_IS_A_BUDGET_STUB.md \
  --verify-cmd "python3 evals/local_lane_ladder/fixtures/roster-walltime-2026-09-05/verify.py"

# Then, for the paper_or_report_claim (substitute the claim ID that claim-add printed):
./operator review-delegate <CLAIM_ID> \
  --task decode-vs-wallclock-2026-09-05 \
  --reviewer "<REVIEWER>" \
  --mode advisory-agent \
  --verify-cmd "python3 evals/local_lane_ladder/fixtures/roster-walltime-2026-09-05/verify.py"
```

## 5. Unresolved: reviewer routing

`review-delegate` defaults to `openai-codex/gpt-5.6-luna`. **Codex is out of
tokens**, which is why this work moved here in the first place, so the default
cannot serve.

The requirement is simply a **separate agent** from the builder - the reviewer
must not be `claude`, and I am the builder here. (`doctor` enforces a *distinct
verification identity*, not a different model family: it errors when a claim is
verified by an identity issued the builder brief for that task (`operator:5699`).)

Candidates, with the tradeoff:

- **Gemini** — a separate agent from the builder and capable of attacking §3's reasoning.
  Requires the Gemini lane, which memory records as deprioritized.
- **`gemma4_local`** — available and free, but it is *the model under test* in
  C1–C4. Self-review by the subject; also unlikely to land §3.1.
- **Defer** — register the claims, leave C5 unverified and explicitly marked, and
  route when a reviewer is available. Costs nothing and keeps the ledger honest.

**Recommendation: defer.** C1–C4 are mechanically verified by a fail-closed
script that anyone can run later. C5 is the only claim needing judgment, and a
weak reviewer signing it off is worse than leaving it open — an honour-system
`verified_by` is advisory, and a green doctor that nobody should trust is the
exact failure this program already caught once.

This is Erik's call, not mine: it is his ledger and his reviewer budget.
