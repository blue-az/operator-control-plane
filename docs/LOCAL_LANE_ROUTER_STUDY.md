# Local-Lane Task Router Study: Route on Task Shape and Interaction Mode, Not Difficulty

**Status:** measured, single-run per model, v2 corpus (16 tasks, two axes)
**Date:** 2026-08-07
**Repo:** `operator-control-plane`
**Artifacts:** `~/Documents/local/routing/` (`corpus.json`, `route.py`, `results_gemma4_26b.json`, `results_gemma4_31b.json`)

## 1. Question

`opr` already tags dispatched tasks with a shaped-ness contract
(`goal-shaped` / `semi-shaped`). That tag is advisory prose. Can a **local
model produce the routing decision itself**, reliably and cheaply enough to
sit in front of dispatch — and which local model should hold that seat?

Hypothesis, from the same day's failures: **task shape predicts local-model
success better than task difficulty does.** `gemma4:31b` handled a
substantive blind-judging task well, then failed a trivial three-step git
task — not because git is harder, but because it required carrying state
across sequential tool calls.

A second axis was added after the operator observed that his ~20 tok/s
usability floor comes specifically from *conversational* `opr` use, and does
not apply to delegated work:

| | conversational | delegated |
|---|---|---|
| binding constraint | decode ≥ ~20 tok/s | completes without stalling |

## 2. Method

16 hand-labeled tasks (`corpus.json` v2) on two independent axes:

**Axis 1 — lane (shape):** `local_ok` (9), `needs_supervision` (4), `frontier` (3)
**Axis 2 — interaction_mode:** `conversational` (10), `delegated` (6)

Tasks are drawn from real observed cases where possible: T02 is the exact
three-step git task `gemma4:31b` measurably failed that day; T01 is the
blind-judging shape it measurably succeeded at. The corpus deliberately
includes a **discriminating pair** — T06/T13 (`local_ok` + conversational)
against T12 (`local_ok` + delegated) — identical lane, opposite mode, so mode
cannot be inferred from lane. It also probes the 1-tool-call band with T15
(read a local file) and T16 (current weather).

