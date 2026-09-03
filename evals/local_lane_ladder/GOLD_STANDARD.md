# Gold standard for local / Front E evaluation

**Status:** active reference (2026-08-11; Qwen 27B / z13 32K correction 2026-08-15)  
**Owner:** Erik  
**Applies to:** Front E routability work, local-lane ladder packs, model comparisons
(gemma4 26b/31b, qwen class), dual-3090 capacity claims when they rest on “tests better.”

This note **composes two existing golds**. It does not invent a third ladder and does not
rebrand Alignerr invoices as Phoenix fixtures.

| Gold | Where it lives | What it standardizes |
|------|----------------|----------------------|
| **A. Alignerr DocAI process** | `~/Alignerr/` (Batch 4/5 guidelines, `batch4_failure_catalog.md`, live ops) | How an answer becomes **trusted gold** |
| **B. Local-lane L0 / L1 / L2** | This directory + `LOCAL_LANE_CONTRACT.md` / `LOCAL_LANE_CONTRACT_SPEC.md` | How **task shape complexity** increases |

Related measured work (do not re-derive): `ANALYSIS.md`, `RESULTS.md`,
`docs/LOCAL_LANE_ROUTER_STUDY.md` (router = 26b),
`project-phoenix/docs/domain_runs/GEMMA4-CTX8192-3090-VS-Z13-001/`,
encoding floor packets, `PILOT_CONFOUND_FINDINGS.md` / continuation-loop audit.

---

## 1. Complexity axis — three task types (L0 → L2)

Increasing structure reduces degrees of freedom. That is the axis already stress-tested
on the 216-cell ladder (6 tasks × 3 levels × 4 models × 3 trials).

| Level | Name (contract language) | Freedom | Local expectation |
|-------|--------------------------|---------|-------------------|
| **L0** | Goal-shaped | High — goal only | Often fails; many historical fails confounded by old harness |
| **L1** | File-named / partial structure | Medium | Middle band |
| **L2** | Plan-shaped (R1–R6 contract) | Low — paths, anchors, one-tool steps, postcondition | Best local success when grading is honest |

**Contract R1–R6 (L2 target):** exact paths · anchored edits · one tool call per step ·
explicit success criterion · imperative closed vocabulary · bounded scope.  
Canonical rule text: `LOCAL_LANE_CONTRACT.md`.

### What the ladder already showed (and what it did not)

| Established | Not established / qualified |
|-------------|-----------------------------|
| Pass rate **rises L0→L2** for `gemma4:26b`, `gemma4:31b`, `qwen2.5-coder:32b` (aggregate) | That every historical **fail** was model inability — **88** negatives confounded by pre-`890d595` terminal `run_command` (relabel 2026-08-08) |
| **128 passes** remain valid (deterministic postcondition met) | That E0 is Front E routability evidence — E0 is a **harness repro**, not new measurement |
| `gemma4:31b` solves hard multi-file case at every L on the original grid | That 31b is best for **conversational** work (~7 t/s on z13 &lt; ~20 t/s floor) |
| Shape predicts success better than “difficulty” slogans | Routing accuracy ⇒ execution success (router study never executed tasks) |

**Rule:** cite **L0/L1/L2** as the complexity ladder. Do **not** call it “the Alignerr types.”
Alignerr’s step templates (Search / Extract / Calculate / …) are **trajectory vocabulary**
for DocAI, not the Phoenix local shape axis.

---

## 2. Answer / trust axis — Alignerr DocAI as process gold

Source: `~/Alignerr/batch4_authoritative_guidelines.md`, Batch 5 Phase 2 PDF, failure catalog.

Every **scoreable** local or routability cell must satisfy the spirit of:

