# Review call: Jev as a grader, whole-essay ranking vs claim-level support checks

- **Status:** draft; not independently verified. Two small paid probes have been run (total ≈ $0.0044).
- **Proposed ledger task:** `jev-decision-grader-2026-09-21`
- Measurement author for J1–J7 below: `claude-39d4ca7a` (this session). Review is routed to
  `claude-supervisor`, a distinct registered identity. Do not infer verification from this document.
- **Evidence directory:** `evals/jev_probe_20260921/` (scripts, raw JSON, offline `score.py`).
- **Time pressure:** Jev's promotional price ($0.042 / MTok input, output free) ends **2026-09-25**;
  the post-promo price is unannounced. The review does not need to finish by then, but any follow-up
  sweep that should be priced at the promo rate does.

## 1. Why this packet exists

Jev (TypeSafe AI, early access since 2026-09-15) is a "decisions" model: it returns typed answers
with probabilities and confidence, not text. That makes it a candidate for the grading/judging layer
of the blind-read evals, where the current LLM judge disagreed with the operator in most rounds.
This packet records two probes against rounds where the operator holds ground truth (R3, R4) and
asks whether the conclusions drawn from them are sound.

## 2. Access facts (prerequisite, observed directly)

| Fact | Observation |
|---|---|
| OpenRouter model id | `typesafe/jev-1.13`, provider TypeSafe, build `jev-1.13-20260917`, 32K context |
| Discovery | Absent from `GET /api/v1/models` (output modality `text->decisions`); present at `/api/v1/models/typesafe/jev-1.13/endpoints` |
| Endpoint | `POST https://openrouter.ai/api/alpha/decisions`; `chat/completions` returns 400 naming this endpoint |
| Question types | `choice`, `score`, and an undocumented `noul`. **No `boolean`** (Vercel's AI SDK docs list one; OpenRouter rejects it) |
| Auth | Existing key at `~/.config/openrouter/api_key` (same one `ppr_consultant_bench/bench.py` uses) |

## 3. Claim map (local labels, not ledger IDs)

| # | Type / status | Scoped claim | Verification route |
|---|---|---|---|
| J1 | fact, observed | Access facts in §2 | Re-query the endpoints listing; one synthetic call to each endpoint |
| J2 | numeric measurement | **Essay ranking fails.** Given the analyst brief plus the three blinded answers (`judge/{A,B,C}.md`), Jev's mean per-answer scores never reproduce the operator ranking in R3 (either order) or R4 original order; R4 shuffled matches | `python3 evals/jev_probe_20260921/score.py` (offline) over `essay_rank_results.json` |
| J3 | numeric measurement | **Order/label sensitivity.** Relabelling the same answers (A/B/C → X/Y/Z, reordered) flips R4's ranking and moves R3 "best"; within a setup, three repeats are near-identical, so the effect is systematic, not noise | Same; compare `orig` vs `shuffled` rows |
| J4 | numeric measurement | **Self-contradiction.** The same answer was the modal pick for both "best" and "worst" in 4 of 12 essay calls; per-answer scores sat at 1.0–1.5 on 0–2 with confidence 0.01–0.28 | Same |
| J5 | numeric measurement | **Claim-level checks work on this set.** With the claim plus its cited source lines, Jev classified 23/24 labelled claims correctly at p=0.5 on both repeats (12/12 unsupported at p=0 exactly; 11/12 supported, S3 at 0.35 and S12 at 0.51/0.56). Max repeat spread 0.05 | `score.py` over `claim_check_results.json`; labels are in `jev_claims.py` `CLAIMS` |
| J6 | interpretation | The contrast J2–J4 vs J5 is a task-shape effect (holistic judgment vs bounded support check), consistent with decompose-first, not evidence that Jev is a weak model overall | Review the reasoning; see threats in §4 |
| J7 | proposal | Jev is a plausible cheap **claim-support checker** inside the blind-read judge pipeline (LLM extracts claims + cited lines; Jev checks each), not a replacement for the holistic judge | Needs the harder test in §5 before any adoption |

## 4. Threats to validity (the reviewer should weigh these, not take them as settled)

1. **Labels were authored and checked by the measurement author.** Each of the 24 labels was checked
   against the source lines, but by the same session that designed the claims. An independent pass over
   `CLAIMS` in `jev_claims.py` is the first thing to do.
2. **The unsupported set skews easy.** Several unsupported claims are number swaps or direct
   contradictions of the excerpt. The analysts' real errors were subtler (scope transfer, conflation).
   Only U6 (A4-type scope error), U7 (A3 conflation), U8 (A:21) and U10 (absence over a whole page)
   are the harder kind. 12/12 at p=0 may overstate performance on realistic errors.
3. **Excerpts do the hard part.** Claims were paired with the lines the LLM verdict cited. A pipeline
   must find those lines itself; retrieval errors are untested here.
4. **Asymmetry.** Every unsupported claim scored exactly 0 while two true claims were lukewarm. S3's
   miss plausibly comes from the claim naming "the domains page", which the excerpt does not show. That
   is a claim-wording artifact, but it also means Jev may penalize any reference to context outside the
   excerpt. This is a bias toward "unsupported" that a pipeline would need to calibrate for.
5. **Essay probe was out of scope for the model by design.** Sources (≈130 KB, ≈33K tokens) exceed the
   32K context, so Jev judged answers without the pages the LLM judge used. J2–J4 therefore test holistic
   judgment from brief + answers, not fidelity checking. That is a fair negative for "replace the judge"
   and says nothing about fidelity checking with sources.
6. **Ground truth is n=2 rounds, one operator.** R3 is the only round where operator and LLM judge agreed,
   and the operator called that agreement luck (registry state for R4).
7. **Single model build.** `jev-1.13-20260917` only; TypeSafe is iterating quickly.

## 5. Proposed next measurement (not run; gated on this review)

Build the claim set from **all** R3 and R4 verdict findings (§1 unsupported claims and the §2/§3
confirmations), with labels written by someone other than the measurement author, and let the pipeline
retrieve excerpts itself (not hand-picked lines). Predeclare the threshold and the metric (balanced
accuracy, plus calibration of p against label), run ≥ 3 repeats, and include a second label permutation
of the question (`supported`/`unsupported` swapped in criteria order) to test the order sensitivity seen
in J3 at claim level. Estimated cost: under $0.05 at promo pricing.

## 6. Reviewer questions

- Is J2–J4 enough to rule out Jev as a holistic judge, or should a with-sources variant be attempted by
  chunking pages under 32K?
- Are the 24 labels in `CLAIMS` correct? S3, S12, B1 and B2 in particular.
- Does threat 2 (easy unsupported set) reduce J5 from "works on this set" to "works on contradictions"?
  If so, restate J5 accordingly.
- Is the §5 design sufficient to support J7, and who should author the independent labels?
- Should the post-2026-09-25 price be a precondition for adopting J7, given Luna's precedent of an 80%
  price move within three weeks?

## 7. Scope and data handling

With operator approval, the probes sent the following to TypeSafe via OpenRouter: the essay probe sent
both rounds' `ANALYST_BRIEF.md` and blinded `judge/{A,B,C}.md`; the claim probe sent excerpts of the
captured public pages in `bt_describe_20260921/inputs/`. No private transcripts or keys were sent.
Nothing in this packet changes any existing eval, verdict, registry entry or dashboard.
