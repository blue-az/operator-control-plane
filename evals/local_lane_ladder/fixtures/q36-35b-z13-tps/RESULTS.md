# q36-35b z13 tok/s

Same meter as desktop_sweep / q36-35b-spill-tps. Trial 1 cold; 2–3 warm.
Power: {'ac0_online': '1', 'bat0_status': 'Full', 'governor': 'powersave', 'powerprofile': 'balanced'}

| model | ctx | t | cold | tok/s | gen | place | load s |
|---|---:|---:|---:|---:|---:|---|---:|
| `qwen3.6:35b` | 16384 | 1 | 1 | 60.9 | 96 | 100% GPU | 8.1 |
| `qwen3.6:35b` | 16384 | 2 | 0 | 59.7 | 92 | 100% GPU | 0.3 |
| `qwen3.6:35b` | 16384 | 3 | 0 | 58.7 | 94 | 100% GPU | 0.3 |
| `qwen3.6:35b` | 32768 | 1 | 1 | 61.1 | 104 | 100% GPU | 8.1 |
| `qwen3.6:35b` | 32768 | 2 | 0 | 59.3 | 117 | 100% GPU | 0.3 |
| `qwen3.6:35b` | 32768 | 3 | 0 | 57.8 | 95 | 100% GPU | 0.3 |
| `gemma4:26b` | 16384 | 1 | 1 | 57.4 | 123 | 100% GPU | 7.2 |
| `gemma4:26b` | 16384 | 2 | 0 | 56.2 | 128 | 100% GPU | 0.4 |
| `gemma4:26b` | 16384 | 3 | 0 | 54.2 | 128 | 100% GPU | 0.4 |
| `gemma4:26b` | 32768 | 1 | 1 | 56.4 | 124 | 100% GPU | 7.2 |
| `gemma4:26b` | 32768 | 2 | 0 | 56.1 | 128 | 100% GPU | 0.4 |
| `gemma4:26b` | 32768 | 3 | 0 | 54.4 | 128 | 100% GPU | 0.4 |

| model | ctx | place (last) | warm mean tok/s |
|---|---:|---|---:|
| `qwen3.6:35b` | 16384 | 100% GPU | **59.2** |
| `qwen3.6:35b` | 32768 | 100% GPU | **58.5** |
| `gemma4:26b` | 16384 | 100% GPU | **55.2** |
| `gemma4:26b` | 32768 | 100% GPU | **55.2** |
