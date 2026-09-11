# A 5.48x dual/solo ratio at configured capacity 131072, with approximately 12.8k prompt tokens

**Run:** desktop, 2026-09-08. `hw_standard.py`, Standard A, loaded regime,
n=3 per cell, `qwen3.8:27b`. This is a **configured-capacity sweep**, not a
prompt-length sweep. Solo placement was not captured; causal interpretation is
provisional. Review/protocol: `docs/REVIEW_CALL_singlecard-and-ctx-depth_2026-09-08.md`.

## Recorded results

Actual prompt counts are **12,837** for dual ctx16384/32768 and **12,838**
for all other rows. Input length is approximately fixed, not capacity-sized.
VRAM values are MiB. Nominal headroom (24576 minus recorded solo VRAM) falls
from 5669 to **2339 MiB** at capacities 16384 to 65536; the previously reported
1979 endpoint does not rederive from those totals.

| config | decode tok/s | prefill ms/token | VRAM total |
|---|---:|---:|---:|
| dual ctx16384 | 62.8 | 0.865 | 20,424 |
| dual ctx32768 | 60.5 | 0.872 | 21,896 |
| dual ctx65536 | 60.8 | 0.872 | 24,844 |
| dual ctx131072 | 61.4 | 0.888 | 28,644 |
| solo ctx16384 | 55.1 | 0.872 | 18,907 |
| solo ctx32768 | 57.8 | 0.872 | 20,027 |
| solo ctx65536 | 56.4 | 0.872 | 22,237 |
| solo ctx131072 | 11.2 | 1.573 | 22,823 |

## Scoped observation

At capacity 131072, dual/solo is **61.4/11.2 = 5.48x**. At capacity 16384,
`(solo/dual - 1)*100` is **-12.3% in this sweep**, versus **-8.0% in the
separate rank run**. These percentages use solo relative to dual, not the reverse.

The observed ratio does not measure decode with a 131,072-token prompt or the
reported 72,113-token median interactive turn. Dual decode varies from 60.5 to
62.8 tok/s as configured capacity changes at fixed input; this is not evidence
that increasing actual prompt length costs no speed.

Solo prefill at capacities 16384/32768/65536 is approximately 0.872 ms/token
within the stored 0.1-second timing precision, not measured exactly identical.
The result weakens the tested headroom prediction but is not a general causal
falsification.

## Provisional residency explanation and CPU-layer cost

The solo slowdown at the highest capacity is consistent with a placement change,
but the solo rows record `layers: None`. The historical instrument read the
systemd journal rather than the solo daemon's log. Later instrumentation cannot
supply missing historical placement evidence.

Dividing the 5,821 MiB dual/solo difference proportionally across 66 layers gives
about 13 hypothetical CPU layers. Dividing the approximately 71.6 ms/token
slowdown by that estimate gives about **5.5 ms/layer**. This is conditional
arithmetic, **not a measured layer count or isolated CPU-layer cost**. VRAM
includes KV and buffers; a memory difference need not scale with layer count.
Comparison with the separately measured 1.34 ms/layer gemma curve is provisional.

Neither the residency mechanism nor a hardware purchase conclusion is verified.
Placement-captured confirmation is pending and must follow the corrected review
protocol, using daemon-specific layer logs plus per-device memory capture;
`/api/ps` alone is insufficient. No new live measurement accompanies this correction.