Mode ground truth is inferred from **natural phrasing cues** ("quick",
"mid-edit", "walk me through", "I'll read it tomorrow", "overnight", "ping me
when it's green"), not an explicit label. A production router would more
likely take mode as a flag; inferring it is the harder test.

Each model is asked, one task per call, for strict JSON:
`{"lane", "interaction_mode", "expected_tool_calls", "reason"}`.

A hardware-aware policy then converts classification into a concrete
assignment, using measured decode rates on this box (26b ≈ 40 tok/s,
31b ≈ 7 tok/s) against the operator's 20 tok/s conversational floor:

```
frontier lane                     -> frontier
needs_supervision lane            -> supervised
local_ok + conversational         -> models clearing 20 tok/s  (here: 26b only)
local_ok + delegated              -> any local model            (26b or 31b)
```

Harness choices carry the day's measured lessons rather than re-deriving
them: HTTP API not `ollama run` (the CLI emits ANSI spinner bytes and can
hang re-printing `> ` forever on EOF — cost 1.78 GB of log earlier that day);
`think: false` and `num_ctx: 12288` (exposed reasoning at ctx 4096 consumed
the whole budget and returned an *empty* response with
`done_reason: "length"`); one task per call with small expected output;
`temperature: 0`.

## 3. Results

| Model | Lane | Mode | Joint | **Assignment** | Parse fail | Wall | Decode |
|---|---:|---:|---:|---:|---:|---:|---:|
| `gemma4:26b` (MoE) | 16/16 | 16/16 | 16/16 | **16/16** | 0 | 57.3 s | 39.23 tok/s |
| `gemma4:31b` (dense) | 16/16 | 15/16 | 15/16 | **16/16** | 0 | 198.6 s | 6.67 tok/s |

Both models got **lane** perfect and emitted well-formed JSON on all 32
calls. Both got the discriminating pair right — T12 delegated, T06/T13
conversational — so mode is being read from phrasing, not inherited from lane.

**The router seat should be 26b.** Equal or better accuracy, 3.5x faster
wall-clock, 5.9x faster decode. Routing is not accuracy-limited here; it is
cost-limited, and there is no accuracy argument for spending 31b decode on it.

### 3.1 The one miss, and why the policy absorbed it

`gemma4:31b` labeled T02 (the git task) `conversational` instead of
`delegated`. Its stated reason was:

> *"Requires a sequence of dependent tool calls to modify and then verify state."*

That reason is entirely about **sequencing** — the lane axis. The model
reasoned correctly and then attached the wrong mode label; it is a labeling
slip, not a reasoning failure. T02 is also the only task in the corpus with
no phrasing cue for mode, so there was nothing to read.

Crucially, **assignment accuracy stayed 16/16 anyway**. Lane
`needs_supervision` routes to `supervised` regardless of mode, so the error
never reached the output. This generalises:

> **Mode is only load-bearing in the `local_ok` lane.** For
> `needs_supervision` and `frontier`, mode does not affect the assignment,
> so mode errors there are free.

That implies a cheap optimisation: **infer lane first, and only ask for mode
when lane is `local_ok`.** On this corpus that skips mode inference for 7 of
16 tasks.

### 3.2 Tool-call bands: a clean separator with one blind spot

| Lane | 26b estimates | 31b estimates |
|---|---|---|
| `local_ok` (n=9) | 0,0,0,0,0,0,0,0,**1** | 0,0,0,0,0,0,0,0,**1** |
| `frontier` (n=3) | **1**,2,**1** | **1**,**1**,**1** |
| `needs_supervision` (n=4) | 3,15,3,10 | 3,10,4,10 |

Two findings:

1. **`expected_tool_calls` cleanly separates `local_ok` from
   `needs_supervision`.** Every `local_ok` scored 0–1; every
   `needs_supervision` scored ≥ 3, under both models. The models disagreed
   on magnitude (T05: 15 vs 10) but never on which side of the boundary —
   the threshold is robust to that noise.
2. **It does *not* separate `local_ok` from `frontier`.** T15 (read
   `version.txt`) and T16 (current weather in Phoenix) both score 1 tool
   call and land in different lanes. The v1 study flagged the 1–2 band as
   unpinned; v2 now shows *why* it cannot be pinned by count alone. The
   missing signal is **data locality** — is the required information on this
   machine or on the network — which is orthogonal to how many calls it takes.

So tool count is a good `local_ok` / `needs_supervision` discriminator and a
useless `local_ok` / `frontier` one. A production router needs a second
feature for the latter.

## 4. Fourth independent confirmation of `gemma4:31b` decode rate

| Task domain | Decode |
|---|---:|
| Blind-judging (text ranking) | 6.3 tok/s |
| `opr` git task (tool-calling) | 6.67 tok/s |
| Routing v1 (classification) | 6.96 tok/s |
| Routing v2 (classification) | 6.67 tok/s |

Four measurements, three task domains, spread ~10%. This is a stable
hardware property of `gemma4:31b` on the Z13, not a task artifact.

## 5. Implications for dispatch

1. **Put 26b in the router seat.** Equal accuracy, 3.5x cheaper wall-clock.
2. **Emit `expected_tool_calls` as a numeric field**, not just a prose
   contract tag. `0–1` → local, `>= 3` → supervised.
3. **Add a data-locality feature** to resolve the 1–2 band; tool count alone
   cannot separate `local_ok` from `frontier` there.
4. **Gate mode inference on lane.** Only `local_ok` needs it; skip it
   otherwise and save the tokens.
5. **Do not route on estimated difficulty.** Nothing here needed it, and the
   day's failure data contradicts it.

## 6. Proof Boundary

This study shows:

- both models classify lane at 16/16 with zero malformed output across 32 calls
- both resolve the discriminating pair, so mode is read from phrasing cues
  rather than inherited from lane
- the assignment policy absorbed 31b's single mode error, demonstrating that
  mode is only load-bearing in `local_ok`
- `expected_tool_calls` separates `local_ok` from `needs_supervision` under
  both models, and demonstrably fails to separate `local_ok` from `frontier`
- a fourth decode measurement for `gemma4:31b` consistent with three priors

It does **not** show:

- **that the router survives genuinely ambiguous tasks.** 16/16 and 15/16 on
  a corpus written by the supervisor is still close to a ceiling. Every task
  has a defensible single answer; a production queue does not. The corpus is
  harder than v1 but has not been shown to be *hard*.
- **that phrasing-cue inference generalises.** Mode was inferred from cues
  this corpus deliberately supplies. T02 — the one task lacking a cue — is
  also the one that produced a mode error, which suggests the models are
  reading cues rather than reasoning about interaction mode from first
  principles. A corpus of cue-free tasks would likely score much worse.
- that routing accuracy predicts *execution* success. The router never
  executed anything; a correct `needs_supervision` label says nothing about
  whether the downstream model then completes the task.
- variance: n=1 run per model at `temperature 0`, no repeated trials.
- generalisation beyond these two models on this hardware, or to a corpus
  not authored by the person defining the ground truth.

## 7. Next Step

Two concrete follow-ups, in priority order:

1. **Cue-free mode corpus.** Strip the phrasing cues and re-run. Section 6
   predicts a significant mode-accuracy drop; if that holds, mode should be
   taken as an explicit dispatch flag rather than inferred, and the router
   should only be asked for lane.
2. **Adversarial lane corpus.** Tasks hard to *classify* rather than hard to
   *do*: a single tool call with a hidden dependency; a multi-step task whose
   steps are independent (parallelisable, arguably `local_ok`); a question
   answerable from parametric knowledge *or* the web; more 1–2 band cases on
   both sides of the local/frontier line.

## 8. Reproducing

```bash
cd ~/Documents/local/routing
python3 route.py gemma4:26b
python3 route.py gemma4:31b
```

Requires `ollama` serving locally with both models pulled. Results write to
`results_<model>.json` with per-task predictions on both axes, tool-call
estimates, the derived assignment, `done_reason`, and per-call decode rate.
