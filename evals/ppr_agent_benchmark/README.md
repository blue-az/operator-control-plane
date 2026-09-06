# PPR Agent Internal Benchmark

Local-only benchmark over the real local `ppr-agent` CRM Product Performance Registry extract.

This is separate from:

- FastFoodAgent: local coding implementation over MenuStat.
- DocAI use-case benchmark: evaluator/reviewer/process extraction from saved DocAI artifacts.

PPR-Agent measures real-world data/product comprehension: can a model preserve product boundaries, reason over deterministic query/gate behavior, and report exact CRM registry facts without turning the system into a generic chatbot or clinical tool.

## Gold standard

Typed two-lane gold standard (v1). The lanes are never merged in claims:

- `GOLD_STANDARD.md` -- Lane A is grounded reproduction of the frozen packet
  (`sources/ppr_ground_truth.md`) into three headed briefs. Lane B is live
  deterministic `./ppr` execution against `/home/blueaz/Python/ppr-agent`.
  Lane A claims grounded reproduction only; Lane B is the only
  execution-competence lane.
- `manifests/gold_manifest_v1.json` -- machine-checkable expected values,
  frozen SHA-256 of `ppr_agent.db`, ppr-agent HEAD, acceptance, and known
  drift notes.
- `check_run.py` -- Lane A rescores a historical run dir (writes
  `scores_strict.json` only with `--write`; never overwrites `scores.json`
  or `SCORES.md`). `--lane-b` executes the recorded CLI commands.

```bash
python3 check_run.py runs/20260825-192929
python3 check_run.py --lane-b
python3 -m pytest evals/ppr_agent_benchmark/test_gold_standard.py
```
