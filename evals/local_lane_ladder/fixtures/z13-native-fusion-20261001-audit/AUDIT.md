# Z13 native Fusion v2 cohort audit

**Status:** PASS for packet completeness, request/weight gates, stored UMA placement captures, and deterministic regrading. This is a separate native Fusion/tool-use workload—not a Local Lane repair-quality result and not a global model ranking.

## Canonical evidence

Artifacts remain on Z13; no native tool/database traces were copied into this repository:

- `~/fusion-native-z13-20261001/` — C1 Qwen3.6-35B configuration completed; the campaign then stopped at the next configuration because slot erase returned HTTP 501.
- `~/fusion-native-z13-20261001-r2/` — completed remaining configurations after adding the required `--slot-save-path` argument.

The first packet's attempted Qwen3.8 configuration has only a start identity capture and no scored request/result; exclude it. Qwen3.8's scored cohort is the complete r2 configuration.

## Audit checks

- Four complete configurations, each with the six-task × six-trial grid (36 cells): Qwen3.6-35B C1/Ollama, Qwen3.8-27B F1/Prism, Bonsai-27B F1/Prism, and Gemma4-26B C1/Ollama.
- Recomputed all 144 trace grades with the frozen packet grader: **129 pass, 15 fail, 0 unproven**; no stored outcome or grade mismatch. The frozen model-free contract test passed.
- All 409 request-gate records passed. The 349 cell-linked request records reconcile as a subset of those logs; the remaining 60 are canary requests. Pinned request fields matched. Prism launch arguments and Ollama parameter layers matched their sampler/context contracts.
- Model-weight start/end captures matched each other and the configured model hash for every completed configuration.
- Revalidated all 288 pre/post placement snapshots using the packet's UMA validator: all passed, with no mismatch. Foreign GPU use was 544.2 MiB, below the declared 1,536 MiB ceiling. Recorded profiles were AC/balanced. The stored `gpu-resident` label reflects weight-allocation ratio; the capture explicitly does **not** prove zero CPU offload and is only a bracketed snapshot, not continuous telemetry.

| Z13 configuration | Result under frozen six-task grader |
|---|---:|
| Qwen3.6-35B C1/Ollama | 30/36 |
| Qwen3.8-27B F1/Prism | 33/36 |
| Bonsai-27B F1/Prism | 36/36 |
| Gemma4-26B C1/Ollama | 30/36 |

## Scope and qualifications

- C1 used Z13's own Qwen3.6 and Gemma4 seat weights, not the Testbench C1 blobs. Prism and Ollama are distinct serving profiles. Do not pool these rows or claim a cross-profile winner.
- The cohort is not the 90-cell repair battery; do not add it to the public Local Lane repair table. No public page was changed.
- The run log includes a weather-enrichment schema warning (`temperature_avg` column absent). The separate weather-analysis tool returned success with source counts in the scored trials, but the frozen weather grader checks tool use and source separation—not independent numerical correctness of every summarized value. Treat that task result as a structured behavior measure, not a validated weather-statistics claim.
- Raw native traces and database-derived values remain on Z13. This audit records only aggregate outcomes and integrity checks.
