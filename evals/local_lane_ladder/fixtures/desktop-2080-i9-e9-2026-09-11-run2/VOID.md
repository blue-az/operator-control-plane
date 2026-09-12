# VOID as a speed measurement — routing fix verified, numbers not usable

**Run:** 2026-09-11, desktop (i9-9900KF, 15.9 GB RAM, RTX 2080), ollama 0.32.12,
`gemma4:26b` base tag, L2, n=4, num_ctx 16384, temp 0.8, think off.

## What this run DID establish (keep)

- **Routing is fixed and proven local.** During the run the local daemon at
  `127.0.0.1:11434` held the model while `testbench.local:11434` stayed empty,
  and `llama-server` ran with `--host 127.0.0.1` against the local blob store.
- **Placement: `offloaded 31/31 layers to GPU`**, 7,418 MiB resident, plus a
  5/5-layer MTP drafter. Reproduces the original 2080 placement.

## Why the wall clock is void

**1. The comparison was invalid from registration.** The prediction asserted the
testbench "matches at 15 GB RAM and differs only in CPU." **The testbench now has
32 GB, but did not when it set the baseline** - the RAM moved with the cards on
2026-09-10. The reference numbers are from a ~15 GB host that no longer exists. Measured live: 32,032 MB with 125/975 MB swap used, against this box's
15,906 MB with 8,114/8,191 MB swap used (99%) and ~200-330 MB free RAM. The
15 GB figure was carried from the June FINDING.md header and never re-checked.

**2. The machine was thrashing while measuring.** `llama-server` alone held
4.75 GB RSS (29%). `vmstat` showed sustained paging. Since boot: pswpout
16,279,660 here against 2,907,310 on the testbench.

**3. Stalls, not work, drive the variance.** `constant-and-callers` t1 and t3
did identical work (9 turns, 8 tools, comparable text) and differ 1.6x:
97.7 s vs 60.5 s. Testbench trials were work-consistent (9/8 on all three), which
is why its numbers were interpretable.

**4. Two cells are censored, not measured.** `csv-summarize-repair` t3 and t4
recorded 600.0 s and 600.1 s and FAILED — the harness wall-clock cap, not a
duration. Any mean over them (the naive "549.0 s") is arithmetic over timeouts.

## Results as recorded, for the record only

| task | trials | pass |
|---|---|---|
| constant-and-callers | 97.7, 62.6, 60.5, 75.7 | 4/4 |
| csv-summarize-repair | 123.3, 446.9, **600.0 cap**, **600.1 cap** | 2/4 |

## Prediction scoring (registered in HANDOFF_2026-09-06.md before the run)

| # | Outcome |
|---|---|
| R1 | **Falsified.** Predicted faster on both tasks; short task 66.3 s warm vs testbench 41.3 s, 1.6x slower. Premise (CPU is the only difference) was false. |
| R2 | **Untestable.** Long task censored at the cap. |
| R3 | **Falsified.** Predicted Speed in 0.27-1.00; short task alone gives 13.0/66.3 = 0.20. |
| R4 | **Held.** 31/31 layers on GPU, 7,418 MiB. |
| R5 | **Falsified.** Predicted 8/8; got 6/8. Cause is the 600 s cap, not capability. |

**The published 2080 row stays at Speed 0.27 with its n=2 caveat. Nothing here
replaces it.**

## The timeout was predicted in writing, three months early

`testbench-2080-e9-batch1/FINDING.md`: "csv-summarize-repair at 330 s is over
half the harness's 600 s timeout, so a slower model on that task could time out
on the bench while passing on the desktop. That would look like a capability
difference and would not be one." It came true on the desktop instead.

## To do this properly

Quiet the desktop (close Chrome, relieve swap) or run it headless. Even then it
compares a 15.9 GB box to a 32 GB one, so it answers "2080 in this machine," not
"2080 vs 3090 on equal footing."
