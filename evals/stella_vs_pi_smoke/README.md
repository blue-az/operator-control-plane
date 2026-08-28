# stella-vs-pi smoke test (Terminal-Bench 2.1, 5 of 89 tasks)

**Status:** real, evidence-backed, single smoke run. **Deliberately never used or
published** — the sample is too thin to defend, and it was never the point. Recorded
here so the raw work isn't lost or half-remembered later, not as a benchmark claim.

## Origin

Stella (`~/Python/Evaluation/stella/`, see `../../../Python/Evaluation/eval-notes/stella.CLAUDE.md`)
ships its own preregistered head-to-head evidence at
`stella/bench/evidence/tb21-hh10-20260731/`: a matched run on **Terminal-Bench 2.1**
(89 tasks, one attempt each), Stella vs. Harbor's own Claude Code agent, both on
`z-ai/glm-5.2` via OpenRouter, same host, same session:

```
Arm A — Stella        58/89 = 65.17%
Arm B — Claude Code   44/89 = 49.44%
```

This surfaced from a LinkedIn post by Stella's author (Mac Anderson) citing that
result. Verified as legitimate directly against the repo's own preregistered,
hash-pinned evidence rather than trusting the post. The question that followed:
does the same hold for **pi** (`~/Python/Evaluation/pi-mono/`,
`@earendil-works/pi-coding-agent`, MIT, by badlogic) — a different terminal
coding-agent CLI in the same category?

## Method

Running the *exact* same methodology (Harbor-driven, full 89 tasks) against pi
wasn't a quick rerun. What was actually available:

- Harbor (the framework Terminal-Bench 2.1 runs on) wasn't installed on this
  machine — installed fresh into `pi-mono/.harbor-venv` for this test.
- Stella needed a **custom** Harbor adapter (`bench/harbor_adapter/stella_harbor`)
  since it's third-party. **Pi ships with a native, built-in Harbor adapter**
  (`harbor/agents/installed/pi.py`) — no adapter work needed.
- Real infra friction along the way, none of it a pi or Harbor bug: Docker Compose
  plugin missing (installed to `~/.docker/cli-plugins/`, no sudo), then a
  SELinux-driven container write-permission failure on the bind-mounted logs dir
  (fixed with `chcon`, no sudo, no policy change).

Given the infra cost of a full 89-task run (~$50-100+, an hour+), the decision was
a **5-task smoke test first** — the 5 *cheapest* tasks from Stella's own published
run (`distribution-search`, `prove-plus-comm`, `fix-git`, `polyglot-rust-c`,
`extract-elf`), same dataset pin
(`terminal-bench/terminal-bench-2-1@sha256:7d7bdc1c...`), same model
(`openrouter/z-ai/glm-5.2`), for a true apples-to-apples slice.

## Result

**pi, 5/5 passed:**

| task | reward | cost | tokens in/out | note |
|---|---:|---:|---:|---|
| `distribution-search` | 1.0 | $0.0949 | 121,152 / 18,153 | |
| `prove-plus-comm` | 1.0 | $0.0224 | 26,877 / 4,256 | |
| `fix-git` | 1.0 | $0.0132 | 22,862 / 1,684 | |
| `polyglot-rust-c` | 1.0 | $0.1778 | 177,415 / 35,719 | |
| `extract-elf` | 1.0 | $0.2087 | 262,500 / 38,642 | hit the 900s agent timeout, but had already satisfied the verifier before being killed |

Total: **5/5, $0.5170** (`evidence/harbor_result.json`).

**Stella, same 5 tasks, from its own published `tb21-hh10` run:**

| task | reward | tool calls | cost |
|---|---:|---:|---:|
| `distribution-search` | 1.0 | 4 | $0.0575 |
| `prove-plus-comm` | 1.0 | 8 | $0.0167 |
| `polyglot-rust-c` | 1.0 | 4 | $0.1689 |
| `fix-git` | **0.0** | 11 | $0.0261 |
| `extract-elf` | **0.0** | 11 | $0.0925 |

Total: **3/5, $0.3617**.

On this slice: pi 5/5 vs. Stella 3/5, at ~43% higher spend.

## Why this is not a claim, and won't become one without a full re-run

1. **N=5, not 89 — and not random.** These were picked as Stella's own *cheapest*
   tasks specifically to keep the smoke test fast, which is a selection bias in
   pi's favor for cost, not a neutral sample. Extrapolating "pi beats stella" from
   this is exactly the mistake both tools' own cultures argue against — Stella's
   `AGENTS.md` itself states a 5-task result "cannot resolve anything smaller than
   a catastrophe."
2. **`extract-elf`'s pi pass is soft.** It burned the full 900s agent timeout and
   was killed mid-run; it happened to have already satisfied the verifier by then.
   Not the same as a clean, timely completion.
3. **No tool-call comparison possible.** Harbor's built-in pi adapter doesn't
   report a tool-call count the way Stella's own accounting does — a real data
   gap in the table above, not a zero.
4. **Never posted, and shouldn't be without the full run.** The one thing that did
   get used publicly from this whole investigation was a different, lower-stakes
   piece of feedback to Stella's author about his own GLM-5.2-vs-GLM-5.2 framing —
   not this comparison.

**If this gets picked up again:** the honest next step is the full 89-task run
(real cost, real time), not citing this smoke test as if it were one.

## Evidence

- `evidence/harbor_result.json` — top-level Harbor run summary (5 trials, 1 error/timeout, $0.5170 total)
- `evidence/<task>__<id>/{result.json,trial.log,config.json}` — per-trial detail, one dir per task
- Stella's own published comparator data lives in the (untracked, read-only) clone:
  `~/Python/Evaluation/stella/bench/evidence/tb21-hh10-20260731/`
- Raw Harbor job directory (not copied here, larger container artifacts):
  `~/Python/Evaluation/pi-mono/.harbor-jobs/pi-smoke-5task/`