| Alignerr rule | Local / Front E equivalent |
|---------------|----------------------------|
| One **`golden_response`** (deterministic) | Machine-checkable **postcondition** (file contains X; command exits 0; hash; exact string) |
| ≥2 PDFs when required | Prefer multi-check or multi-file fixtures; never a single self-report |
| Visual / source re-derive (not broken text layer) | Grader reads **artifacts**, not model narration or harness “I succeeded” |
| Trajectory ≥3 single-action steps + formulas | L2 steps or retained tool trace; drop-reasons if candidates discarded |
| Reproducible by another person | Fixture + grader script another machine can re-run |
| Dispute ≠ verdict | Re-derive from sources; never adopt a challenger’s number wholesale |
| Route corrections through evidence | Operator claim/evidence (or explicit pack evidence), not silent form edits |

**Failure catalog culture** (`batch4_failure_catalog.md`): document **harness** mistakes
(capitulation to reviewers, missing re-derive). Same family as opr continuation-loop
confounds — keep a living list when Front E harnesses fail closed for the wrong reason.

**Out of scope for this gold file:** shipping Batch 5 invoice PDFs into the local ladder
unless a deliberate DocAI-local bridge project is opened. **Methodology transfers; corpus does not.**

### MuJoCo Alignerr prep (parallel gold)

`~/Alignerr/mujoco-prep/INTERVIEW_CRIB.md`: *every answer gets a measured number.*  
Use for **hardware / tok/s / residency** claims. Same spirit: no unsourced “tests better.”

---

## 2a. Sample-size policy — how much n before a claim counts

**Added 2026-08-30**, directly motivated by `fixtures/gemma26-csv-n100-baseline/FINDING.md`:
a cell that looked clean at n=6 across three separate runs (5/6, 6/6, 6/6) turned out
to have a true pass rate of 75% (95% CI [66.5%, 83.5%]) at n=100. `P(6/6 by chance at
that true rate) = 17.8%` — not rare. Two same-night findings (a brevity-instruction
fix, a VRAM-cap accuracy check) had been read with more confidence than an n=6 sample
against an unknown true rate can actually support. Neither finding was wrong, but the
confidence level attached to the pass-rate claim specifically was.

**Rule: every ablation result must be labeled with the tier its n actually supports,
and the label travels with the claim wherever it's cited.**

