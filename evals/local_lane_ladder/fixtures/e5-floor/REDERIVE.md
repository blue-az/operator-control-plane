# Pack re-derive — `e5-floor`

**Verdict:** `PASS`
**Checked at:** 2026-08-13T02:46:48.612029+00:00
**Checker:** uid=971 user=operator-builder host=z13
**Pack path:** `/home/blueaz/operator-control-plane/evals/local_lane_ladder/fixtures/e5-floor`

## Checks

| Check | Result | Detail |
|---|---|---|
| state.results non-empty | **PASS** | n=90 |
| postcondition totals | **PASS** | 65/90 overall; models={'gemma4:12b': '17/18', 'gemma4:e4b': '13/18', 'granite4:latest': '8/18', 'llama3.1:8b': '9/18', 'qwen2.5-coder:14b': '18/18'} |
| RESULTS.md matches re-sum | **PASS** | sha256=e222a6686193f040… |
| trace completeness | **PASS** | expected=90 on_disk=90 missing=0 orphans=0 |
| state↔trace field consistency | **PASS** | mismatches=0 |
| state.trace basename | **PASS** | all basenames match naming convention (or absent) |
| model tags | **PASS** | observed=['gemma4:12b', 'gemma4:e4b', 'granite4:latest', 'llama3.1:8b', 'qwen2.5-coder:14b'] (no --expected-models) |
| machine provenance | **PASS** | counts={'desktop': 90} expected='desktop' |
| GPU residency (no CPU spill) | **PASS** | samples=41 all matrix models 100% GPU in every observation; by_model={'qwen2.5-coder:14b': {'gpu': 10}, 'gemma4:12b': {'gpu': 18}, 'gemma4:e4b': {'gpu': 22}, 'llama3.1:8b': {'gp… |
| trace git_rev coherence | **PASS** | revs={'1ef8364a459e0ab5ae409566eff6c49bbdc1a9ff': 90} |

## Re-derived postcondition totals (from state.json)

| Model | Pass | N | Rate |
|---|---:|---:|---:|
| `gemma4:12b` | 17 | 18 | 94% |
| `gemma4:e4b` | 13 | 18 | 72% |
| `granite4:latest` | 8 | 18 | 44% |
| `llama3.1:8b` | 9 | 18 | 50% |
| `qwen2.5-coder:14b` | 18 | 18 | 100% |

Overall: **65/90**

## Per-task × model

| Task | Model | Pass | N |
|---|---|---:|---:|
| `alias-add` | `gemma4:12b` | 6 | 6 |
| `alias-add` | `gemma4:e4b` | 1 | 6 |
| `alias-add` | `granite4:latest` | 0 | 6 |
| `alias-add` | `llama3.1:8b` | 0 | 6 |
| `alias-add` | `qwen2.5-coder:14b` | 6 | 6 |
| `config-value-change` | `gemma4:12b` | 6 | 6 |
| `config-value-change` | `gemma4:e4b` | 6 | 6 |
| `config-value-change` | `granite4:latest` | 6 | 6 |
| `config-value-change` | `llama3.1:8b` | 5 | 6 |
| `config-value-change` | `qwen2.5-coder:14b` | 6 | 6 |
| `function-add` | `gemma4:12b` | 5 | 6 |
| `function-add` | `gemma4:e4b` | 6 | 6 |
| `function-add` | `granite4:latest` | 2 | 6 |
| `function-add` | `llama3.1:8b` | 4 | 6 |
| `function-add` | `qwen2.5-coder:14b` | 6 | 6 |

## Digests

- `state.json` sha256: `b8b2e55a6aec16840fbaa8aed601c84edce4b52a6cf7341487921cb11607d4da`
- `RESULTS.md` sha256: `e222a6686193f040c5f7d64dc41547e811332817e4b24ccde878a143d56c8832`
- `ollama_ps_samples.log` sha256: `421570d9e2bba5fd23f59336cd72eb94d82d7a4812451a2657f9ccd34b815981`
- trace git_revs: `{'1ef8364a459e0ab5ae409566eff6c49bbdc1a9ff': 90}`
- machines: `{'desktop': 90}`

This report re-derives aggregates from retained artifacts only. It does not re-run models or re-grade discarded temp fixtures.
