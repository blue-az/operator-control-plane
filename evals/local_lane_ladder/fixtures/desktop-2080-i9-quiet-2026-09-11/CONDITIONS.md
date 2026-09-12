# Machine conditions at launch (recorded before the run, not after)

Desktop, i9-9900KF, RTX 2080 8 GB, ollama 0.32.12, driver 580.178.04.

| | void run (20:23) | this run (21:06) |
|---|---:|---:|
| free RAM | 259 MB | **6,004 MB** |
| available | ~8,900 MB | **13,043 MB** |
| swap used | 8,114 / 8,191 (99%) | **1,514 / 8,191 (18%)** |
| load avg (1m) | 10.31 | **0.88** |
| chrome | 564 MB across processes | **not running** |
| vmstat si/so | 9,972 / 88,500 | **~0 sustained** |
| GPU at launch | model resident | **250 MiB, clear** |

**Scope, stated up front.** This measures the RTX 2080 *in this machine*. It is
NOT a like-for-like comparison against `testbench-2080-e9-batch1`: that host has
**32 GB** RAM, this one has 15.9 GB. That difference is uncontrolled and quiet
does not fix it. The earlier claim that the two "match at 15 GB" was wrong and
invalidated the run-2 comparison.

**Known hazard.** `MAX_WALL_CLOCK_SECONDS = 600` (runner.py:261). A 600.0 s cell
is censored, not measured. Two cells hit it in run 2. Any mean including a capped
cell is arithmetic over timeouts.
