# Pack re-derive — `e4-sampled`

**Verdict:** `PASS`
**Checked at:** 2026-08-13T02:46:48.561201+00:00
**Checker:** uid=971 user=operator-builder host=z13
**Pack path:** `/home/blueaz/operator-control-plane/evals/local_lane_ladder/fixtures/e4-sampled`

## Checks

| Check | Result | Detail |
|---|---|---|
| state.results non-empty | **PASS** | n=63 |
| postcondition totals | **PASS** | 62/63 overall; models={'gemma3:27b': '9/9', 'gemma4:26b': '8/9', 'gemma4:31b': '9/9', 'qwen2.5-coder:14b': '9/9', 'qwen3-vl:30b': '9/9', 'qwen3.6:27b': '9/9', 'qwen3:32b': '9/9'} |
| RESULTS.md matches re-sum | **PASS** | sha256=b185a8e1188963ba… |
| trace completeness | **PASS** | expected=63 on_disk=63 missing=0 orphans=0 |
| state↔trace field consistency | **PASS** | mismatches=0 |
| state.trace basename | **PASS** | all basenames match naming convention (or absent) |
| model tags | **PASS** | observed=['gemma3:27b', 'gemma4:26b', 'gemma4:31b', 'qwen2.5-coder:14b', 'qwen3-vl:30b', 'qwen3.6:27b', 'qwen3:32b'] (no --expected-models) |
| machine provenance | **PASS** | counts={'desktop': 63} expected='desktop' |
| GPU residency (no CPU spill) | **PASS** | samples=78 all matrix models 100% GPU in every observation; by_model={'qwen3.6:27b': {'gpu': 21}, 'gemma4:26b': {'gpu': 5}, 'gemma4:31b': {'gpu': 8}, 'qwen3:32b': {'gpu': 14}, '… |
| trace git_rev coherence | **PASS** | revs={'8f6ccca74945cc7907b924d40b6974e5de5582eb': 63} |

## Re-derived postcondition totals (from state.json)

| Model | Pass | N | Rate |
|---|---:|---:|---:|
| `gemma3:27b` | 9 | 9 | 100% |
| `gemma4:26b` | 8 | 9 | 89% |
| `gemma4:31b` | 9 | 9 | 100% |
| `qwen2.5-coder:14b` | 9 | 9 | 100% |
| `qwen3-vl:30b` | 9 | 9 | 100% |
| `qwen3.6:27b` | 9 | 9 | 100% |
| `qwen3:32b` | 9 | 9 | 100% |

Overall: **62/63**

## Per-task × model

| Task | Model | Pass | N |
|---|---|---:|---:|
| `alias-add` | `gemma3:27b` | 3 | 3 |
| `alias-add` | `gemma4:26b` | 2 | 3 |
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

- `state.json` sha256: `61e62003c622a2a5ce6eade6aee6b7e55395f34e678417a4ae406b6565aa6f56`
- `RESULTS.md` sha256: `b185a8e1188963ba3afc403c410a4dc1e44695bd45cac160b4e975b8fdddbcff`
- `ollama_ps_samples.log` sha256: `49415f04fca148cfabdfb98960f29faff828fc25375f56129a697cdd9b1dca62`
- trace git_revs: `{'8f6ccca74945cc7907b924d40b6974e5de5582eb': 63}`
- machines: `{'desktop': 63}`

This report re-derives aggregates from retained artifacts only. It does not re-run models or re-grade discarded temp fixtures.
