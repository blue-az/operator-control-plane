# E1 finding — the two qwen failures are a harness confound, not capability

**Run:** desktop, 2026-08-12, rev `90e91d7`, 27/27 cells, 27/27 traces retained,
100% GPU residency for all three models. **Not yet UID-verified.**

## Headline table (raw, as graded)

| Model | L2 pass | median wall | mean | max |
|---|---|---:|---:|---:|
| `gemma4:26b` | **9/9** | 6.4s | 10.2s | 27.5s |
| `gemma4:31b` | **9/9** | 19.0s | 18.5s | 31.3s |
| `qwen2.5-coder:14b` | **7/9** | 2.1s | 4.5s | 9.9s |

Zero timeouts, zero non-zero return codes. Both failures are
`config-value-change`, trials 1 and 2.

## Do not read 7/9 as a capability result

The retained traces show `qwen2.5-coder:14b` produced the **correct** edit in all
three trials. It only got *credit* in one.

Passing trial 3 — the harness recognises and dispatches the call:

```
[Model requests tool call: patch_file]
Arguments: { "tool": "patch_file", "path": "config/settings.ini",
             "target_content": "debug = false",
             "replacement_content": "debug = true" }
[Tool Output]
Successfully patched config/settings.ini.
```

Failing trials 1 and 2 — no `[Model requests tool call:]`, no `[Tool Output]`.
The model emitted the same JSON as **fenced prose**, which the harness printed
instead of executing, so the file was never modified and the postcondition
correctly reported `pattern not found: 'debug = true'`:

````
--- Output ---
```json
{ "tool": "patch_file", "path": "config/settings.ini",
  "target_content": "debug = false",
  "replacement_content": "debug = true" }
```
```json
{ "tool": "grep_search", "pattern": "^debug = true$", ... }
```
````

**The tool/path/target/replacement payload is byte-identical between the passing
and failing trials.** The only difference is whether the harness parsed the
emission as a tool call. Both failures also emit *two* fenced blocks in one
response (the edit plus a self-verification `grep_search`), which is the shape
that fails to parse; the passing trial emitted a single call.

So the failure mode is **tool-call emission format**, not wrong answers, and it
is **intermittent** for this model on this fixture (1 of 3).

## Why this is filed rather than reported as a score

GOLD_STANDARD §2 requires the grader read artifacts, not narration — it did, and
the grading is *correct*: no edit happened, so the cell fails. The defect is
upstream of grading. This is the same family as the 88 pre-`890d595` negatives
that could not be distinguished from harness truncation, and it is a **new,
post-`890d595` instance** of it. Per the failure-catalog rule in §2, it goes in
the catalog rather than into a model ranking.

Consequences:

1. **`gemma4:26b` 9/9 and `gemma4:31b` 9/9 stand** — unconfounded, and the two
   named seats both cleared L2 on every cell.
2. **The 14b floor-model row is confounded.** Do not cite "qwen2.5-coder:14b
   scores 7/9 at L2" as a capability finding. The honest statement is that its
   *answers* were right 3/3 and its *tool-call emission* parsed 1/3.
3. This does not reopen L0→L2 monotonicity or E0; it is a single-cell-class
   harness defect.

## What would settle it

Either a harness change that accepts fenced-JSON tool emissions (or explicitly
rejects them with a distinguishable error, so a parse failure never looks like a
wrong answer), or a re-run of the `config-value-change` × 14b cell at higher n to
measure the emission-format rate. Neither is in E1's scope.

**No claim is registered from this run.** MANIFEST requires a distinct-UID
re-derive of postcondition totals, trace completeness, model tags, residency and
machine provenance first. The traces, `state.json`, `RESULTS.md`, `evidence/`
(prerun provenance + 20s-interval `ollama ps` samples) are retained for exactly
that.
