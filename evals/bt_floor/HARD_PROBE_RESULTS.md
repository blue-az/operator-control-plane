# Hard probes — first field result (WITH RETRACTION)

**Measured:** 2026-08-14, `current` funnel (40,510 tokens), `num_ctx 49152`,
`temperature 0.8`, `think off`, n=5 per cell with `seed=rep`.
**Not UID-verified. No claim registered.**

Raw: `handoffs/bt_hard_20260814_130202.json` (five-model field),
`bt_hard_20260814_135742.json` (`qwen3.8:27b`), `bt_hard_20260814_121228.json` (n=1).

> ## RETRACTION (2026-08-14, same day)
>
> **The h2 answer key was wrong, and two findings built on it are withdrawn.**
>
> h2 graded models against `operator-control-plane/AGENTS.md:90` — *"nothing in
> that doc is implemented yet"*. That line is **stale**. The spec's own line 3
> reads **"Status: Phases 1–3 implemented (2026-07-18)"**, with `DONE 2026-07-18`
> on all three phases, and the code agrees: `crystal-attach` is registered at
> `operator:52`, handled at `:2447`, and fails closed on status at `:2453`
> quoting T2. `crystal_parse.py` exists. `./operator crystal-attach --help` runs.
>
> The stale line was written 2026-07-18 in `2b46544` — the same day the phases
> were marked DONE — and never updated. AGENTS.md has been edited since
> (2026-08-12, `8041b19`) with that line surviving.
>
> **What this means:** models penalised for "confabulating an implementation
> date" were quoting the corpus accurately. `qwen3.6:27b` and `qwen3.8:27b` both
> independently produced "2026-07-18" because it is written in the spec. Two
> models agreeing on a specific date was the tell, and it should have prompted a
> corpus check before the finding was written, not after.
>
> **Withdrawn:**
> - *Finding 2, "the failure mode is reading a plan as a status"* — there was no
>   such failure. The plan says implemented because it is implemented.
> - *Finding 3, "the gemma4 tie breaks at p=0.048"* — re-graded, 26b vs 31b is
>   5/5 vs 2/5, **p=0.167**. The tie stands. E11's P=0.49 is unchallenged.
>
> **Not withdrawn:** `gemma4:26b`'s answers were never wrong. It said the
> mechanism that would permit status-setting "does not exist yet and is
> explicitly prohibited" — true independently of whether the spec shipped.

## Corrected result

h2 re-graded accepting both readings of "does the mechanism exist yet" (see
below). h1 and h3 unaffected.

| Model | h1 | h2 (corrected) | h3 | total |
|---|---|---|---|---:|
| `gemma4:26b` | 5/5 | 5/5 | 5/5 | 15/15 |
| `qwen3.6:27b` | 5/5 | 5/5 *(was 1/5)* | 5/5 | 15/15 |
| `qwen3.8:27b` | 5/5 | 5/5 *(was 2/5)* | 5/5 | 15/15 |
| `gemma4:12b` | 5/5 | 4/5 | 5/5 | 14/15 |
| `gemma4:31b` | 5/5 | 2/5 | 5/5 | 12/15 |
| `granite4` (3.4B) | 0/5 | 3/5 | 0/5 | 3/15 |

## Finding 1 — the probes saturate (h1, h3 unchanged; h2 now too)

h1 and h3 are 5/5 for every model from 12B up and 0/5 for granite4: hard
downward discrimination, none above 12B. Once h2 is graded correctly it
saturates as well, with three models at 5/5.

**Cross-document assembly did not produce ceiling resolution.** The apparent
h2 spread in the first write-up was an artefact of grading one reading of an
ambiguous question as correct. `gemma4:31b` at 2/5 is the only genuine
separation left, and it comes from the model not addressing the existence
question at all rather than from getting it wrong.

## Finding 2 — the question was ambiguous, and the grader picked a side

"Whether the mechanism that would permit it exists yet" has two defensible
readings, and the models split cleanly between them:

- **(a)** does a mechanism that *permits* status-setting exist? **No** — and
  `gemma4:26b` / `gemma4:12b` answered this, correctly.
- **(b)** is the crystal-attach machinery built? **Yes, 2026-07-18** — and
  `qwen3.6` / `qwen3.8` / `granite4` answered this, also correctly.

The `forbids` axis marked (b) a contradiction. It was written after reading
granite4's answer and encoded the assumption that any claim of implementation
was false — an assumption inherited from a stale line rather than checked
against the code. **`qwen3.8:27b` rep3 gave the most complete answer of any
model in the field** — "the mechanism that would permit it does not exist. The
spec for `crystal-attach` (Phase 1, implemented 2026-07-18) explicitly notes
that no `--status` [is] accepted" — joining both readings correctly. It was
graded FAIL_CONTRADICTS.

A probe whose question admits two correct answers cannot rank anything.

## Finding 3 — `qwen3.8:27b` is indistinguishable from `qwen3.6:27b` here

15/15 vs 15/15, identical per-probe. Preflight: `think=False` honored, 100% GPU
at `num_ctx 49152`, no CPU placement, 12.8s cold load. Architecturally it is a
point release — same `qwen35` arch, Q4_K_M, 262144 context, vision+tools+
thinking, 27.3B vs 27.8B.

The only visible difference is on h3, where 3.8 hit both bonus groups on all
five reps (`uid_isolated` *and* the Front H divergence) against 3.6's one. That
is a bonus-column signal on a saturated probe — suggestive, not a result.

**This instrument cannot rank 3.8 against 3.6.** The agentic ladder at E11's
config is the instrument that would, and it has not been run.

## What survives

- `granite4` (3.4B) is below the floor on h1 and h3 (0/5 each): the dashboard is
  "produced by the **Claude Code** agent"; h3 answered "**Yes**, the desktop can
  verify" with an invented `session_end --attach-crystal`. Those are real
  confabulations, unaffected by the retraction.
- `gemma4:31b` does not address the existence half of h2 in 4 of 5 samples under
  either reading.
- `gemma4:26b` remains the only model at 15/15 with zero flips across the
  original five-model field.

## The instrument's real defect

Across two grading passes this instrument produced **four paraphrase false
negatives**, **one negation false positive**, and **one wrong answer key** —
the last being the expensive one, because it inverted a finding rather than
suppressing a cell.

The lesson is not "widen the accept lists". It is that **the answer key must be
verified against the system, not against the documentation**. `AGENTS.md:90` was
treated as ground truth because it was declarative and recent-looking. One
`--help` invocation falsified it. Every future probe key needs that check before
any model is scored against it.

The citation check remains the sounder axis and still only covers fabricated
paths; prose claims are caught only by reading them.

## Action item for the repo (not an eval finding)

`operator-control-plane/AGENTS.md:90` states that
`CRYSTAL_LEDGER_INTEROP_SPEC.md` is an unimplemented draft. It is implemented.
Any agent cold-starting from AGENTS.md will conclude `crystal-attach` does not
exist. This misled a whole eval pass and will mislead the next reader.

## Limits

n=5, one machine, one funnel epoch, one prompt per probe. Six models; the wider
E11 field (`qwen3-vl:30b`, `qwen3:32b`, `qwen2.5-coder:14b`, `gemma3:27b`) has
not been run here. Not comparable to p1..p5 (different epochs, temperature 0).
`capped` cannot host these probes — it truncates BOTTLENECKS.md above both h1's
and h3's sources.
