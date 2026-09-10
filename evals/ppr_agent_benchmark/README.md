# PPR Agent Internal Benchmark

Local-only benchmark over the real local `ppr-agent` CRM Product Performance Registry extract.

This is separate from:

- FastFoodAgent: local coding implementation over MenuStat.
- DocAI use-case benchmark: evaluator/reviewer/process extraction from saved DocAI artifacts.

PPR-Agent measures real-world data/product comprehension: can a model preserve product boundaries, reason over deterministic query/gate behavior, and report exact CRM registry facts without turning the system into a generic chatbot or clinical tool.

## Isolated Lane A sweep

```bash
python3 run_grok_sweep.py --models qwen38
python3 run_grok_sweep.py --models grok,qwen38 --grok-model grok-4.3
python3 run_grok_sweep.py --rescore --run-dir runs/<explicit-run>
python3 -m unittest test_grok_sweep -v
```

Grok routes through `xai`; its actual model ID must be selected explicitly (the example is in the installed registry, not a live-validation claim). Qwen routes through `ollama` as `qwen3.8:27b`. Credentials/endpoints remain pi configuration.

Every sweep reserves a fresh `runs/sweep-*` directory, or accepts a new `--run-dir` and refuses any existing path. Rescore requires an explicit existing directory; only `--write` writes strict scores. Each manifest row records provider, model, process status, and output path.

Sweep exit status is the first failed submission's code (timeout 124, launch error 127, signal 128+signal); later successful tasks cannot hide it. All bounded tasks are attempted. Exit 0 means submissions succeeded, **not** that gold-standard scoring passed. Rescore propagates the checker's exit status. No live model campaign was run for these repairs.

Claim-0153 remains quarantined; see [independent inspection](CLAIM_0153_INDEPENDENT_REVIEW.md). Runner fixes do not release it.

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
