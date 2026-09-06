# Expanded PPR benchmark runner/checker verification

Task: `ppr-benchmark-expanded-runner`  
Date: 2026-09-03  
Reviewer/runner: `pi-01a0659c`  

## Files present

- `evals/ppr_agent_benchmark/GOLD_STANDARD.md`
- `evals/ppr_agent_benchmark/manifests/gold_manifest_v1.json`
- `evals/ppr_agent_benchmark/check_run.py`
- `evals/ppr_agent_benchmark/test_gold_standard.py`
- `evals/ppr_agent_benchmark/README.md` updated with gold-standard usage

## Commands run

```bash
cd /home/blueaz/operator-control-plane
python3 -m unittest evals/ppr_agent_benchmark/test_gold_standard.py -v
```

Result: 5 tests passed.

```bash
cd /home/blueaz/operator-control-plane/evals/ppr_agent_benchmark
python3 check_run.py runs/20260825-192929 --write
python3 check_run.py --lane-b --cwd /home/blueaz/Python/ppr-agent
```

Result:

- Lane A historical run `runs/20260825-192929`: `fully_pass=True`, 12 rows passed.
- Strict Lane A scores written to ignored run artifact `runs/20260825-192929/scores_strict.json`.
- Lane B live deterministic execution against `/home/blueaz/Python/ppr-agent`: `fully_pass=True`.
- Lane B passed all 7 recorded commands:
  - `ppr_stats`
  - `ppr_tools`
  - `ppr_gate_mdt_2030`
  - `ppr_gate_st_jude_2007`
  - `ppr_query_compare_icd_2023`
  - `ppr_run_top_devices_2023`
  - `ppr_run_hhi_icd_2023`

## Notes

This verifies the checker/manifest mechanics and live PPR command replay on the current machine. It does not claim any new local-model benchmark run beyond rescoring the existing historical Lane A run.
