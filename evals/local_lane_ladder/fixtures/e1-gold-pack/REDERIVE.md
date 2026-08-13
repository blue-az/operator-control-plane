# Pack re-derive — `e1-gold-pack`

**Verdict:** `PASS`
**Checked at:** 2026-08-13T02:46:48.369291+00:00
**Checker:** uid=971 user=operator-builder host=z13
**Pack path:** `/home/blueaz/operator-control-plane/evals/local_lane_ladder/fixtures/e1-gold-pack`

## Checks

| Check | Result | Detail |
|---|---|---|
| state.results non-empty | **PASS** | n=27 |
| postcondition totals | **PASS** | 25/27 overall; models={'gemma4:26b': '9/9', 'gemma4:31b': '9/9', 'qwen2.5-coder:14b': '7/9'} |
| RESULTS.md matches re-sum | **PASS** | sha256=fb639946649990c1… |
| trace completeness | **PASS** | expected=27 on_disk=27 missing=0 orphans=0 |
| state↔trace field consistency | **PASS** | mismatches=0 |
| state.trace basename | **PASS** | all basenames match naming convention (or absent) |
| model tags | **PASS** | observed=['gemma4:26b', 'gemma4:31b', 'qwen2.5-coder:14b'] (no --expected-models) |
| machine provenance | **PASS** | counts={'desktop': 27} expected='desktop' |
| GPU residency (no CPU spill) | **PASS** | samples=16 all matrix models 100% GPU in every observation; by_model={'qwen2.5-coder:14b': {'gpu': 2}, 'gemma4:31b': {'gpu': 7}, 'gemma4:26b': {'gpu': 4}} |
| trace git_rev coherence | **PASS** | revs={'90e91d732403c525d6ecb9a6c639bd2685976f87': 27} |

## Re-derived postcondition totals (from state.json)

| Model | Pass | N | Rate |
|---|---:|---:|---:|
| `gemma4:26b` | 9 | 9 | 100% |
| `gemma4:31b` | 9 | 9 | 100% |
| `qwen2.5-coder:14b` | 7 | 9 | 78% |

Overall: **25/27**

## Per-task × model

| Task | Model | Pass | N |
|---|---|---:|---:|
| `alias-add` | `gemma4:26b` | 3 | 3 |
| `alias-add` | `gemma4:31b` | 3 | 3 |
| `alias-add` | `qwen2.5-coder:14b` | 3 | 3 |
| `config-value-change` | `gemma4:26b` | 3 | 3 |
| `config-value-change` | `gemma4:31b` | 3 | 3 |
| `config-value-change` | `qwen2.5-coder:14b` | 1 | 3 |
| `function-add` | `gemma4:26b` | 3 | 3 |
| `function-add` | `gemma4:31b` | 3 | 3 |
| `function-add` | `qwen2.5-coder:14b` | 3 | 3 |

## Digests

- `state.json` sha256: `4e6f6bbfe85d100ccd9d03adef4a254d25059a49668c387049ba78f1090aac5a`
- `RESULTS.md` sha256: `fb639946649990c169a11a570167beba95e95d197949e46fed30fdc949b4b015`
- `ollama_ps_samples.log` sha256: `243664dc804cffc128d852151291dcac42c0b3c3942cf7022bfb19149e758a21`
- trace git_revs: `{'90e91d732403c525d6ecb9a6c639bd2685976f87': 27}`
- machines: `{'desktop': 27}`

This report re-derives aggregates from retained artifacts only. It does not re-run models or re-grade discarded temp fixtures.
