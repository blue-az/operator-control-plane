# PPR Agent GOLD_STANDARD.md review

Reviewer: `pi-01a0659c`  
Date: 2026-09-03  
Task: `ppr-agent-gold-standard`  
Claim reviewed: `claim-0152`

## Result

Advisory review: **accepted with one correction applied**.

Correction applied to `evals/ppr_agent_benchmark/GOLD_STANDARD.md`: fixed the local-model examples from incorrect prose labels (`Qwen 3 8B`, `Qwen 3 6/35B`, `Gemma 3 31B`, `Gemma 2 6B`) to the actual benchmark model IDs: `qwen3.8:27b`, `qwen3.6:35b`, `gemma4:31b`, `gemma4:26b`.

## Verification commands run

From `/home/blueaz/Python/ppr-agent`:

```bash
sha256sum ppr_agent.db PPR_Agent.pbc.md desk/devices_published.json
git rev-parse HEAD
./ppr stats
./ppr gate "mdt 2030"
./ppr gate "st jude 2007"
python -m unittest discover -s tests -v
./ppr tools
./ppr run get_market_concentration --year 2023 --device-category ICD
./ppr run get_top_devices --year 2023 --limit 5
```

From `/home/blueaz/operator-control-plane`:

```bash
test -s evals/ppr_agent_benchmark/GOLD_STANDARD.md
grep -q 'qwen3.8:27b' evals/ppr_agent_benchmark/GOLD_STANDARD.md
grep -q 'PPR8-trajectory' evals/ppr_agent_benchmark/GOLD_STANDARD.md
grep -q '753123e5d05de9008d6ddfdfa813a214cdfc5df1241fe8f2156b3f81974daf89' evals/ppr_agent_benchmark/GOLD_STANDARD.md
```

## Evidence observed

- Source commit matched: `04ed8ed9ce8095cbeedc09d5aa218e7ffb2565ad`.
- Hashes matched the gold-standard packet:
  - `ppr_agent.db`: `753123e5d05de9008d6ddfdfa813a214cdfc5df1241fe8f2156b3f81974daf89`
  - `PPR_Agent.pbc.md`: `6cdbb3fb47dbd971269d0d5fb5ff3d37831c7f7f72f3f9b543bc1ba3bc7db359`
  - `desk/devices_published.json`: `1fae1b6b3dea55d98aefb3f63386cab7df43f7716b6db2275bfa579ac7c1d09c`
- `./ppr stats` confirmed 3,576 devices, 92,071,191 implants, 2008-2025, 18 years, 3 companies, and the company/category totals used by the gold standard.
- `./ppr gate "mdt 2030"` confirmed allowed true, company `MDT`, `year_capped=2025`, rule hits `PPR-RUL-002` and `PPR-RUL-003`.
- `./ppr gate "st jude 2007"` confirmed allowed true, company null, `year_capped=2008`, rule hit `PPR-RUL-003`.
- Unit tests passed: 11 tests, OK.
- `./ppr tools` confirmed 15 registered tools and export signature `export_results(data_key, filename)`.
- `get_market_concentration` confirmed HHI `3912.31`, High, shares MDT `52.96`, ABT `24.42`, BSX `22.61`.
- `get_top_devices --year 2023 --limit 5` confirmed the top-five device list and counts used in the gold standard.

## Scope note

This is advisory same-UID review, not UID-isolated verification. The content is ready for a separate verifier if strict isolation is required.
