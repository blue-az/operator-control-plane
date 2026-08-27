# Map probe — five asked facets, length and time recorded

**Run:** desktop, 2026-08-15, 24/24 cells, think off, ctx 16384, temp 0.8,
`--no-bn` (glossary not injected). Workspace = live copies of `AGENTS.md`,
`CLAUDE.md`, `BOTTLENECKS.md`, `ONBOARDING.md`, `README.md` only.
**Not UID-verified.**

Pass gate is 5/5 sourced facets in the **final answer** only. Tool dumps
are not scored. Word count and wall-clock are recorded, not the gate.

## Result

| Model | 5/5 | Mean facets | Mean s | Median s | Mean words | Mean ctok | Mean calls |
|---|---:|---:|---:|---:|---:|---:|---:|
| `gemma4:26b` | 0/6 | **2.8** | **9.6** | 6.9 | 110 | 350 | 2.8 |
| `qwen3.6:27b` | 0/6 | 1.7 | 31.2 | 33.0 | **278** | **614** | 4.2 |
| `qwen3.8:27b` | 0/6 | 0.0 | 15.5 | 12.1 | 11 | 129 | 3.8 |
| `gemma4:31b` | 0/6 | 0.0 | 8.7 | 5.2 | 15 | 45 | 2.0 |

Facet hits:

| Model | what_for | names | authority | open_now | read_first |
|---|---:|---:|---:|---:|---:|
| `gemma4:26b` | 6/6 | 0/6 | 6/6 | 5/6 | 0/6 |
| `qwen3.6:27b` | 3/6 | 0/6 | 5/6 | 2/6 | 0/6 |
| `qwen3.8:27b` | 0/6 | 0/6 | 0/6 | 0/6 | 0/6 |
| `gemma4:31b` | 0/6 | 0/6 | 0/6 | 0/6 | 0/6 |

Nobody cleared 5/5. The names facet needs Bulkhead + BN/BOTTLENECKS +
Operator + project-phoenix in the *answer*; that lives in `AGENTS.md` /
`BOTTLENECKS.md`, which 26b never opened.

## What each model actually did

**`gemma4:26b` answered the brief.** ~110 words, ~7s after the cold first
cell. Read `README.md` + `ONBOARDING.md` (once only README). Hit purpose,
authority, and current LabWired/Grafana work. Missed the glossary because
it did not open BN/AGENTS, and said so ("public line not in the provided
files"). That is concise-and-sourced on the files it chose, not a collapse.

**`qwen3.8:27b` read the right files and never answered.** Four of six
cells opened `AGENTS.md` and `BOTTLENECKS.md`, then the final span is a
preamble ("I'll explore the workspace…"). Two cells are Ollama 500s
(INFRA). Same stall as ledger-gate pass 3: reconnaissance, no synthesis.
This is **not** the interactive session where it wrote the long brief —
that harness forces a final message. opr does not.

**`gemma4:31b`** 6/6 stopped on a repeated `list_dir: .` after reading
README. No answer. Repeat-guard, not a short style.

**`qwen3.6:27b`** longest (278 words, 31s) and often *wrong workspace*:
treated the text as an operator-control-plane log or said the repo was
empty after having read AGENTS.md. Verbose is not the same as sourced.

## Length vs score

26b is shortest among models that answered, and has the highest facet
mean. 3.6 is longest and not better on the asked list. 3.8 looks short
only because the recorded "answer" is a preamble, not a brief.

## Limits

n=6, one machine, opr tool loop, governing-docs workspace not the full
tree. 2/24 cells are serving 500s. Keyword facets can miss a correct
paraphrase of Bulkhead/BN; 26b's names miss is real (it never opened
those files), not a grader false negative on a synonym.
