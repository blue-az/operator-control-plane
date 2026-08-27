# spill tok/s

Same meter as `desktop_sweep.py`: `eval_count/eval_duration`, think off, 128 tokens.
Trial 1 is cold load; 2–3 are warm. Not Elo. Not a seat.

| model | ctx | t | cold | tok/s | gen | place | load s | smi |
|---|---:|---:|:---:|---:|---:|---|---:|---|
| `nemotron-3-nano:latest` | 16384 | 1 | 1 | 119.2 | 128 | 7%/93% CPU/GPU | 22.9 | 22964 MiB, 24576 MiB, 58 %, 265.07 W |
| `nemotron-3-nano:latest` | 16384 | 2 | 0 | 121.7 | 114 | 7%/93% CPU/GPU | 0.2 | 22964 MiB, 24576 MiB, 58 %, 250.33 W |
| `nemotron-3-nano:latest` | 16384 | 3 | 0 | 120.8 | 126 | 7%/93% CPU/GPU | 0.2 | 22964 MiB, 24576 MiB, 57 %, 270.92 W |
| `gemma4:26b` | 16384 | 1 | 1 | 122.8 | 121 | 100% GPU | 16.9 | 18488 MiB, 24576 MiB, 92 %, 224.14 W |
| `gemma4:26b` | 16384 | 2 | 0 | 127.3 | 128 | 100% GPU | 0.5 | 18488 MiB, 24576 MiB, 92 %, 292.19 W |
| `gemma4:26b` | 16384 | 3 | 0 | 127.6 | 128 | 100% GPU | 0.5 | 18488 MiB, 24576 MiB, 92 %, 276.58 W |
| `gemma4:31b` | 16384 | 1 | 1 | 34.3 | 118 | 100% GPU | 19.9 | 21362 MiB, 24576 MiB, 97 %, 319.09 W |
| `gemma4:31b` | 16384 | 2 | 0 | 34.5 | 105 | 100% GPU | 0.5 | 21362 MiB, 24576 MiB, 98 %, 317.60 W |
| `gemma4:31b` | 16384 | 3 | 0 | 34.4 | 120 | 100% GPU | 0.5 | 21362 MiB, 24576 MiB, 96 %, 318.52 W |

## Warm mean (trials 2–3)

| model | ctx | place | n | mean tok/s |
|---|---:|---|---:|---:|
| `gemma4:26b` | 16384 | 100% GPU | 2 | 127.4 |
| `gemma4:31b` | 16384 | 100% GPU | 2 | 34.5 |
| `nemotron-3-nano:latest` | 16384 | 7%/93% CPU/GPU | 2 | 121.2 |
