# Pack re-derive — `e1x-27b`

**Verdict:** `PASS`
**Checked at:** 2026-08-13T02:46:48.417159+00:00
**Checker:** uid=971 user=operator-builder host=z13
**Pack path:** `/home/blueaz/operator-control-plane/evals/local_lane_ladder/fixtures/e1x-27b`

## Checks

| Check | Result | Detail |
|---|---|---|
| state.results non-empty | **PASS** | n=18 |
| postcondition totals | **PASS** | 14/18 overall; models={'gemma3:27b': '5/9', 'qwen3.6:27b': '9/9'} |
| RESULTS.md matches re-sum | **PASS** | sha256=91f6e8d0fd4d1325… |
| trace completeness | **PASS** | expected=18 on_disk=18 missing=0 orphans=0 |
| state↔trace field consistency | **PASS** | mismatches=0 |
| state.trace basename | **PASS** | all basenames match naming convention (or absent) |
| model tags | **PASS** | observed=['gemma3:27b', 'qwen3.6:27b'] (no --expected-models) |
| machine provenance | **PASS** | counts={'desktop': 18} expected='desktop' |
| GPU residency (no CPU spill) | **PASS** | samples=22 all matrix models 100% GPU in every observation; by_model={'qwen3.6:27b': {'gpu': 18}, 'gemma3:27b': {'gpu': 2}} |
| trace git_rev coherence | **PASS** | revs={'8041b19e039ac20dec1f301064844565db964f01': 18} |

## Re-derived postcondition totals (from state.json)

| Model | Pass | N | Rate |
|---|---:|---:|---:|
| `gemma3:27b` | 5 | 9 | 56% |
| `qwen3.6:27b` | 9 | 9 | 100% |

Overall: **14/18**

## Per-task × model

| Task | Model | Pass | N |
|---|---|---:|---:|
| `alias-add` | `gemma3:27b` | 3 | 3 |
| `alias-add` | `qwen3.6:27b` | 3 | 3 |
| `config-value-change` | `gemma3:27b` | 1 | 3 |
| `config-value-change` | `qwen3.6:27b` | 3 | 3 |
| `function-add` | `gemma3:27b` | 1 | 3 |
| `function-add` | `qwen3.6:27b` | 3 | 3 |

## Digests

- `state.json` sha256: `e3c35c7154ca39d3ef79d2c4051afb790df5d8c3858d451a39fb5ae0c4cde857`
- `RESULTS.md` sha256: `91f6e8d0fd4d13255fc53d5c353e4bb55415f5cd9a1eb3068bcead76d210ca5d`
- `ollama_ps_samples.log` sha256: `b81cbe192c24e1e1cb88224cba292f41561b89576521bde7bf29ee82681bc2dd`
- trace git_revs: `{'8041b19e039ac20dec1f301064844565db964f01': 18}`
- machines: `{'desktop': 18}`

This report re-derives aggregates from retained artifacts only. It does not re-run models or re-grade discarded temp fixtures.
