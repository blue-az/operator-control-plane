# Pack re-derive — `e3-controlled`

**Verdict:** `PASS`
**Checked at:** 2026-08-13T02:46:48.512064+00:00
**Checker:** uid=971 user=operator-builder host=z13
**Pack path:** `/home/blueaz/operator-control-plane/evals/local_lane_ladder/fixtures/e3-controlled`

## Checks

| Check | Result | Detail |
|---|---|---|
| state.results non-empty | **PASS** | n=63 |
| postcondition totals | **PASS** | 60/63 overall; models={'gemma3:27b': '9/9', 'gemma4:26b': '6/9', 'gemma4:31b': '9/9', 'qwen2.5-coder:14b': '9/9', 'qwen3-vl:30b': '9/9', 'qwen3.6:27b': '9/9', 'qwen3:32b': '9/9'} |
| RESULTS.md matches re-sum | **PASS** | sha256=f23d3f3c912db686… |
| trace completeness | **PASS** | expected=63 on_disk=63 missing=0 orphans=0 |
| state↔trace field consistency | **PASS** | mismatches=0 |
| state.trace basename | **PASS** | all basenames match naming convention (or absent) |
| model tags | **PASS** | observed=['gemma3:27b', 'gemma4:26b', 'gemma4:31b', 'qwen2.5-coder:14b', 'qwen3-vl:30b', 'qwen3.6:27b', 'qwen3:32b'] (no --expected-models) |
| machine provenance | **PASS** | counts={'desktop': 63} expected='desktop' |
| GPU residency (no CPU spill) | **PASS** | samples=89 all matrix models 100% GPU in every observation; by_model={'qwen2.5-coder:14b': {'gpu': 2}, 'gemma4:26b': {'gpu': 5}, 'gemma3:27b': {'gpu': 2}, 'qwen3.6:27b': {'gpu':… |
| trace git_rev coherence | **PASS** | revs={'8f6ccca74945cc7907b924d40b6974e5de5582eb': 63} |

## Re-derived postcondition totals (from state.json)

| Model | Pass | N | Rate |
|---|---:|---:|---:|
| `gemma3:27b` | 9 | 9 | 100% |
| `gemma4:26b` | 6 | 9 | 67% |
| `gemma4:31b` | 9 | 9 | 100% |
| `qwen2.5-coder:14b` | 9 | 9 | 100% |
| `qwen3-vl:30b` | 9 | 9 | 100% |
| `qwen3.6:27b` | 9 | 9 | 100% |
| `qwen3:32b` | 9 | 9 | 100% |

Overall: **60/63**

## Per-task × model

| Task | Model | Pass | N |
|---|---|---:|---:|
| `alias-add` | `gemma3:27b` | 3 | 3 |
| `alias-add` | `gemma4:26b` | 0 | 3 |
| `alias-add` | `gemma4:31b` | 3 | 3 |
| `alias-add` | `qwen2.5-coder:14b` | 3 | 3 |
| `alias-add` | `qwen3-vl:30b` | 3 | 3 |
| `alias-add` | `qwen3.6:27b` | 3 | 3 |
| `alias-add` | `qwen3:32b` | 3 | 3 |
| `config-value-change` | `gemma3:27b` | 3 | 3 |
| `config-value-change` | `gemma4:26b` | 3 | 3 |
| `config-value-change` | `gemma4:31b` | 3 | 3 |
| `config-value-change` | `qwen2.5-coder:14b` | 3 | 3 |
| `config-value-change` | `qwen3-vl:30b` | 3 | 3 |
| `config-value-change` | `qwen3.6:27b` | 3 | 3 |
| `config-value-change` | `qwen3:32b` | 3 | 3 |
| `function-add` | `gemma3:27b` | 3 | 3 |
| `function-add` | `gemma4:26b` | 3 | 3 |
| `function-add` | `gemma4:31b` | 3 | 3 |
| `function-add` | `qwen2.5-coder:14b` | 3 | 3 |
| `function-add` | `qwen3-vl:30b` | 3 | 3 |
| `function-add` | `qwen3.6:27b` | 3 | 3 |
| `function-add` | `qwen3:32b` | 3 | 3 |

## Digests

- `state.json` sha256: `f2094f3e578f49a29d1b1822ed4319507f028a9e1bb0b5715ce9462b1735129c`
- `RESULTS.md` sha256: `f23d3f3c912db686384677f4a91c8f0b2679979a703ae2a8dc9fae1e6909138c`
- `ollama_ps_samples.log` sha256: `db33f4d3968d248fb5f0585eec5c0b1ff236d4df538c8d43e7ccb0b2a742d40a`
- trace git_revs: `{'8f6ccca74945cc7907b924d40b6974e5de5582eb': 63}`
- machines: `{'desktop': 63}`

This report re-derives aggregates from retained artifacts only. It does not re-run models or re-grade discarded temp fixtures.