| n | Tier | What it can support | What it cannot |
|---:|---|---|---|
| 1 | **Screen** | "worth running further" / "not obviously broken" | Never cited as a finding on its own |
| 6 (this harness's floor) | **Directional** | A hypothesis, a plausible effect, a reason to run more | A "clean X/6" is not evidence of a *rate* — see the n=100 result above. Continuous measures (token counts, wall-clock) have real power at n=6 even when pass/fail does not; a large effect-size claim on a continuous metric can stand at n=6, a pass-rate claim cannot. |
| 30 | **Reportable** | A real comparison between two conditions, with an honest CI | Precision below roughly ±9 points (binomial, p≈0.5) |
| 100 | **Rate estimate** | A defensible point estimate with CI narrow enough to compare against another n=100 run | Anything finer than the CI width — don't over-read a 3rd n=100 run landing a few points differently as a trend without a proper two-sample test |

**Practical consequence:** a pass/fail comparison written up from an n=6 ablation must
say so explicitly and must not use language like "no accuracy cost" or "clean sweep"
as a settled conclusion — "consistent with no cost, underpowered to confirm" is the
correct phrasing until a matched higher-n run exists. This is not new caution invented
for its own sake; it's the exact caveat `gemma26-12gb-cap-e9`'s own Limits section
already carried, now backed by a real number instead of a general hedge.

**Selection bias in screen-then-confirm (added 2026-09-02).** The tiers above
govern how big an n must be. This governs *which cells you re-run*, and it is a
separate trap.

When a screen produces many cells and you confirm only the most extreme ones,
those cells regress toward the mean **whether or not any effect is real** — they
were selected partly for their noise. Confirming only extremes therefore cannot
distinguish a genuine effect from selection.

Measured instance: `e9-l1-pi-screen` screened 20 model x task cells at n=6 and
sent the two most extreme (both 2/6) to n=30. One came back **27/30 (90%)** —
the screen result had a 0.1% chance at that rate, and mechanical causes were
ruled out. The other came back **16/30 (53%)**, consistent with its screen. Half
the finding was selection artifact, and the write-up's central framing had to be
retracted.

**Rule:** treat screen numbers as *targeting*, never as effect estimates, and
never quote a screen cell's rate in a finding. When confirming, either
(a) confirm a random subset alongside the extremes so regression is measurable,
or (b) state explicitly that the confirmed cells were selected on extremity and
that a single regressing cell is the expected outcome rather than a surprise.
A screen cell that survives confirmation is evidence; one that regresses is not
evidence of anything, including that the screen was broken.

**When n=100 is worth the GPU time:** reserve it for the most-contested, most-cited
cell in a given investigation — not every cell. `gemma26-csv-n100-baseline` was worth
it specifically because three separate n=6 samples had already disagreed with each
other on that exact cell. A cell nobody has questioned does not need this treatment
pre-emptively.

---

## 3. Model seats (from measured work, not preference)

**Rates below are chip-to-chip: RTX 3090 (320 W) vs Ryzen AI MAX 390
(Radeon 8050S).** Cite placement next to the rate. 100% GPU is the clean
case, not a veto. A few-percent **weight lip** on the 3090 (`qwen3.6:35b`
at 4%/96%, 86.4 t/s) is a host-conditioned row. The same blob is 100%
iGPU on the MAX 390. Hide neither the model nor the spill. Do not mix
3090 rates with MAX 390; see `DESKTOP_BENCHMARK.md` and `Z13_BENCHMARK.md`.

| Seat | Model | Role |
|------|--------|------|
| **Router + local executor** | `gemma4:26b` | Seat on **both chips**. Lane + mode + plan-shaped tool work. **133.0 t/s** on the 3090 / **55.2 t/s** on the MAX 390, 100% GPU. E9 24/30 on both. |
| **Fast Qwen** | `qwen3.6:35b` | 35B-A3B MoE. 3090: **86.4 t/s**, 4%/96%, E9 **14/30**. MAX 390: **59.2 t/s**, **100% GPU**, E9 **18/30**. Faster than 26b on the MAX 390, slower on the 3090. Not the seat. |
| **Dominated, not unusable** | `gemma4:31b` | Ties 26b on correctness (36/54 each, P=0.49) and is **3.8x slower** (34.8 t/s). 26b dominates it, so nothing argues for choosing it — but 34.8 t/s clears the ~20 t/s interactive floor comfortably, and delegated work has no floor at all |
| **Floor local** | `qwen2.5*:14b` class when 100% GPU | Encoding / smaller tasks |
| **Measured dense-Qwen candidates; no seat assigned** | `qwen3.6:27b`, `qwen3.8:27b` | 3.8 is faster; correctness is tied. Both now complete a native 32K / 100% GPU repository-guide cell on z13. See below. |
| **Capacity unlock (dual later)** | Qwen ~32B class | Same fixtures only — then claim “tests better” |
| **Frontier** | Claude / Codex / … | `frontier` / `needs_supervision` lanes |

### Dense Qwen 27B characterization

These models are measured local candidates, not an undifferentiated future capacity class:

- **Correctness:** `qwen3.8:27b` and `qwen3.6:27b` scored 76/105 and 73/105 in the
  pooled head-to-head (`p=0.761`), so the current agentic fixtures do not establish a
  correctness difference. Both scored 15/15 on the corrected BT hard probes, which
  saturated and therefore cannot rank them. `qwen3.8:27b` produced the field's most
  complete answer on one ambiguous cross-document probe, but that is a qualitative
  strength signal rather than a ranking result.
- **Capability shape:** in E9, `qwen3.6:27b` scored 19/30 and was the only model to solve
  any `csv-summarize-repair` cells, but three of five fixtures were coin-flips. Its
  profile is higher peak reach with lower determinism than the selected `gemma4:26b`
  seat. No equivalent evidence yet shows that 3.8 removes that variance.
- **Throughput:** on the desktop RTX 3090 at matched 16,384 context, 3.8 averaged
  44.6 tok/s against 37.3 for 3.6 (`+19.7%`, four samples each, non-overlapping
  ranges). The direction reproduced on z13 at matched 8,192 context: 16.3 versus
  13.0 tok/s.
- **Memory:** the earlier z13 run placed 3.8's ceiling at 8,192 context, with 12,288
  and 16,384 OOM. That limit is historical, not current: with Ollama 0.32.13 and the
  current model artifact, native OpenCode loaded both 3.6 and 3.8 at 32,768 context,
  reported 100% GPU placement, and completed the repository-guide task. Preserve the
  older result as a versioned runtime observation rather than a model-intrinsic limit.
- **Runtime confounds:** two recorded 3.8 timeouts were Ollama server stalls in which
  the model was never invoked. Both revisions also traverse Ollama's `qwen35` tool-call
  parser, whose observed EOF failures are backend failures rather than model-quality
  measurements.
- **Repository-guide `/init`:** in one matched cell each, both revisions wrote only the
  declared nested `AGENTS.md`, preserved the parent guide, passed the fixture tests, and
  captured every semantic acceptance item. Qwen 3.8 produced the more explicit guide
  and finished in 45.38 seconds against 117.09 for 3.6. That 2.58x task-time gap came
  mostly from fewer generations and tokens, not its 15.3% decode-rate advantage. These
  are successful examples, not reliability estimates; repeated seeds are still needed.
  The same native-provider task also passed on z13 at 32K/100% GPU: 177.83 seconds for
  3.8 and 335.26 seconds for 3.6.

Evidence: [desktop throughput](DESKTOP_BENCHMARK.md), [z13 fit](Z13_BENCHMARK.md),
[hard probes](../bt_floor/HARD_PROBE_RESULTS.md), [E9 profile](NEXT_SESSION.md), and
[runtime diagnosis](SILENT_TURN_DIAGNOSIS.md). The repository-guide continuation is
recorded under Operator task `qwen27-repo-guide-characterization`.

Policy sketch (router study):

```
frontier              → frontier
needs_supervision     → supervised
local_ok + conversational → models clearing ~20 tok/s (here: 26b)
local_ok + delegated      → any local fit (26b or 31b)
```

Tool-call estimates: **0–1** → local band; **≥3** → supervised; **1–2** needs **data-locality**
feature (local file vs network) — study §3.2.

### Decode rates vs the ~20 tok/s conversational floor (residency-verified)

Use these numbers, not the older power-sweep range. Measured at `num_ctx 8192`,
220 W, **100% GPU residency confirmed via `ollama ps`**, low variance across 3 runs
(`project-phoenix/docs/domain_runs/GEMMA4-CTX8192-3090-VS-Z13-001/findings.md`):

| Model | desktop 3090 | z13 | vs ~20 t/s floor |
|---|---:|---:|---|
| `gemma4:26b` | **91.4** t/s | 18.8 t/s (38%/62% CPU/GPU) | clears on desktop; marginal on z13 |
| `gemma4:31b` | **18.1** t/s | 4.86 t/s (45%/55% CPU/GPU) | **below on both** |

**Recurring mis-citation — reject it.** `DEDICATED_VS_UNIFIED_MEMORY.md` §6 has an
older 200–350 W sweep whose `gemma4:31b` column peaks at 30.8–31.7 tok/s. That sweep
**did not confirm residency per row** and was probably partially CPU-spilling; its
own §6 note says so. Citing "31B runs at ~31 tok/s" to argue 31b clears the
conversational floor and should be the default interactive model is therefore
unsupported — the residency-verified figure is 18.1 t/s, i.e. *below* the floor,
and lower than the sweep's 300/350 W rows despite a higher cap.

This is why §1 files "31b is best for conversational work" under **Not established**.

**UPDATED 2026-08-15 — the seat table changed, and the bar this paragraph set is
what changed it.** The old table read *"26b conversational / router, 31b
delegated / executor"* and listed 26b at "~40 t/s". That 40 was a **z13** rate
applied to the desktop. Desktop, residency-verified at 100% GPU with every model
in the field (`DESKTOP_BENCHMARK.md`, corroborated by 279 `ollama ps` samples in
`HARDWARE_TRANSFER.md`):

| | desktop | z13 |
|---|---:|---:|
| `gemma4:26b` | **133.0 t/s** | 46.2 |
| `gemma4:31b` | 34.8 t/s | 7.2 |

`fixtures/q36-35b-spill-tps/RESULTS.md` had already measured 26b at 125.7-128.0
t/s at 100% GPU across 16k and 32k context; that pack and the seat table
disagreed by 3x for weeks without anyone reconciling them.

On correctness the two are tied — 36/54 each, P=0.49 in E11 (n=18, 378 cells) —
so the 3.8x decode gap decides it, and it decides for 26b. **`gemma4:31b` is
dominated — not unusable.** It runs at 34.8 t/s, well above the ~20 t/s floor,
and that floor is a perceived-latency threshold for interactive use only
(informal `opr` bench sessions), not a capability gate. The argument against 31b
is that 26b matches it on correctness and is 3.8x faster, so there is no task it
is the right answer for — not that it is too slow to run.

The rule stands for the next change: a seat move needs a **placement-logged**
rate on the machine it applies to. Unverified rates stay out. A logged 4%
MoE weight lip does not. G2 in `new_model_gate.sh` warns on spill and only
refuses CPU-only / failed load — it does not keep 86 t/s models off the
speed table. The "~40 t/s" figure was itself the inherited unverified claim
this sentence was written to guard against, which is how it survived so long.

**UPDATED 2026-08-17 — 35b belongs on the speed ranking, and now has an E9 row.**
`fixtures/q36-35b-spill-tps` measured `qwen3.6:35b` at **86.4 / 84.0 t/s**
(16k / 32k) with a stable 4% weight spill. `fixtures/q36-35b-e9` ran the
five-fixture ceiling battery: **14/30** vs same-run 26b **24/30** (p=0.015).
26b matched its E9 score exactly. 35b is on both tables. It is not the seat.

### Out of field — vision grader

`qwen3-vl:30b` is **not a seat and not a ranking row.** It is a vision-language
grader (pixels in, text out). One job: score stills the text field cannot see
(paper 1.37 ATS cartoon, Comfy vs frontier). Packs: `fixtures/vl-smoke`,
`fixtures/vl-casestudy`.

Do not add it to Elo, L0–L2, tok/s-vs-ladder, or seat tables. Historical packs
that already ran it (E2, E9, desktop sweep) stay as records; new field tables
and new ladder batteries omit it. `new_model_gate.sh` refuses the tag.

---

## 4. Rules for any new Front E pack (after E0)

E0 (`fixtures/e0-desktop-pack/`) is **not** routability gold. It reproduced the July desktop
sweep and is filed as harness-regression evidence only. See consultant FINDING + BN Front E.

A pack that **may** count toward Front E must:

1. State a **new question** (not “rerun July L2 on three tasks”).
2. Use **L0/L1/L2** (or a documented subset) as the complexity axis.
3. Define **Alignerr-style postconditions** per cell (R4 + golden).
4. Grade with **deterministic checks**; retain traces (no terminal-tool false fails).
5. Report **placement** (`ollama ps`) on every ranking row. 100% GPU is
   preferred. A few-percent weight lip is a host-conditioned row, not a
   reason to omit the model. KV-default overflow is still a confound —
   pin `num_ctx`, do not hide the score.
6. Keep **desktop vs z13 ledger** identity honest (Front **H** — two `.operator/` trees).
7. Register claims only for what was measured; UID-isolated verify preferred.

**Minimum first real E pack (suggested):** same 3–6 L2 fixtures × `{14b-class, 26b, 31b}`
(and later 27/32b when dual/fit), n≥3, postconditions only — tests “who tests better”
under this gold standard.

---

## 5. Explicit non-goals

- Casual-ratify Operator PBCs.
- Merge z13 and desktop ledgers (unsafe; Front H).
- Treat router accuracy as execution proof.
- Treat E0 or confounded ladder fails as model ranking.
- Spend frontier tokens re-deriving L0/L1/L2 monotonicity without new fixtures.

---

## 6. Pointers

| Path | Role |
|------|------|
| `LOCAL_LANE_CONTRACT.md` | R1–R6 short rules |
| `LOCAL_LANE_CONTRACT_SPEC.md` | Full background |
| `docs/LOCAL_LANE_ROUTER_STUDY.md` | 26b router measurement |
| `ANALYSIS.md` / `RESULTS.md` | 216-cell ladder |
| `fixtures/e0-desktop-pack-consultant-review/FINDING.md` | Why E0 ≠ Front E evidence |
| `~/Alignerr/batch4_authoritative_guidelines.md` | DocAI process gold — **z13 only** (see below) |
| `~/Alignerr/batch4_failure_catalog.md` | Harness failure culture — **z13 only** (see below) |
| `~/Alignerr/Labeling_Instructions.pdf` | **Code-editing eval rubric** — present on desktop; see §7 |

### Host availability of the Alignerr corpus (checked 2026-08-13)

`batch4_authoritative_guidelines.md`, `batch4_failure_catalog.md` and the Batch 5
Phase 2 PDF **do not exist on desktop** — verified by name across `/` and by
content signature. They live on **z13**, per the bridge handoff's asset table
(*"Alignerr corpus | `~/Alignerr/` | only if that tree exists on desktop"*). The
desktop `~/Alignerr/` tree is a different, code-eval engagement.

A desktop agent following the two rows above hits missing paths with no
explanation, which is the cold-start failure the bridge doc warns about. Two
things follow:

- **Do not invent a parallel gold** from the absence. §2's mapping table below is
  the distilled transfer and is self-contained — use it.
- **Resolved 2026-08-13** by retrieving the methodology files from z13 into
  desktop `~/Alignerr/` (methodology only — the 260 MB Batch 5 PDF pools were
  deliberately left behind, per "methodology transfers; corpus does not"):

**The 15-vs-≥3 conflict was form-slots vs a validity floor, exactly as suspected.**
Verbatim: *"Use `step_1` through `step_15` as separate fields. Use at least three
steps; leave unused fields empty."* So **≥3 is the rule**; 15 is the platform form.

**Full trajectory step vocabulary** (and it is explicitly *not* closed —
*"These are descriptive categories, not mandatory wording"*):

| Step form | Definition |
|---|---|
| **Scan** | Visually scan the whole pool for an exact condition; state count and exact filenames |
| **Reference lookup** | Open one exact filename, locate one field, state its value |
| **Extract** | Open one exact filename, extract the requested value(s) from a stated location |
| **Calculate** | Show one arithmetic operation as a full expression with its result |
| **Derive/final** | Apply the final derivation; round to exactly two decimals |

Three source rules that sharpen the local mapping in §2:

- *"Each step describes exactly **one action**. Do not combine scanning/searching
  and extraction in one step."* — the compound-call prohibition, stated directly.
- *"Whenever a step produces multiple candidates but later steps retain only some,
  explicitly name the rejected candidates and explain why each was dropped."* —
  drop-reasons are mandatory, not optional colour.
- *"Do not use PDF text search as the source of truth; some PDFs have broken text
  layers."* — the original form of "grader reads artifacts, not narration."

**Acceptance rule that is really R6:** *"Find all matching files: no omissions and
no extras."* The local equivalent is scope enforcement — an answer that edits the
right file plus three others is the "no extras" failure.

**Instruction-conflict rule (transferable as a fixture design).** Batch 4 carried a
genuine internal contradiction between two skipping rules. The ruling was: *"Do not
improvise if that situation occurs. Preserve the exhaustive scan evidence, open an
issue, and request an operator ruling before skipping or submitting."* A fixture
whose spec is deliberately self-contradictory, where correct behaviour is to
**escalate rather than guess**, is a strong candidate discriminator for capable
models.

### The failure catalog: what it actually catalogues

`batch4_failure_catalog.md` opens by scoping itself, and the scoping is the point:

> **this catalog documents our own harnesses' mistakes, not external reviewers'
> claims.** A reviewer disputing an answer is an input to be independently
> verified, not a party whose competence gets graded here.

All four entries are **one root pattern — reviewer-dispute capitulation** — and the
generalisation is sharper than "dispute ≠ verdict":

1. *"A dispute is a claim, not a verdict, regardless of who raises it or how
   confident it sounds."*
2. **Evaluate each sub-claim independently.** A dispute can be right about the file
   set and wrong about the arithmetic. Entry 1's diagnosis: *"The correct parts of
   the dispute made the incorrect parts look credible by association — that's the
   actual failure mode."*
3. **Capitulation runs in both directions.** Entry 4 is over-*exclusion* under
   reviewer pressure: *"abandon a previously-sound judgment call without
   re-verifying whether the reviewer's objection is actually correct."*
4. **Not every blocked dispute is a mistake.** Entry 3 is recorded as *closed, not
   a confirmed harness failure* — the reviewer turned out to be right and the
   ambiguity was real. *"'Hold for clarification' is a valid outcome distinct from
   'harness was wrong'."*

Direct consequence for this eval programme: the **harness-defect catalogue**
(extractor bug, name-gated system prompt, uncontrolled sampling/context/thinking)
is a *different artifact* from the model scoreboard and the two must never be
pooled — which is exactly why `e1`–`e3` are retained as harness records rather
than deleted or re-scored.

### §7 — `Labeling_Instructions.pdf`: an Alignerr rubric already aimed at code

A separate Alignerr engagement (Model Response Evaluation, repo-based) that ships
a **code-editing evaluation rubric** — closer to Front E's target format than the
DocAI corpus, and present on this host. Load-bearing parts:

- **Forced-direction preference scale, 0–7, with no tie.** 3/4 is the
  "reasonable people could disagree" band. *"Correctness and final code quality
  matter most. A model that took a messy path but produced better final code
  should be rated higher than a model that was efficient but produced weaker
  code."*
- **12 behavioural weakness codes**, each requiring evidence-backed justification:
  `INST · OVERENG · TOOL · LAZY · VERIFY · FALSE · ROOT · DESTRUCT · FILE ·
  HALLUC · DOCS · VERBOSE/FORMAT`.
- **Disambiguation pairs** — the part most rubrics omit and the reason inter-rater
  agreement holds: *VERIFY* = did not check vs *FALSE* = claimed it worked when it
  did not; *TOOL* = used a real tool wrong vs *HALLUC* = invented one; *LAZY* =
  gave up early vs *ROOT* = finished but fixed symptoms.
- **Flagging rules that map directly onto harness guards:** evaluate final output,
  not chain-of-thought; do not penalise pre-existing codebase issues; do not
  penalise for not running tests when execution is disabled; **apply weaknesses
  symmetrically** across compared models.
- **Three-line summary:** `Correctness > Efficiency` · `Evidence > Assumptions` ·
  `Final Code > Process`.
| `project-phoenix/docs/handoffs/NEXT_SESSION.md` §E | Front E status |
