# gemma4:26b VRAM envelope (24 / 16 / 12 / 8 / CPU)

Same meter as desktop_sweep. `num_gpu` layer cap. Trial 1 cold; 2–3 warm.

| tag | t | cold | tok/s | place | load s | smi |
|---|---:|---:|---:|---|---:|---|
| `full-24gb` | 1 | 1 | 122.2 | 100% GPU | 11.4 | 18533 MiB, 24576 MiB, 92 %, 301.84 W |
| `full-24gb` | 2 | 0 | 126.2 | 100% GPU | 0.5 | 18495 MiB, 24576 MiB, 92 %, 293.02 W |
| `full-24gb` | 3 | 0 | 125.0 | 100% GPU | 0.5 | 18495 MiB, 24576 MiB, 60 %, 305.82 W |
| `razor-16.5gb` | 1 | 1 | 96.8 | 11%/89% CPU/GPU | 10.1 | 16881 MiB, 24576 MiB, 69 %, 286.01 W |
| `razor-16.5gb` | 2 | 0 | 100.1 | 11%/89% CPU/GPU | 0.5 | 16843 MiB, 24576 MiB, 68 %, 291.68 W |
| `razor-16.5gb` | 3 | 0 | 100.1 | 11%/89% CPU/GPU | 0.5 | 16843 MiB, 24576 MiB, 61 %, 291.69 W |
| `cap-16gb` | 1 | 1 | 71.6 | 14%/86% CPU/GPU | 9.9 | 15709 MiB, 24576 MiB, 43 %, 243.52 W |
| `cap-16gb` | 2 | 0 | 72.4 | 14%/86% CPU/GPU | 0.5 | 15708 MiB, 24576 MiB, 45 %, 243.71 W |
| `cap-16gb` | 3 | 0 | 70.3 | 14%/86% CPU/GPU | 0.5 | 15709 MiB, 24576 MiB, 40 %, 241.79 W |
| `cap-12gb` | 1 | 1 | 34.1 | 39%/61% CPU/GPU | 8.5 | 11655 MiB, 24576 MiB, 17 %, 144.52 W |
| `cap-12gb` | 2 | 0 | 34.2 | 39%/61% CPU/GPU | 0.5 | 11696 MiB, 24576 MiB, 22 %, 146.83 W |
| `cap-12gb` | 3 | 0 | 34.6 | 39%/61% CPU/GPU | 0.5 | 11657 MiB, 24576 MiB, 21 %, 145.82 W |
| `cap-8gb` | 1 | 1 | 23.2 | 62%/38% CPU/GPU | 7.0 | 7501 MiB, 24576 MiB, 8 %, 131.20 W |
| `cap-8gb` | 2 | 0 | 23.1 | 62%/38% CPU/GPU | 0.5 | 7501 MiB, 24576 MiB, 8 %, 132.04 W |
| `cap-8gb` | 3 | 0 | 23.2 | 62%/38% CPU/GPU | 0.5 | 7501 MiB, 24576 MiB, 8 %, 132.15 W |
| `floor-cpu` | 1 | 1 | 12.9 | 100% CPU | 22.0 | 401 MiB, 24576 MiB, 2 %, 37.60 W |
| `floor-cpu` | 2 | 0 | 12.9 | 100% CPU | 0.6 | 440 MiB, 24576 MiB, 2 %, 43.48 W |
| `floor-cpu` | 3 | 0 | 12.9 | 100% CPU | 0.5 | 401 MiB, 24576 MiB, 2 %, 37.83 W |

| tag | place | warm mean tok/s | vs full |
|---|---|---:|---:|
| `full-24gb` | 100% GPU | **125.6** | 1.0 |
| `razor-16.5gb` | 11%/89% CPU/GPU | **100.1** | 0.8 |
| `cap-16gb` | 14%/86% CPU/GPU | **71.3** | 0.57 |
| `cap-12gb` | 39%/61% CPU/GPU | **34.4** | 0.27 |
| `cap-8gb` | 62%/38% CPU/GPU | **23.1** | 0.18 |
| `floor-cpu` | 100% CPU | **12.9** | 0.1 |
