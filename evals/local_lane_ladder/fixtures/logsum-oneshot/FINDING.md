# logsum one-shot — 3.6 writes the contract when opr is gone

**Run:** desktop, 2026-08-15T07:44:41Z, 18/18 cells, think off, ctx 16384,
no opr. Same `check_logsum.py` as the ladder. **Not UID-verified.**

## Result

| Model | pass | nicer `1 error` | left stub | other |
|---|---:|---:|---:|---:|
| `qwen3.6:27b` | **6/6** | 0 | 0 | 0 |
| `qwen3.8:27b` | 5/6 | 0 | 0 | 1 (`got []`) |
| `gemma4:26b` | **6/6** | 0 | 0 | 0 |

Nobody beautified. The ugly `"09: 1 errors"` string is not the 3.6 miss
when the file is in the prompt.

## Against the ladder

E11 `strict-log-format`: 3.6 **2/12**, almost all `NotImplementedError`.
3.8 **15/18**. That split is **tool-loop completion** (3.6 reads and does
not patch), not format IQ. One-shot inverts it: 3.6 is 6/6, 3.8 5/6.

The q38-ladder sentence that 3.6 “solves the counting and ships a nicer
format” does not hold on this path. 3.8’s one miss here is empty output
(`[]`), a logic slip, not a singular.

## Limits

n=6, one prompt, extract-from-markdown. This is not a seat. It says the
3.6/3.8 log-format gap is **harness-expressed** (opr write), not a missing
ability to emit the contract.
