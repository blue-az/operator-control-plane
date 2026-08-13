# E1X finding — 27B-class capacity extension

**Run:** desktop, 2026-08-12, rev `8041b19`, 18/18 cells, 18/18 traces,
100% GPU residency for both models, zero CPU-spill samples. **UID-verified 2026-08-13** (pack integrity) by uid 971 on z13 ledger via `claim-0018`. Raw totals in `REDERIVE.md`; confounds in this FINDING stand.

Sibling pack to `e1-gold-pack/`. Same three L2 fixtures, same grader, same
harness — only the model list differs. E1's 27-cell matrix is **not** modified;
its MANIFEST fixes that matrix, and it is already filed with evidence hashes.

## Why these two models qualify

`GOLD_STANDARD.md` §3 seats 27–32B as "capacity unlock (dual later) — same
fixtures only, then claim tests better", and E1's non-goals bar adding a
**spilling** model. Both models here load at **17 GB / 100% GPU / 32768 ctx** on
the single 24 GB RTX 3090, verified before the run and sampled every 20s during
it. No dual-GPU requirement, no spill. The gate is met.

## Raw results

| Model | L2 pass | median | mean | max |
|---|---:|---:|---:|---:|
| `qwen3.6:27b` | **9/9** | 23.7s | 40.4s | 126.1s |
| `gemma3:27b` | 5/9 | 3.3s | 6.2s | 13.8s |

## The 5/9 is mostly the same confound as E1

Classified from the retained traces by whether the harness ever dispatched a tool:

| Cell | Classification |
|---|---|
| `config-value-change` t1 | **Confound** — never dispatched |
| `config-value-change` t3 | **Confound** — never dispatched |
| `function-add` t3 | **Confound** — never dispatched |
| `function-add` t2 | **Real defect** — tool ran, output wrong |

Three of the four `gemma3:27b` failures are the *same* emission-format defect
catalogued in `e1-gold-pack/FINDING.md`. It emitted correct bare JSON as prose,
which the harness printed instead of executing:

```
--- Output ---
{"tool": "patch_file", "path": "config/settings.ini",
 "target_content": "debug = false", "replacement_content": "debug = true"}
{"tool": "grep_search", "pattern": "debug = true", "path": "config/settings.ini"}
```

No `[Model requests tool call:]`, no `[Tool Output]`, so no edit occurred. Note
this variant is **bare** JSON, where the 14b case was fenced — the harness fails
to parse both. `function-add` t3's `ImportError: cannot import name 'square'` has
the same cause: nothing was ever written.

**One failure is genuine.** `function-add` t2 dispatched correctly and produced
broken code — it anchored on `    return a + b` and emitted a replacement that
left a dangling copy of that line after the new function, causing an
`IndentationError`:

```
"replacement_content": "\n\ndef square(n):\n    return n * n\n\n    return a + b"
```

That is a real anchored-edit failure and counts against the model.

## Honest restatement

Excluding cells the harness never dispatched, on **gradeable** cells only:

| Model | Gradeable | Confounded cells |
|---|---:|---:|
| `gemma4:26b` | 9/9 | 0 |
| `gemma4:31b` | 9/9 | 0 |
| `qwen3.6:27b` | 9/9 | 0 |
| `qwen2.5-coder:14b` | 7/7 | 2 |
| `gemma3:27b` | **5/6** | 3 |

## ROOT CAUSE FOUND AND FIXED (2026-08-12, later same day)

The mechanism is **not** fenced-vs-bare JSON, as first written below. It is the
number of objects in the response. `opr`'s `extract_json_tool_call` matched
`re.search(r"\{.*\}", text, re.DOTALL)` — a **greedy** span from the first `{`
to the last `}`. A response carrying two objects (an edit plus a
self-verification read) produced a span covering both plus the text between
them, which is not valid JSON. Extraction returned `None` and the caller
returned the raw text as a final answer.

Verified against all 45 retained traces: **all 5 non-dispatched cells emitted
exactly 2 tool-shaped objects, and no single-object response ever failed to
dispatch.** Fencing was incidental — both fenced and bare two-object responses
failed, and both single-object forms succeeded.

Fixed by scanning for the first *balanced* object with `JSONDecoder.raw_decode`
instead of a greedy regex, plus an explicit `[No tool dispatched: ...]` marker
so tool-shaped output that yields no call can never again be mistaken for a
prose answer. Direct A/B on the verbatim failing payloads: old returns `None`,
new returns the correct `patch_file` call. Covered by
`tests/test_opr_tool_extraction.py` (10 tests) using the trace payloads verbatim.

**This creates a harness epoch boundary.** Results in this pack and in
`e1-gold-pack/` are **pre-fix** and are not comparable to anything run after it,
exactly as the pre-`890d595` results are not comparable to these. Do not pool
them.

A post-fix re-run of the 12 affected cells passed 12/12, but that is
*consistent with* the fix rather than proof of it — the models emitted single
calls in that run, so the two-object path was not exercised. The A/B and the
unit tests are the causal evidence. Note also that `gemma3:27b`'s genuine
`function-add` t2 defect passed on re-run; that is run-to-run variance, **not**
something the fix addressed.

## The confound is not model-family-specific

This is the finding that matters beyond the scores. Across all 45 cells run
today, the emission defect appeared in **two different model families**
(`qwen2.5-coder:14b` and `gemma3:27b`) and never in `gemma4:26b`, `gemma4:31b`,
or `qwen3.6:27b`. E1 alone could not distinguish "a Qwen quirk" from "a harness
defect"; two families failing the same way, and both newer models of *both*
families passing cleanly, is much stronger evidence for the harness reading.

The apparent pattern — older model generations emit bare/fenced JSON, newer ones
emit parseable tool calls — is a **hypothesis, not a result**. It rests on 5
confounded cells across 2 models and was not designed for. It does suggest the
parser is tuned to what current models happen to emit, which is a fragile place
for a grading harness to sit.

## Speed

`qwen3.6:27b` is accurate but **slow**: median 23.7s against `gemma4:26b`'s 6.4s,
with a 126.1s outlier — roughly 4x the median and 20x the worst case. For
delegated work that is irrelevant; for anything interactive it is not.
`gemma3:27b` is the fastest of the five (median 3.3s) and the least reliable.

## Relation to the earlier qwen3.6:27b probe

An informal TSMC-question judge probe earlier the same day had `qwen3.6:27b`
misranking answers and inventing factual "corrections". That probe was explicitly
marked non-citable — no deterministic postcondition, single self-reported
ranking, no trace. These results do **not** contradict it: this instrument
measures plan-shaped tool execution, that one poked at evaluative judgment. A
model can be reliable at anchored edits and unreliable as a judge. Do not merge
the two into one ranking.

## Claim boundary

**Pack integrity claimed via `claim-0018` (UID-verified).** Historical bar was a distinct-UID re-derive of postcondition
totals, trace completeness, model tags, residency and machine provenance comes
first. Wall-clock was taken at a 320 W cap and is not comparable to the 220 W
throughput packets.
