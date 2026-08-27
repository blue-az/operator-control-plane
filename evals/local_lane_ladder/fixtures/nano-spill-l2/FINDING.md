# nemotron-3-nano host-conditioned L2 — fast, empty

**Run:** desktop, 2026-08-15T06:41:13Z, rev `18611de`, 54/54 cells, 54/54
traces. `num_ctx 16384`, temp 0.8, think off. Same-run: `gemma4:26b`,
`qwen3.6:27b`. **Not UID-verified.** Not Elo. Not a seat change. Not pooled
with E9/E11 or `q36-35b-spill-l2`.

Decode prior (`nano-spill-tps`): warm **121.2** tok/s at 7% spill vs 26b
127.4 / 31b 34.4. This pack asks whether that speed buys L2.

## Result

| Model | total | anchor | csv | logfmt | place |
|---|---:|---:|---:|---:|---|
| `gemma4:26b` | **11/18** | **6/6** | 0/6 | **5/6** | 5/5 `100% GPU` |
| `qwen3.6:27b` | 9/18 | **6/6** | **1/6** | 2/6 | 11/11 `100% GPU` |
| `nemotron-3-nano:latest` | **0/18** | 0/6 | 0/6 | 0/6 | 2/2 `7%/93%` |

## What nano did

It is **not 31b-slow**. Warm cells fail in **2.3–2.5s**. The 7% spill is
visible and irrelevant.

It is **not a seat**. All 18 fails are missing implementation, not timeouts:

- `ambiguous-anchor` 0/6 — same extra-heading patch as 35b’s misses
- `csv-summarize-repair` 0/6 — parser never handles the quoted `$` field
  (`float('"\$1')`)
- `strict-log-format` 0/6 — `error_report` left as `NotImplementedError`

26b and 27b still pass the fixtures they usually pass. 27b even landed **1/6**
on csv this invocation (the ceiling marker, not a ranking).

## Read against 35b

Same host, same three fixtures, n=6: 35b **9/18** (logfmt 6/6, anchor 3/6).
Nano **0/18**. Decode class does not predict L2. 35b is 3.6-plus-contract;
nano is a fast skip.

## Limits

n=6, one machine. Placement samples for nano are sparse because cells were
short. Do not fold 0/18 into Elo. Seat remains `gemma4:26b`.
