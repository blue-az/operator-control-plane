# Gold standard for local / Front E evaluation

**Status:** active reference (2026-08-11)  
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

## 3. Model seats (from measured work, not preference)

| Seat | Model | Role |
|------|--------|------|
| **Router** | `gemma4:26b` | Lane + mode (+ tool-call band); ~40 t/s; **LOCAL_LANE_ROUTER_STUDY** conclusion |
| **Local executor / high tester** | `gemma4:31b` | Plan-shaped tool work when fit/speed OK; dense-slow for chat |
| **Floor local** | `qwen2.5*:14b` class when 100% GPU | Encoding / smaller tasks |
| **Capacity unlock (dual later)** | Qwen ~27–32B “fits well” | Same fixtures only — then claim “tests better” |
| **Frontier** | Claude / Codex / … | `frontier` / `needs_supervision` lanes |

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
The seat table above stands: **26b conversational / router, 31b delegated / executor.**
A future change to these seats needs a residency-verified rate, not a throughput
claim inherited from an unverified sweep.

---

## 4. Rules for any new Front E pack (after E0)

E0 (`fixtures/e0-desktop-pack/`) is **not** routability gold. It reproduced the July desktop
sweep and is filed as harness-regression evidence only. See consultant FINDING + BN Front E.

A pack that **may** count toward Front E must:

1. State a **new question** (not “rerun July L2 on three tasks”).
2. Use **L0/L1/L2** (or a documented subset) as the complexity axis.
3. Define **Alignerr-style postconditions** per cell (R4 + golden).
4. Grade with **deterministic checks**; retain traces (no terminal-tool false fails).
5. Report **100% GPU / spill** when making capacity claims (`ollama ps` or equivalent).
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
