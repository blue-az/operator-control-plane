# Distinct-UID re-derive — Front E span e1–e9

**Verdict:** `PASS`
**Checked at:** 2026-08-13T16:54:22.646944+00:00
**Checker:** uid=971 user=operator-builder host=z13

Independent re-derive of postcondition totals, RESULTS.md, traces, machine
provenance, and GPU residency (where evidence exists) across the Front E ladder.

| Pack | Verdict | Pass/N | #models | Machines |
|---|---|---:|---:|---|
| `e1-gold-pack` | **PASS** | 25/27 | 3 | `{'desktop': 27}` |
| `e1x-27b` | **PASS** | 14/18 | 2 | `{'desktop': 18}` |
| `e2-postfix-vl` | **PASS** | 17/18 | 2 | `{'desktop': 18}` |
| `e3-controlled` | **PASS** | 60/63 | 7 | `{'desktop': 63}` |
| `e4-sampled` | **PASS** | 62/63 | 7 | `{'desktop': 63}` |
| `e5-floor` | **PASS** | 65/90 | 5 | `{'desktop': 90}` |
| `e6-think-ab/on` | **PASS** | 72/72 | 4 | `{'desktop': 72}` |
| `e6-think-ab/off` | **PASS** | 72/72 | 4 | `{'desktop': 72}` |
| `e7-unused-fixtures` | **PASS** | 126/126 | 7 | `{'desktop': 126}` |
| `e8-ceiling` | **PASS** | 55/210 | 7 | `{'desktop': 210}` |
| `e9-ceiling-continued` | **PASS** | 122/210 | 7 | `{'desktop': 210}` |

## E9 ceiling battery (re-derived totals)

- `gemma3:27b`: 12/30
- `gemma4:26b`: 24/30
- `gemma4:31b`: 24/30
- `qwen2.5-coder:14b`: 14/30
- `qwen3-vl:30b`: 16/30
- `qwen3.6:27b`: 19/30
- `qwen3:32b`: 13/30
- **overall 122/210**

Artifacts: `/home/blueaz/operator-control-plane/.operator/evidence/front-e1-gold-pack/rederive-e1-e9`

