# Map probe — results

Generated from 24 trial records. Machine: desktop.
Pass = all five asked facets sourced in the final answer.
Length and time are recorded; they are not the gate.

## Per cell

| Model | Trial | Pass | Facets | s | words | chars | ctok | ptok | calls | rounds | files_read |
|---|---:|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| gemma4:26b | 1 | FAIL | 3/5 | 26.1 | 131 | 1295 | 432 | 3944 | 3 | 4 | README.md,ONBOARDING.md |
| gemma4:26b | 2 | FAIL | 3/5 | 7.3 | 125 | 1228 | 415 | 3944 | 3 | 4 | README.md,ONBOARDING.md |
| gemma4:26b | 3 | FAIL | 3/5 | 6.4 | 112 | 1006 | 335 | 3944 | 3 | 4 | README.md,ONBOARDING.md |
| gemma4:26b | 4 | FAIL | 3/5 | 6.9 | 112 | 1161 | 379 | 3944 | 3 | 4 | README.md,ONBOARDING.md |
| gemma4:26b | 5 | FAIL | 2/5 | 4.1 | 62 | 492 | 176 | 2071 | 2 | 3 | README.md |
| gemma4:26b | 6 | FAIL | 3/5 | 6.7 | 115 | 1093 | 366 | 3944 | 3 | 4 | README.md,ONBOARDING.md |
| gemma4:31b | 1 | FAIL | 0/5 | 26.3 | 15 | 110 | 45 | 2071 | 2 | 3 | README.md |
| gemma4:31b | 2 | FAIL | 0/5 | 5.6 | 15 | 110 | 45 | 2071 | 2 | 3 | README.md |
| gemma4:31b | 3 | FAIL | 0/5 | 5.0 | 15 | 110 | 45 | 2071 | 2 | 3 | README.md |
| gemma4:31b | 4 | FAIL | 0/5 | 5.2 | 15 | 110 | 45 | 2071 | 2 | 3 | README.md |
| gemma4:31b | 5 | FAIL | 0/5 | 5.1 | 15 | 110 | 45 | 2071 | 2 | 3 | README.md |
| gemma4:31b | 6 | FAIL | 0/5 | 5.1 | 15 | 110 | 45 | 2071 | 2 | 3 | README.md |
| qwen3.8:27b | 1 | FAIL | 0/5 | 40.2 | 14 | 85 | 270 | 15236 | 5 | 6 | README.md,AGENTS.md,BOTTLENECKS.md |
| qwen3.8:27b | 2 | FAIL | 0/5 | 12.7 | 8 | 53 | 130 | 14305 | 4 | 5 | README.md,AGENTS.md,BOTTLENECKS.md |
| qwen3.8:27b | 3 | FAIL | 0/5 | 11.3 | 12 | 81 | 102 | 14260 | 4 | 5 | README.md,AGENTS.md,BOTTLENECKS.md |
| qwen3.8:27b | 4 | FAIL | 0/5 | 9.4 | 12 | 102 | 44 | 1982 | 3 | 3 | README.md,AGENTS.md |
| qwen3.8:27b | 5 | FAIL | 0/5 | 12.1 | 10 | 59 | 182 | 14260 | 4 | 5 | README.md,AGENTS.md,BOTTLENECKS.md |
| qwen3.8:27b | 6 | FAIL | 0/5 | 7.1 | 12 | 102 | 45 | 1982 | 3 | 3 | README.md,CLAUDE.md |
| qwen3.6:27b | 1 | FAIL | 0/5 | 33.0 | 64 | 376 | 161 | 14260 | 4 | 5 | README.md,AGENTS.md,BOTTLENECKS.md |
| qwen3.6:27b | 2 | FAIL | 2/5 | 36.0 | 435 | 3453 | 918 | 14260 | 4 | 5 | README.md,AGENTS.md,BOTTLENECKS.md |
| qwen3.6:27b | 3 | FAIL | 1/5 | 29.5 | 317 | 2403 | 677 | 14305 | 4 | 5 | README.md,AGENTS.md,BOTTLENECKS.md |
| qwen3.6:27b | 4 | FAIL | 1/5 | 23.0 | 202 | 1623 | 471 | 14260 | 4 | 5 | README.md,AGENTS.md,BOTTLENECKS.md |
| qwen3.6:27b | 5 | FAIL | 3/5 | 30.4 | 240 | 1912 | 605 | 16590 | 5 | 6 | README.md,CLAUDE.md,AGENTS.md,BOTTLENECKS.md |
| qwen3.6:27b | 6 | FAIL | 3/5 | 35.5 | 412 | 3259 | 855 | 14260 | 4 | 5 | README.md,AGENTS.md,BOTTLENECKS.md |

## Per model

| Model | Pass | Mean s | Median s | Mean words | Mean ctok | Mean calls |
|---|---:|---:|---:|---:|---:|---:|
| gemma4:26b | 0/6 | 9.6 | 6.9 | 110 | 350 | 2.8 |
| gemma4:31b | 0/6 | 8.7 | 5.2 | 15 | 45 | 2.0 |
| qwen3.8:27b | 0/6 | 15.5 | 12.1 | 11 | 129 | 3.8 |
| qwen3.6:27b | 0/6 | 31.2 | 33.0 | 278 | 614 | 4.2 |

## Facet hit rate

| Model | what_for | names | authority | open_now | read_first |
|---|---:|---:|---:|---:|---:|
| gemma4:26b | 6/6 | 0/6 | 6/6 | 5/6 | 0/6 |
| gemma4:31b | 0/6 | 0/6 | 0/6 | 0/6 | 0/6 |
| qwen3.8:27b | 0/6 | 0/6 | 0/6 | 0/6 | 0/6 |
| qwen3.6:27b | 3/6 | 0/6 | 5/6 | 2/6 | 0/6 |
