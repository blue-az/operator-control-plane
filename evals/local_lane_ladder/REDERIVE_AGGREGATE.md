# Distinct-UID re-derive — Front E ladder packs (E1–E5)

**Verdict:** `PASS`
**Checked at:** 2026-08-13T02:47:56.850845+00:00
**Checker:** uid=971 user=operator-builder host=z13

Independent re-derive of postcondition totals, RESULTS.md regeneration,
trace completeness, state↔trace consistency, model tags, machine provenance,
and GPU residency — from retained artifacts only. Run as a distinct OS UID
from the claim author (uid 1000).

| Pack | Verdict | Pass/N | #models | Machines | Checker uid |
|---|---|---:|---:|---|---:|
| `e1-gold-pack` | **PASS** | 25/27 | 3 | `{'desktop': 27}` | 971 |
| `e1x-27b` | **PASS** | 14/18 | 2 | `{'desktop': 18}` | 971 |
| `e2-postfix-vl` | **PASS** | 17/18 | 2 | `{'desktop': 18}` | 971 |
| `e3-controlled` | **PASS** | 60/63 | 7 | `{'desktop': 63}` | 971 |
| `e4-sampled` | **PASS** | 62/63 | 7 | `{'desktop': 63}` | 971 |
| `e5-floor` | **PASS** | 65/90 | 5 | `{'desktop': 90}` | 971 |

## Headline re-derived numbers

### e4-sampled (ceiling / saturation)

- `gemma3:27b`: 9/9
- `gemma4:26b`: 8/9
- `gemma4:31b`: 9/9
- `qwen2.5-coder:14b`: 9/9
- `qwen3-vl:30b`: 9/9
- `qwen3.6:27b`: 9/9
- `qwen3:32b`: 9/9
- **overall 62/63**
- state.json sha256: `61e62003c622a2a5ce6eade6aee6b7e55395f34e678417a4ae406b6565aa6f56`

### e5-floor (path-fidelity floor)

- `gemma4:12b`: 17/18
- `gemma4:e4b`: 13/18
- `granite4:latest`: 8/18
- `llama3.1:8b`: 9/18
- `qwen2.5-coder:14b`: 18/18
- **overall 65/90**
- state.json sha256: `b8b2e55a6aec16840fbaa8aed601c84edce4b52a6cf7341487921cb11607d4da`

### e1-gold-pack (pre-harness-fix matrix; confounded cells included)

- `gemma4:26b`: 9/9
- `gemma4:31b`: 9/9
- `qwen2.5-coder:14b`: 7/9
- **overall 25/27**
- state.json sha256: `4e6f6bbfe85d100ccd9d03adef4a254d25059a49668c387049ba78f1090aac5a`

### e1x-27b

- `gemma3:27b`: 5/9
- `qwen3.6:27b`: 9/9
- **overall 14/18**
- state.json sha256: `e3c35c7154ca39d3ef79d2c4051afb790df5d8c3858d451a39fb5ae0c4cde857`

### e2-postfix-vl

- `gemma4:26b`: 8/9
- `qwen3-vl:30b`: 9/9
- **overall 17/18**
- state.json sha256: `8b5fbc50bcca8a9edbdbbbde4093a14501e489b9858b65155f547331a6d5406b`

### e3-controlled (temperature-0 artifact record)

- `gemma3:27b`: 9/9
- `gemma4:26b`: 6/9
- `gemma4:31b`: 9/9
- `qwen2.5-coder:14b`: 9/9
- `qwen3-vl:30b`: 9/9
- `qwen3.6:27b`: 9/9
- `qwen3:32b`: 9/9
- **overall 60/63**
- state.json sha256: `f2094f3e578f49a29d1b1822ed4319507f028a9e1bb0b5715ce9462b1735129c`

Per-pack `*.json` / `*.md` reports live alongside this file.

Method: `evals/local_lane_ladder/rederive_pack.py`. Does not re-run models; temp fixtures are gone. Integrity is over the freeze (state + traces + evidence).

