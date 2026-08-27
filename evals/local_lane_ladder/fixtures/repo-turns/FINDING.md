# repo-turns — 31b does not take fewer turns

**Run:** desktop, 2026-08-16, 30/30 cells, 30/30 traces, n=3,
`num_ctx 16384 · temperature 0.8 · think off`. Five Evaluation repos,
agent files stripped in the temp copy. **Not UID-verified.** Not Elo.
Does not revise the `gemma4:26b` seat.

## Result

Both models **15/15**. The hypothesis (31b fewer tool calls on a foreign
tree with no agent files) is **not supported** on this instrument.

| Task | 26b pass | 26b mean calls | 31b pass | 31b mean calls |
|---|---:|---:|---:|---:|
| `bothread-lease-ttl` | 3/3 | 2.0 | 3/3 | 2.0 |
| `code-stick-github-url` | 3/3 | **2.0** | 3/3 | **4.0** |
| `groundtruth-web-port` | 3/3 | 2.0 | 3/3 | 2.0 |
| `ollm-utf8-sig` | 3/3 | **3.0** | 3/3 | **3.3** |
| `projectkitty-snippet-lines` | 3/3 | 2.0 | 3/3 | 2.0 |

Pooled passing-cell calls: 26b **2.2**, 31b **2.66**. 31b is never cheaper.
On `code-stick` it is twice as expensive: grep → patch `package.json` →
grep → patch `src/utils/logger.ts`. 26b greps once and patches the logger.

`ollm` t3 is the only 31b miss-then-retry: a second `patch_file` on
`utils.py` failed (already edited). Still passed.

## Quality (A / B / C)

Same shape as the z13 pack (`characterization/RESULTS.md`): one
programmatic grader, three writers. Full table: `QUALITY.md`.

| | writer | repo-turns | z13 29-task |
|---|---|---:|---:|
| A | 31b | 0.91 | **0.96** |
| B | 26b n=1 | **1.00** | 0.93 |
| C | 26b best-of-N | **1.00** | 0.95 |

31b won on z13 (codegen + longctx). Here `required` saturates; 31b drops
on scope (`package.json`) and one failed retry. Do not pool the two
overalls.

## What this does not say

The L1 prompts **named the symbol**. Both models grep it and patch. That
is a 2-call floor, and four of five tasks sat on it. It does not test the
informal observation (31b fewer turns on underspecified live work). That
would need L0, or a multi-file repair, or a task that does not name the
identifier.

Wall-clock still belongs to 26b (warm ~3–6s vs 31b ~7–18s). Do not rank
turns from wall-clock.

## Limits

n=3, one machine, five one-line edits, symbol-named L1. Saturated: 30/30
pass. Live Eval trees were not mutated.
