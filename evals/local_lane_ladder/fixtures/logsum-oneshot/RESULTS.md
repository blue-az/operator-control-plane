# logsum one-shot — no opr

File in the prompt. Grade is `check_logsum.py`. think off, ctx 16384.

| model | t | kind | rc | src_ch | think_ch |
|---|---:|---|---:|---:|---:|
| `qwen3.6:27b` | 1 | pass | 0 | 1218 | 0 |
| `qwen3.6:27b` | 2 | pass | 0 | 1083 | 0 |
| `qwen3.6:27b` | 3 | pass | 0 | 1316 | 0 |
| `qwen3.6:27b` | 4 | pass | 0 | 1245 | 0 |
| `qwen3.6:27b` | 5 | pass | 0 | 1137 | 0 |
| `qwen3.6:27b` | 6 | pass | 0 | 1090 | 0 |
| `qwen3.8:27b` | 1 | wrong_strings | 1 | 1313 | 0 |
| `qwen3.8:27b` | 2 | pass | 0 | 1051 | 0 |
| `qwen3.8:27b` | 3 | pass | 0 | 1062 | 0 |
| `qwen3.8:27b` | 4 | pass | 0 | 1010 | 0 |
| `qwen3.8:27b` | 5 | pass | 0 | 1002 | 0 |
| `qwen3.8:27b` | 6 | pass | 0 | 379 | 0 |
| `gemma4:26b` | 1 | pass | 0 | 1202 | 0 |
| `gemma4:26b` | 2 | pass | 0 | 1394 | 0 |
| `gemma4:26b` | 3 | pass | 0 | 1371 | 0 |
| `gemma4:26b` | 4 | pass | 0 | 1332 | 0 |
| `gemma4:26b` | 5 | pass | 0 | 1354 | 0 |
| `gemma4:26b` | 6 | pass | 0 | 1418 | 0 |

## Totals

| model | pass | nicer_singular | left_stub | other |
|---|---:|---:|---:|---:|
| `qwen3.6:27b` | 6/6 | 0 | 0 | 0 |
| `qwen3.8:27b` | 5/6 | 0 | 0 | 1 |
| `gemma4:26b` | 6/6 | 0 | 0 | 0 |
