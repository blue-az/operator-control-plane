# qwen3.6:35b host-conditioned L2 — three-fixture look, not E9

**Run:** desktop, 2026-08-15T06:06:47Z, rev `18611de`, 54/54 cells, 54/54
traces. `num_ctx 16384`, temp 0.8, think off. Same-run: `gemma4:26b`,
`qwen3.6:27b`. **Not UID-verified.** Placement sampled every 30s. Speed
row is now on the desktop ranking (`q36-35b-spill-tps`). This pack is
still **not** an E9 Elo row — wrong fixture set (3 vs 5) — and is **not**
a seat change. G2 no longer forbids running the full battery.

Question: does 35b-with-spill win L2 merit on this host.

## Result

| Model | total | anchor | csv | logfmt | place (samples) |
|---|---:|---:|---:|---:|---|
| `gemma4:26b` | **12/18** | **6/6** | 0/6 | **6/6** | 4/4 `100% GPU` |
| `qwen3.6:35b` | 9/18 | 3/6 | 0/6 | **6/6** | 2/4 `100%`, 2/4 `4%/96%` |
| `qwen3.6:27b` | 8/18 | **6/6** | 0/6 | 2/6 | 8/8 `100% GPU` |

`csv-summarize-repair` was floor for everyone this invocation (0/18), same
`food=45.44/46.44` miss. It does not rank these three here.

## What 35b did

It is **3.6:27b plus the log-format contract**, not 26b. `strict-log-format`
6/6 vs 27b’s 2/6 is the same split 3.8 showed against 3.6 (instruction
fidelity, not a new reasoning band). `ambiguous-anchor` is the other way:
26b and 27b 6/6, 35b **3/6** (first three fail, last three pass — it
patched more than the named heading).

Wall-clock on passing cells is in the 26b band after load, not the 27b csv
slog (27b 21–55s on csv fails; 35b 9–15s on the same fail). Decode 86 tok/s
with 4% spill shows up as *usable* cell time. It does not buy the missing
anchor cells.

## Placement

35b sat on the lip during the pack: half the `ollama ps` samples were
`100% GPU` (22 GB), half `4%/96%` (23 GB). 26b and 27b never left 100%.
That is why this stays a **desktop-spill host row**. The 4% did not make
35b unusable. It also did not make it the seat.

## Limits

n=6, one machine, one invocation. csv is uninformative this run (keep it
as the known ceiling marker; 27b has passed it in E11). Do not fold these
9/18 into E9 — wrong fixture set, not because of spill. Seat remains
`gemma4:26b`. The remaining hole is the E9 five-fixture battery for 35b
with a same-run 26b control. z13 replica is a separate pack.
