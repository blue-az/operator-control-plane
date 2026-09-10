#!/usr/bin/env python3
"""PPR Lane A sweep utility. No live benchmark acceptance is claimed.

Grok uses xai with an explicitly selected model; Qwen uses ollama.
New sweeps reserve isolated directories. Rescoring requires an explicit directory.

Usage:
  # Full sweep (grok + qwen38 comparison)
  python3 run_grok_sweep.py --grok-model grok-4.3

  # Grok only
  python3 run_grok_sweep.py --models grok --grok-model grok-4.3

  # Rescore existing output without re-running
  python3 run_grok_sweep.py --rescore --run-dir runs/<run>

  # Rescore + write strict scores
  python3 run_grok_sweep.py --rescore --run-dir runs/<run> --write
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNS_DIR = ROOT / "runs"
PROMPTS = ROOT / "sources" / "ppr_ground_truth.md"

DEFAULT_MODELS = [
    ("grok", "xai", None),
    ("qwen38", "ollama", "qwen3.8:27b"),
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


def submit_model(provider: str, model_id: str, prompt: str, timeout: int = 120) -> dict:
    """Submit a single task using its explicit provider/model route."""
    cmd = [
        "pi",
        "--provider",
        provider,
        "--model",
        model_id,
        "--thinking",
        "off",
        "--no-context-files",
        "--no-session",
        "--no-tools",
        "--print",
        "--",
        prompt,
    ]
    t0 = time.time()
    try:
        p = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            timeout=timeout,
            env={**subprocess.os.environ},
        )
        elapsed = round(time.time() - t0, 3)
        return {
            "returncode": p.returncode,
            "elapsed_s": elapsed,
            "stdout": p.stdout or "",
            "stderr": p.stderr or "",
        }
    except subprocess.TimeoutExpired:
        elapsed = round(time.time() - t0, 3)
        return {
            "returncode": 124,
            "elapsed_s": elapsed,
            "stdout": "",
            "stderr": f"timeout after {timeout}s",
        }
    except OSError as exc:
        return {
            "returncode": 127,
            "elapsed_s": round(time.time() - t0, 3),
            "stdout": "",
            "stderr": str(exc),
        }


def main(argv=None):
    ap = argparse.ArgumentParser(description="PPR Lane A grok sweep")
    ap.add_argument(
        "--models",
        default="grok,qwen38",
        help="Comma-separated labels to run (default: grok,qwen38)",
    )
    ap.add_argument(
        "--rescore", action="store_true", help="Just rescore existing output, don't submit"
    )
    ap.add_argument("--write", action="store_true", help="Write scores_strict.json on rescore")
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--grok-model", help="Required for Grok: actual xai model ID, not a session ID")
    ap.add_argument(
        "--run-dir", type=Path, help="New directory for sweep; existing directory for rescore"
    )
    args = ap.parse_args(argv)

    selected_labels = {x.strip() for x in args.models.split(",") if x.strip()}
    if not selected_labels or selected_labels - {row[0] for row in DEFAULT_MODELS}:
        ap.error("--models must select grok and/or qwen38")
    if args.timeout <= 0:
        ap.error("--timeout must be positive")
    if args.write and not args.rescore:
        ap.error("--write requires --rescore")
    if args.rescore:
        if args.run_dir is None or not (args.run_dir / "manifest.json").is_file():
            ap.error("--rescore requires --run-dir with an existing manifest.json")
        run_dir = args.run_dir.resolve()
    else:
        if "grok" in selected_labels and not args.grok_model:
            ap.error("--grok-model is required when selecting grok")
        if args.run_dir is not None:
            run_dir = args.run_dir.resolve()
            run_dir.mkdir(parents=True, exist_ok=False)
        else:
            RUNS_DIR.mkdir(parents=True, exist_ok=True)
            run_dir = Path(tempfile.mkdtemp(prefix="sweep-", dir=RUNS_DIR))
    models = [
        (label, provider, args.grok_model if label == "grok" else model)
        for label, provider, model in DEFAULT_MODELS
        if label in selected_labels
    ]
    manifest = {
        "out_dir": str(run_dir),
        "lane": "A",
        "model_routes": {
            label: {"provider": provider, "model": model} for label, provider, model in models
        },
        "results": [],
    }

    if args.rescore:
        print(f"Rescoring run directory: {run_dir}")
        result = subprocess.run(
            [sys.executable, str(ROOT / "check_run.py"), str(run_dir)]
            + (["--write"] if args.write else []),
            capture_output=True,
            text=True,
            timeout=60,
        )
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr, file=__import__("sys").stderr)
        return result.returncode

    exit_code = 0
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    # Run tasks
    print(f"Running grok sweep in {run_dir}", flush=True)
    for task_id, brief_file in TASK_FILES.items():
        prompt = make_prompt(task_id, "")
        (run_dir / f"{task_id}.prompt.txt").write_text(prompt)
        for label, provider, model_id in models:
            out_path = run_dir / f"{task_id}__{label}.out.md"
            json_path = run_dir / f"{task_id}__{label}.json"
            print(f"RUN {task_id} {label} ({model_id})", flush=True)
            r = submit_model(provider, model_id, prompt, args.timeout)
            if r["returncode"] and not exit_code:
                exit_code = r["returncode"] if r["returncode"] > 0 else 128 - r["returncode"]
            out_path.write_text(r["stdout"])
            row = {
                **r,
                "task": task_id,
                "label": label,
                "provider": provider,
                "model": model_id,
                "stdout_path": out_path.name,
            }
            json_path.write_text(json.dumps(row, indent=2))
            manifest["results"].append(row)
            (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
            status = "OK" if r["returncode"] == 0 else f"FAIL rc={r['returncode']}"
            print(f"DONE {task_id} {label} elapsed={r['elapsed_s']}s [{status}]", flush=True)

    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"\nRun complete: {run_dir}\n", flush=True)
    print("Now rescore with:", flush=True)
    print(f"  cd {ROOT} && python3 check_run.py {run_dir}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
