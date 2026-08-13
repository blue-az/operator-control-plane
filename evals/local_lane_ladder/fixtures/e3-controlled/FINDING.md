# E3 finding — temperature 0 is not a neutral control

**Run:** desktop, 2026-08-13, rev `8f6ccca`, 63/63 cells, 63/63 traces,
zero CPU spill. **Retained as an artifact record, NOT as a model comparison.** **UID-verified 2026-08-13** (pack integrity, 60/63) by uid 971 via `claim-0018`.

Raw result: six models 9/9; `gemma4:26b` 6/9, with all three failures on
`alias-add` and all three via the repeat-guard.

That 6/9 is an artifact of the control, not a quality measure. Greedy decoding
locks an agentic loop into re-issuing an identical tool call, which the
repeat-guard correctly stops. Measured directly on the affected cell:

| Setting | `gemma4:26b` × `alias-add` |
|---|---|
| temperature 0 | **1/6** |
| temperature 0.8 | **6/6** |

Temperature 0 buys reproducibility by introducing a failure mode absent from
real use, and it penalises loop-prone models specifically. It should not be used
for agentic-loop evaluation.

The reproducibility it was meant to buy is also unavailable: `seed` is not
reliably honoured by this Ollama build (same seed, different output on a
high-entropy prompt).

Superseded as a comparison by `e4-sampled/` (same matrix at temperature 0.8).
The equalised system prompt introduced here was correct and is retained there.
