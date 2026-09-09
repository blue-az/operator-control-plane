#!/usr/bin/env python3
"""DRAFT / NOT VALIDATED: PPR Lane A sweep utility retained for review.

Known blockers: both models are sent through provider 'grok' (including Qwen),
the Grok model value is a session-like ID, and outputs overwrite the latest
existing run directory. Correct routing and isolate output before live use.
No successful run or benchmark acceptance is claimed by retaining this script.

Usage:
  # Full sweep (grok + qwen38 comparison)
  python3 run_grok_sweep.py

  # Grok only
  python3 run_grok_sweep.py --models grok

  # Rescore existing output without re-running
  python3 run_grok_sweep.py --rescore

  # Rescore + write strict scores
  python3 run_grok_sweep.py --rescore --write
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNS_DIR = ROOT / "runs"
PROMPTS = ROOT / "sources" / "ppr_ground_truth.md"

# Models to run: (label, pi_model_arg)
DEFAULT_MODELS = [
    ("grok", "grok-beb2d4da"),
    ("qwen38", "qwen3.8:27b"),
]

TASK_FILES = {
    "ppr1_product_boundary": "p1_product_boundary.brief.md",
    "ppr2_gate_query_semantics": "p2_gate_query_semantics.brief.md",
    "ppr3_real_data_report": "p3_real_data_report.brief.md",
}


def make_prompt(task_id: str, label: str) -> str:
    """Build the raw prompt string from ground truth packet + task brief."""
    SOURCE = PROMPTS.read_text()
    TASK_BRIEFS = {
        "ppr1_product_boundary": (
            "Task: Write a concise product-boundary briefing for PPR Agent. Preserve exact facts and avoid overclaiming.\n"
            "Return sections: SURFACES, DATA_BOUNDARY, NON_GOALS, NUMBERS, RISK_NOTES.\n"
            "Must mention 4 surfaces, 15 tools, full vs published subset, 3576, 1483, 41.5%, "
            "not clinical monitoring, offline PDF ingestion, deterministic-not-chatbot.\n"
        ),
        "ppr2_gate_query_semantics": (
            "Task: Explain PPR Agent query/gate semantics and answer the two gate examples.\n"
            "Return sections: RULES, GATE_RESULTS, QUERY_VS_GATE, FAILURE_MODES.\n"
            "Must mention RUL-001 precedence, RUL-002 normalization, RUL-003 year cap, "
            "mdt 2030 allowed/year_capped 2025/company MDT, st jude 2007 allowed/year_capped 2008/company null, "
            "query executes data and gate only inspects policy.\n"
        ),
        "ppr3_real_data_report": (
            "Task: Produce an analyst report from the PPR real-data facts.\n"
            "Return sections: ICD_2023_COMPARISON, TOP_2023_DEVICES, MARKET_CONCENTRATION, SCOPE_LIMITS.\n"
            "Must include MDT vs ABT ICD 2023 exact model/family/implant numbers, top five 2023 devices with implant counts, "
            "HHI 3912.31 High, market shares MDT 52.96 ABT 24.42 BSX 22.61, "
            "and state this is historical analytical registry data not clinical advice.\n"
        ),
    }
    return TASK_BRIEFS[task_id] + f"\nUse only this local ground truth snapshot:\n{SOURCE}"


def submit_grok(model_id: str, prompt: str, timeout: int = 120) -> dict:
    """Submit a single task to grok via pi --provider grok."""
    cmd = [
        "pi", "--provider", "grok", "--model", model_id,
        "--thinking", "off",
        "--no-context-files", "--no-session", "--no-tools",
        "--print", "--", prompt,
    ]
    t0 = time.time()
    try:
        p = subprocess.run(
            cmd, text=True, capture_output=True, timeout=timeout,
            env={**subprocess.os.environ},
        )
        elapsed = round(time.time() - t0, 3)
        return {
            "returncode": p.returncode,
            "elapsed_s": elapsed,
            "stdout": p.stdout or "",
            "stderr": p.stderr or "",
        }
    except subprocess.TimeoutExpired as e:
        elapsed = round(time.time() - t0, 3)
        return {
            "returncode": 124,
            "elapsed_s": elapsed,
            "stdout": "",
            "stderr": f"timeout after {timeout}s",
        }


def main():
    ap = argparse.ArgumentParser(description="PPR Lane A grok sweep")
    ap.add_argument("--models", default="grok,qwen38", help="Comma-separated labels to run (default: grok,qwen38)")
    ap.add_argument("--rescore", action="store_true", help="Just rescore existing output, don't submit")
    ap.add_argument("--write", action="store_true", help="Write scores_strict.json on rescore")
    ap.add_argument("--timeout", type=int, default=120)
    args = ap.parse_args()

    selected_labels = {x.strip() for x in args.models.split(",") if x.strip()}
    models = [(l, m) for l, m in DEFAULT_MODELS if l in selected_labels]

    # Find or create run directory
    recent_run = sorted(RUNS_DIR.iterdir(), key=lambda p: p.name, reverse=True)[0].name
    run_dir = RUNS_DIR / recent_run
    manifest_path = run_dir / "manifest.json"

    if not args.rescore and manifest_path.exists():
        # Load existing manifest to populate results
        with open(manifest_path) as f:
            manifest = json.load(f)
    else:
        manifest = {
            "out_dir": str(run_dir),
            "provider": "grok",
            "model_purpose": {"grok": "Primary re-run model", "qwen38": "Reference for prior failure comparison"},
            "usage_source": "manual",
            "transcript_source": "cloud",
            "results": [],
        }

    if args.rescore:
        print(f"Rescoring run directory: {run_dir}")
        result = subprocess.run(
            ["python3", str(ROOT / "check_run.py"), str(run_dir)]
            + (["--write"] if args.write else []),
            capture_output=True, text=True, timeout=60,
        )
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr, file=__import__("sys").stderr)
        return result.returncode

    # Run tasks
    print(f"Running grok sweep in {run_dir}", flush=True)
    for task_id, brief_file in TASK_FILES.items():
        prompt = make_prompt(task_id, "")
        (run_dir / f"{task_id}.prompt.txt").write_text(prompt)
        for label, model_id in models:
            out_path = run_dir / f"{task_id}__{label}.out.md"
            json_path = run_dir / f"{task_id}__{label}.json"
            print(f"RUN {task_id} {label} ({model_id})", flush=True)
            r = submit_grok(model_id, prompt, args.timeout)
            out_path.write_text(r["stdout"])
            json.dump({**r, "task": task_id, "label": label, "model": model_id}, open(json_path, "w"), indent=2)
            status = "OK" if r["returncode"] == 0 else f"FAIL rc={r['returncode']}"
            print(f"DONE {task_id} {label} elapsed={r['elapsed_s']}s [{status}]", flush=True)
        manifest["results"].append({
            "task": task_id,
            "models": [l for l, _ in models],
            "prompt_file": f"{task_id}.prompt.txt",
        })

    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"\nRun complete: {run_dir}\n", flush=True)
    print("Now rescore with:", flush=True)
    print(f"  cd {ROOT} && python3 check_run.py {run_dir}")


if __name__ == "__main__":
    main()
