# Short task clean, long task censored again — and the gap is unexplained

**Run:** 2026-09-11 21:06, desktop (i9-9900KF, 15.9 GB, RTX 2080 8 GB),
ollama 0.32.12, `gemma4:26b`, L2, n=4, num_ctx 16384, temp 0.8, think off.
Launched after the desktop was quieted (Chrome closed, swap 18%, load 0.88).
Conditions at launch are recorded in `CONDITIONS.md`, written before the run.

## Result

| task | trials (s) | caps | pass | warm mean (t2-t4) |
|---|---|---|---|---|
| constant-and-callers | 167.8, 51.4, 54.3, 46.1 | none | 4/4 | **50.6 s**, spread 1.18x |
| csv-summarize-repair | 305.2, 202.9, 493.4, **600.0** | t4 | 3/4 | **WITHHELD** |

Reference (`testbench-2080-e9-batch1`, ~15 GB host, n=3): short 41.3 s warm,
long 171.6 s warm.

## The long task is void for the second time, same cause

t4 hit `MAX_WALL_CLOCK_SECONDS = 600` (runner.py:261) exactly. A capped cell is
censored, not measured; any mean including it is arithmetic over a timeout.

**Quieting the desktop did not hold.** Swap climbed monotonically across the run
and never recovered:

    21:10  1,614 MB   cell 1
    21:19  3,964 MB   cell 5
    21:28  6,840 MB   cell 6
    21:33  8,146 MB   cell 8 starting
    21:35  8,191 MB   (100%)

Cause: **closing Chrome frees RAM but does not drain swap.** Linux never pages
back in proactively. `llama-server` had 4,525 MB of anonymous pages stuck in
swap; every touch during generation is a swap-in stall. Observed directly during
t3: GPU at 2% and 37 W, `si` at 66,553, no file writes for 100 s, RSS collapsed
from 4,381 MB to 3,067 MB. t3 recovered and finished at 493.4 s. t4 did not.

Because degradation was monotonic and the long task runs late, its trials are
systematically biased, not noisy. The short task ran at cells 1-4 while swap was
still 1.6-1.9 GB and is unaffected.

## The short task is usable, and its gap is UNEXPLAINED

50.6 s here against 41.3 s on the testbench, ~1.2x slower, on the same GPU.

Candidate explanations, all currently dead:

- **CPU.** No. i9-9900KF, 16 threads at 4,700 MHz avg, against an i3-9100F with
  4 cores. The desktop has the better processor.
- **Page cache holding the model blob.** No. This was the explanation offered
  during the session and it does not survive: the testbench had ~15 GB when it
  set the 41.3 s baseline, not the 32 GB it reports now. The RAM moved there with
  the 3090s on 2026-09-10 (`HARDWARE_TRANSFER.md`: "15 GB (32 GB after swap)").
- **Swap pressure.** Unlikely for this task — it ran while swap was still low.

**No mechanism is established. Do not publish one.**

## Consequence

- **The published 2080 row stays at Speed 0.27 with its n=2 caveat.** A Speed
  figure needs both tasks and only one is valid.
- A valid long-task number needs swap drained (`swapoff -a && swapon -a`, root)
  or ollama restarted, not merely Chrome closed.
- The clean way to settle the short-task gap is to re-run the baseline on the
  testbench **as it is now**, so both sides are measured in their current state
  rather than one against a remembered configuration.
