#!/usr/bin/env python3
"""Repo-orientation probe: 4 models x n=6, grade five asked facets.

Workspace is a copy of the live governing docs (no sample-project
distractors, no BN injection). Length and wall-clock are recorded;
neither is a pass gate.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PHOENIX = Path("/home/blueaz/Python/project-phoenix")
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO))

from map_probe import PROMPT, extract_answer, grade_answer, measure
from runner import (
    MACHINE,
    MAX_WALL_CLOCK_SECONDS,
    OPR_BIN,
    parse_trajectory,
    write_trace,
)

GUIDES = ("AGENTS.md", "CLAUDE.md", "BOTTLENECKS.md", "ONBOARDING.md", "README.md")
MODELS = ("gemma4:26b", "gemma4:31b", "qwen3.8:27b", "qwen3.6:27b")


def build_workspace() -> Path:
    root = Path(tempfile.mkdtemp(prefix="local-lane-eval-map-probe-")).resolve()
    for name in GUIDES:
        src = PHOENIX / name
        if not src.is_file():
            raise FileNotFoundError(src)
        shutil.copyfile(src, root / name)
    return root


def run_cell(model: str, trial: int, trace_dir: Path) -> dict:
    workspace = build_workspace()
    argv = [
        str(OPR_BIN),
        PROMPT,
        "--model",
        model,
        "--workspace",
        str(workspace),
        "--eval-auto-confirm",
        "--allow-write",
        "--allow-run",
        "--no-govern",
        "--no-bn",
        "--continue-steps",
        "8",
        "--num-ctx",
        "16384",
        "--temperature",
        "0.8",
        "--think",
        "off",
    ]
    start = time.monotonic()
    timed_out = False
    try:
        completed = subprocess.run(
            argv, capture_output=True, text=True, timeout=MAX_WALL_CLOCK_SECONDS
        )
        stdout, stderr, rc = completed.stdout, completed.stderr, completed.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout, stderr, rc = exc.stdout or "", exc.stderr or "", None
    wall = time.monotonic() - start
    shutil.rmtree(workspace, ignore_errors=True)

    traj = parse_trajectory(stdout or "")
    answer = extract_answer(stdout or "")
    grade = grade_answer(answer)
    length = measure(stdout or "", wall, traj)
    record = {
        "task_id": "map-probe",
        "level": "ask",
        "model": model,
        "trial": trial,
        "machine": MACHINE,
        "passed": grade["passed"] and not timed_out,
        "detail": "timed out" if timed_out else f"{grade['n_sourced']}/5 facets sourced",
        "facets": grade["facets"],
        "n_sourced": grade["n_sourced"],
        "wall_clock_s": length.wall_clock_s,
        "answer_chars": length.answer_chars,
        "answer_words": length.answer_words,
        "n_calls": length.n_calls,
        "completion_tokens": length.completion_tokens,
        "prompt_tokens": length.prompt_tokens,
        "n_rounds": length.n_rounds,
        "files_read": length.files_read,
        "answer": answer,
        "returncode": rc,
        "timed_out": timed_out,
    }
    path = write_trace(
        trace_dir,
        "map-probe",
        "ask",
        model,
        trial,
        argv=argv,
        prompt=PROMPT,
        stdout=stdout or "",
        stderr=stderr or "",
        record=record,
        timed_out=timed_out,
    )
    extra = json.loads(path.read_text())
    extra.update(
        {
            "facets": record["facets"],
            "n_sourced": record["n_sourced"],
            "answer": record["answer"],
            "answer_chars": record["answer_chars"],
            "answer_words": record["answer_words"],
            "prompt_tokens": record["prompt_tokens"],
            "n_rounds": record["n_rounds"],
            "files_read": record["files_read"],
        }
    )
    path.write_text(json.dumps(extra, indent=2, sort_keys=True), encoding="utf-8")
    return record


def write_results(rows: list[dict], path: Path) -> None:
    lines = [
        "# Map probe — results",
        "",
        f"Generated from {len(rows)} trial records. Machine: {MACHINE}.",
        "Pass = all five asked facets sourced in the final answer.",
        "Length and time are recorded; they are not the gate.",
        "",
        "## Per cell",
        "",
        "| Model | Trial | Pass | Facets | s | words | chars | ctok | ptok | calls | rounds | files_read |",
        "|---|---:|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        files = ",".join(r.get("files_read") or []) or "—"
        lines.append(
            f"| {r['model']} | {r['trial']} | {'PASS' if r['passed'] else 'FAIL'} | "
            f"{r['n_sourced']}/5 | {r['wall_clock_s']} | {r['answer_words']} | "
            f"{r['answer_chars']} | {r['completion_tokens']} | {r['prompt_tokens']} | "
            f"{r['n_calls']} | {r['n_rounds']} | {files} |"
        )
    lines += ["", "## Per model", "",
              "| Model | Pass | Mean s | Median s | Mean words | Mean ctok | Mean calls |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for model in MODELS:
        cell = [r for r in rows if r["model"] == model]
        if not cell:
            continue
        ws = sorted(r["wall_clock_s"] for r in cell)
        lines.append(
            f"| {model} | {sum(r['passed'] for r in cell)}/{len(cell)} | "
            f"{sum(r['wall_clock_s'] for r in cell)/len(cell):.1f} | "
            f"{ws[len(ws)//2]:.1f} | "
            f"{sum(r['answer_words'] for r in cell)/len(cell):.0f} | "
            f"{sum(r['completion_tokens'] for r in cell)/len(cell):.0f} | "
            f"{sum(r['n_calls'] for r in cell)/len(cell):.1f} |"
        )
    lines += ["", "## Facet hit rate", "",
              "| Model | what_for | names | authority | open_now | read_first |",
              "|---|---:|---:|---:|---:|---:|"]
    keys = ("what_for", "names", "authority", "open_now", "read_first")
    for model in MODELS:
        cell = [r for r in rows if r["model"] == model]
        if not cell:
            continue
        bits = []
        for k in keys:
            n = sum(1 for r in cell if r["facets"].get(k) == "sourced")
            bits.append(f"{n}/{len(cell)}")
        lines.append(f"| {model} | " + " | ".join(bits) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--models", nargs="+", default=list(MODELS))
    p.add_argument("--trials", type=int, default=6)
    p.add_argument("--output", type=Path, default=HERE / "fixtures/map-probe/RESULTS.md")
    p.add_argument("--state", type=Path, default=HERE / "fixtures/map-probe/state.json")
    p.add_argument("--trace-dir", type=Path, default=HERE / "fixtures/map-probe/traces")
    args = p.parse_args()
    args.trace_dir.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    state = {"results": []}
    if args.state.exists():
        state = json.loads(args.state.read_text())
    done = {(r["model"], r["trial"]) for r in state.get("results", [])}

    print(
        f"Grid: {len(args.models)} models x {args.trials} trials. "
        f"no-bn, think off, ctx 16384, temp 0.8",
        flush=True,
    )
    print(f"guides copied from {PHOENIX}: {', '.join(GUIDES)}", flush=True)
    print(f"started {datetime.now(UTC).isoformat()}", flush=True)

    for model in args.models:
        for trial in range(1, args.trials + 1):
            if (model, trial) in done:
                print(f"[{model} t{trial}] skip (done)", flush=True)
                continue
            print(f"[{model} t{trial}] running...", flush=True)
            rec = run_cell(model, trial, args.trace_dir)
            state["results"].append(rec)
            args.state.write_text(json.dumps(state, indent=2), encoding="utf-8")
            write_results(state["results"], args.output)
            print(
                f"[{model} t{trial}] "
                f"{'PASS' if rec['passed'] else 'FAIL'} "
                f"{rec['n_sourced']}/5 {rec['wall_clock_s']}s "
                f"{rec['answer_words']}w ctok={rec['completion_tokens']} "
                f"calls={rec['n_calls']}",
                flush=True,
            )
    write_results(state["results"], args.output)
    print(f"Wrote {args.output}", flush=True)
    return 0


if __name__ == "__main__":
    os.environ.setdefault("OPERATOR_MACHINE", "desktop")
    raise SystemExit(main())
