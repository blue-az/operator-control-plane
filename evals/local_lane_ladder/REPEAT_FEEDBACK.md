# `--on-repeat feedback` — experimental mode, first result

**Added:** 2026-08-13, desktop. **Default is unchanged** (`stop`), so every pack
`e1`–`e9` keeps its meaning and remains comparable.

## Why

Repetition is the largest failure mode this harness measures. In
`e9-ceiling-continued`: **61 of 210 cells** hit the repeat-guard, and
`no_blind_repeat` was the most-violated trajectory rule. A hard stop cannot
distinguish two very different situations:

- the model is **genuinely stuck** and repeating is the symptom, or
- the model **lost the tool result from context** and is re-fetching it.

`--on-repeat feedback` hands the prior result back and lets the loop continue,
bounded by `--max-repeat-feedback` (default 3) so a truly stuck model still
terminates. The repeated call is **not** re-executed — otherwise a repeated
`run_command` would run twice.

## A/B result, three affected cell classes, n=6 each

| Cell class | | pass | repeat-stops | edit calls | mean calls |
|---|---|---:|---:|---:|---:|
| `csv` × `gemma4:26b` | stop | 0/6 | 5/6 | 5 | 3.7 |
| | **feedback** | **2/6** | **0/6** | **11** | 4.8 |
| `csv` × `gemma4:31b` | stop | 0/6 | 5/6 | 5 | 2.8 |
| | **feedback** | **0/6** | **0/6** | **10** | 4.0 |
| `constant-and-callers` × `qwen3.6:27b` | stop | 5/6 | 1/6 | 17 | 4.0 |
| | **feedback** | **6/6** | **0/6** | 18 | 4.2 |

## What this establishes, and what it does not

**The mechanism works, reliably.** Repeat-stops went to **0/6 in all three**
classes, and edit calls roughly doubled where they had been suppressed
(5 → 11, 5 → 10). The models were being cut off mid-task, and feeding the result
back does let them continue. That part is consistent across every arm.

**The outcome does not follow.** Aggregate 5/18 → 8/18. One class improved
(0/6 → 2/6), one did not move at all (0/6 → 0/6), and one moved by a single cell
(5/6 → 6/6) which is within noise at n=6.

`csv` × `gemma4:31b` is the informative arm: repeat-stops eliminated, edit calls
doubled, **and still 0/6**. The model gets unstuck, makes its edits, and remains
unable to solve the task. So on that cell class repetition was a *symptom* of not
being able to solve it, not a cause of failing to.

**The honest summary is that this separates two things that used to be
conflated.** Where repetition is a context problem, feedback recovers the run.
Where repetition is a symptom of incapacity, feedback removes the symptom and
changes nothing. Both now show up distinctly in the trace, which they could not
before.

## Recommendation

- **Do not change the default.** The evidence for an outcome improvement is one
  cell class at n=6, which under `MSC-RUL-107` is nowhere near enough to revise a
  finding, let alone a default.
- **Do use it as a diagnostic.** Running an affected cell class both ways now
  answers "stuck, or just lost the context?" in one A/B, and that question was
  previously unanswerable.
- **Worth a proper epoch** at higher n across all affected classes if the
  question is whether local models are being under-measured by the guard. The
  mechanism evidence is already strong enough to justify that spend.

## Limits

Three cell classes, n=6, one machine, one prompt shape. Seeds are not honoured on
this stack so these are independent draws. The `stop` arms reproduce E9's
repeat-stop rates but not its exact pass counts, which is ordinary
cross-invocation variance and another reason to treat the outcome numbers as
weak.
