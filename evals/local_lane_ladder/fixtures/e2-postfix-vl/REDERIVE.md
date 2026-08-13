# Pack re-derive — `e2-postfix-vl`

**Verdict:** `PASS`
**Checked at:** 2026-08-13T02:46:48.464305+00:00
**Checker:** uid=971 user=operator-builder host=z13
**Pack path:** `/home/blueaz/operator-control-plane/evals/local_lane_ladder/fixtures/e2-postfix-vl`

## Checks

| Check | Result | Detail |
|---|---|---|
| state.results non-empty | **PASS** | n=18 |
| postcondition totals | **PASS** | 17/18 overall; models={'gemma4:26b': '8/9', 'qwen3-vl:30b': '9/9'} |
| RESULTS.md matches re-sum | **PASS** | sha256=797f23ef8b25850c… |
| trace completeness | **PASS** | expected=18 on_disk=18 missing=0 orphans=0 |
| state↔trace field consistency | **PASS** | mismatches=0 |
| state.trace basename | **PASS** | all basenames match naming convention (or absent) |
| model tags | **PASS** | observed=['gemma4:26b', 'qwen3-vl:30b'] (no --expected-models) |
| machine provenance | **PASS** | counts={'desktop': 18} expected='desktop' |
| GPU residency (no CPU spill) | **PASS** | samples=26 all matrix models 100% GPU in every observation; by_model={'qwen3-vl:30b': {'gpu': 21}, 'gemma4:26b': {'gpu': 2}} |
| trace git_rev coherence | **PASS** | revs={'5be7db50d97de45b1a2860995a2d411d311fdb9c': 18} |

## Re-derived postcondition totals (from state.json)

| Model | Pass | N | Rate |
|---|---:|---:|---:|
| `gemma4:26b` | 8 | 9 | 89% |
| `qwen3-vl:30b` | 9 | 9 | 100% |

Overall: **17/18**

## Per-task × model

| Task | Model | Pass | N |
|---|---|---:|---:|
| `alias-add` | `gemma4:26b` | 2 | 3 |
| `alias-add` | `qwen3-vl:30b` | 3 | 3 |
| `config-value-change` | `gemma4:26b` | 3 | 3 |
| `config-value-change` | `qwen3-vl:30b` | 3 | 3 |
| `function-add` | `gemma4:26b` | 3 | 3 |
| `function-add` | `qwen3-vl:30b` | 3 | 3 |

## Digests

- `state.json` sha256: `8b5fbc50bcca8a9edbdbbbde4093a14501e489b9858b65155f547331a6d5406b`
- `RESULTS.md` sha256: `797f23ef8b25850c94c049741e8b1013099d3ef411977324ae03e96a80c5753a`
- `ollama_ps_samples.log` sha256: `ee6aa5b5c2221fa02357051e3c20ca11c6027c00c865f37aa528781fd312a682`
- trace git_revs: `{'5be7db50d97de45b1a2860995a2d411d311fdb9c': 18}`
- machines: `{'desktop': 18}`

This report re-derives aggregates from retained artifacts only. It does not re-run models or re-grade discarded temp fixtures.
