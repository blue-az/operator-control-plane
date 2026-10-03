#!/usr/bin/env python3
"""Copy the small evidence from Harbor job dirs and derive per-trial agent stats.

Usage (from the repo root):
    python3 evals/pi_tb21_local_smoke/collect.py [JOBS_DIR]

JOBS_DIR defaults to ~/Python/Evaluation/pi-mono/.harbor-jobs. For each run in
RUNS this copies the job config/result and, per trial, config.json,
result.json, verifier/test-stdout.txt and verifier/reward.txt into
evidence/<run>/, and writes agent_stats.json derived from agent/pi.txt (the
transcripts themselves stay in the raw job dir). It then prints the summary
tables used in README.md.
"""

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence"
RUNS = [
    "pi-smoke-5task-2026-10-01-latest",
    "pi-smoke-5task-2026-10-02-local-qwen36",
    "pi-smoke-extract-elf-2026-10-02-local-qwen36-limits",
    "pi-smoke-5task-2026-10-02-local-qwen36-limits",
    "pi-smoke-5task-2026-10-02-local-qwen36-nothink",
    "ABORTED-pi-smoke-5task-2026-10-02-local-qwen38-64k-developer-role",
    "pi-smoke-5task-2026-10-02-local-qwen38-64k-nothink",
]
TRIAL_FILES = ["config.json", "result.json", "verifier/test-stdout.txt", "verifier/reward.txt"]


def agent_stats(pi_txt):
    """Per-trial numbers from pi's JSON event stream."""
    turns, ins, outs, stops, thinking, compactions, errors = 0, [], [], [], 0, 0, []
    for line in pi_txt.read_text(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "compaction_end":
            compactions += 1
        if event.get("type") != "message_end":
            continue
        message = event["message"]
        if message.get("role") != "assistant":
            continue
        turns += 1
        usage = message.get("usage") or {}
        ins.append(usage.get("input") or 0)
        outs.append(usage.get("output") or 0)
        stops.append(message.get("stopReason"))
        thinking += sum(len(p.get("thinking", "")) for p in message.get("content") or []
                        if p.get("type") == "thinking")
        if message.get("errorMessage"):
            errors.append(message["errorMessage"][:300])
    return {
        "assistant_turns": turns,
        "max_turn_input_tokens": max(ins, default=0),
        "max_turn_output_tokens": max(outs, default=0),
        "length_stops": stops.count("length"),
        "last_stop_reason": stops[-1] if stops else None,
        "thinking_chars": thinking,
        "compactions": compactions,
        "first_error": errors[0] if errors else None,
    }


def trial_row(trial_dir):
    result = json.loads((trial_dir / "result.json").read_text())
    stats = json.loads((trial_dir / "agent_stats.json").read_text())
    reward = ((result.get("verifier_result") or {}).get("rewards") or {}).get("reward")
    started, finished = result.get("started_at"), result.get("finished_at")
    seconds = None
    if started and finished:
        parse = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
        seconds = round((parse(finished) - parse(started)).total_seconds())
    tests = []
    stdout = trial_dir / "verifier" / "test-stdout.txt"
    if stdout.exists():
        tests = [l[:6] for l in stdout.read_text().splitlines() if l.startswith(("PASSED", "FAILED"))]
    return {
        "task": trial_dir.name.split("__")[0],
        "reward": reward,
        "seconds": seconds,
        "tests": "%d/%d" % (tests.count("PASSED"), len(tests)) if tests else "-",
        **stats,
    }


def collect(jobs_dir):
    for run in RUNS:
        src = jobs_dir / run
        dst = EVIDENCE / run
        if not src.is_dir():
            print("missing run dir, skipped:", src, file=sys.stderr)
            continue
        dst.mkdir(parents=True, exist_ok=True)
        for name in ("config.json", "result.json"):
            if (src / name).exists():
                shutil.copy2(src / name, dst / name)
        for trial in sorted(p for p in src.iterdir() if p.is_dir() and "__" in p.name):
            out = dst / trial.name
            for rel in TRIAL_FILES:
                if (trial / rel).exists():
                    (out / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(trial / rel, out / rel)
            pi_txt = trial / "agent" / "pi.txt"
            if pi_txt.exists():
                (out / "agent_stats.json").write_text(
                    json.dumps(agent_stats(pi_txt), indent=2) + "\n")


def summarize():
    for run in RUNS:
        run_dir = EVIDENCE / run
        if not run_dir.is_dir():
            continue
        rows = [trial_row(t) for t in sorted(run_dir.iterdir())
                if t.is_dir() and (t / "agent_stats.json").exists()]
        passed = sum(1 for r in rows if r["reward"] == 1.0)
        print("\n## %s  (%d/%d)" % (run, passed, len(rows)))
        for r in rows:
            print("  %(task)-20s reward=%(reward)s %(seconds)ss tests=%(tests)s turns=%(assistant_turns)s "
                  "max_in=%(max_turn_input_tokens)s max_out=%(max_turn_output_tokens)s "
                  "length_stops=%(length_stops)s last=%(last_stop_reason)s thinking=%(thinking_chars)s "
                  "compactions=%(compactions)s" % r)
            if r["first_error"]:
                print("      error: " + r["first_error"][:160])


if __name__ == "__main__":
    jobs = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else \
        Path("~/Python/Evaluation/pi-mono/.harbor-jobs").expanduser()
    collect(jobs)
    summarize()
