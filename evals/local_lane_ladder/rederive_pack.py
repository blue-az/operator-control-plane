#!/usr/bin/env python3
"""Independent re-derive of a local-lane ladder pack from retained artifacts.

Distinct-UID re-derive for Front E packs (GOLD_STANDARD rule 7 / E1 MANIFEST).
Recomputes from state.json + per-cell traces + evidence/, without trusting
FINDING.md narration or RESULTS.md tables as authoritative.

Checks:
  1. Postcondition totals — re-sum state.results[i].passed by model and task
  2. RESULTS.md regeneration — rewrite via runner.write_results_md and byte-compare
  3. Trace completeness — every result has a matching traces/*.json; no orphans
  4. State ↔ trace consistency — model, task, level, trial, passed, machine agree
  5. Model tags — set of models equals the declared set (arg or prerun/FINDING free text)
  6. Machine provenance — every trial machine is the expected producer
  7. GPU residency — ollama_ps_samples.log shows no CPU spill for listed models

Does NOT re-run models or re-grade fixtures (temp fixtures are gone). The grade
was frozen into state + trace at run time; this re-derives the *aggregates*
and integrity of that freeze.

Usage:
    python3 rederive_pack.py fixtures/e5-floor [--expected-machine desktop]
    python3 rederive_pack.py fixtures/e5-floor --json-out /tmp/e5.json --md-out /tmp/e5.md

Exit 0 only when every check PASSes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Allow importing runner helpers from this directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from runner import write_results_md, trace_path_for  # noqa: E402

REQUIRED_TRACE_KEYS = {
    "cell_key",
    "task_id",
    "level",
    "model",
    "trial",
    "machine",
    "git_rev",
    "passed",
    "stdout",
    "stderr",
    "argv",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_model(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "-", model)


def parse_ollama_ps(log_text: str) -> dict:
    """Parse ollama_ps_samples.log into residency observations.

    Returns {
      "samples": N,
      "rows": [{"name":..., "processor":...}, ...],
      "by_model": {name: {"gpu": n, "cpu": n, "mixed": n, "other": n}},
      "non_gpu_rows": [...],
    }
    """
    samples = 0
    rows: list[dict] = []
    by_model: dict[str, Counter] = defaultdict(Counter)
    non_gpu: list[dict] = []
    for block in re.split(r"\n--- ", log_text):
        if not block.strip():
            continue
        lines = block.strip().splitlines()
        # first line is timestamp or "--- timestamp"
        body = lines[1:] if lines else []
        # skip header
        data_lines = [ln for ln in body if ln.strip() and not ln.startswith("NAME")]
        if not data_lines and body:
            # empty sample (no models loaded)
            samples += 1
            continue
        samples += 1
        for ln in data_lines:
            # NAME ID SIZE PROCESSOR CONTEXT UNTIL — columns are multi-space separated
            parts = re.split(r"\s{2,}", ln.strip())
            if len(parts) < 4:
                continue
            name = parts[0]
            # PROCESSOR is typically "100% GPU" or "45%/55% CPU/GPU"
            processor = parts[3] if len(parts) >= 4 else ""
            # Sometimes SIZE is "3.0 GB" so parts may shift; find the processor token.
            proc_match = re.search(r"(\d+%\s*GPU|\d+%\s*/\s*\d+%\s*CPU/GPU|100%\s*CPU)", ln)
            if proc_match:
                processor = proc_match.group(1)
            row = {"name": name, "processor": processor, "raw": ln}
            rows.append(row)
            p = processor.upper().replace(" ", "")
            if "CPU/GPU" in p or ("CPU" in p and "GPU" in p and "/" in p):
                bucket = "mixed"
            elif "CPU" in p and "GPU" not in p:
                bucket = "cpu"
            elif "GPU" in p:
                bucket = "gpu"
            else:
                bucket = "other"
            by_model[name][bucket] += 1
            if bucket != "gpu":
                non_gpu.append(row)
    return {
        "samples": samples,
        "row_count": len(rows),
        "by_model": {k: dict(v) for k, v in by_model.items()},
        "non_gpu_rows": non_gpu,
    }


def rederive_pack(
    pack_dir: Path,
    *,
    expected_machine: str = "desktop",
    expected_models: set[str] | None = None,
) -> dict:
    pack_dir = pack_dir.resolve()
    checks: list[dict] = []
    errors: list[str] = []

    def record(name: str, ok: bool, detail: str, **extra):
        checks.append({"name": name, "ok": ok, "detail": detail, **extra})
        if not ok:
            errors.append(f"{name}: {detail}")

    state_path = pack_dir / "state.json"
    results_path = pack_dir / "RESULTS.md"
    traces_dir = pack_dir / "traces"
    # e6-think-ab keeps evidence/ on the pack root with state under on/ and off/.
    evidence_dir = pack_dir / "evidence"
    if not evidence_dir.is_dir():
        parent_ev = pack_dir.parent / "evidence"
        if parent_ev.is_dir():
            evidence_dir = parent_ev

    if not state_path.is_file():
        return {
            "pack": str(pack_dir),
            "ok": False,
            "checks": [{"name": "state.json present", "ok": False, "detail": "missing"}],
            "errors": ["state.json missing"],
        }

    state = json.loads(state_path.read_text(encoding="utf-8"))
    results = state.get("results")
    if not isinstance(results, list) or not results:
        record("state.results non-empty", False, f"got {type(results).__name__}")
        return _finish(pack_dir, checks, errors, {})

    record("state.results non-empty", True, f"n={len(results)}")

    # --- 1. Postcondition totals ---
    by_model: dict[str, list] = defaultdict(list)
    by_task_model: dict[tuple[str, str], list] = defaultdict(list)
    for r in results:
        by_model[r["model"]].append(r)
        by_task_model[(r["task_id"], r["model"])].append(r)

    model_totals = {
        m: {"pass": sum(1 for r in rs if r["passed"]), "n": len(rs)}
        for m, rs in sorted(by_model.items())
    }
    task_totals = {
        f"{t}|{m}": {"pass": sum(1 for r in rs if r["passed"]), "n": len(rs)}
        for (t, m), rs in sorted(by_task_model.items())
    }
    total_pass = sum(1 for r in results if r["passed"])
    record(
        "postcondition totals",
        True,
        f"{total_pass}/{len(results)} overall; models={ {k: f'{v['pass']}/{v['n']}' for k,v in model_totals.items()} }",
        model_totals=model_totals,
        task_totals=task_totals,
    )

    # --- 2. RESULTS.md regeneration ---
    if results_path.is_file():
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            write_results_md(results, tmp_path)
            expected = tmp_path.read_text(encoding="utf-8")
            actual = results_path.read_text(encoding="utf-8")
            # Normalise trailing newlines
            ok = expected.rstrip("\n") + "\n" == actual.rstrip("\n") + "\n"
            if ok:
                record("RESULTS.md matches re-sum", True, f"sha256={sha256_file(results_path)[:16]}…")
            else:
                # Show a short unified-style hint
                exp_lines = expected.splitlines()
                act_lines = actual.splitlines()
                diffs = []
                for i, (a, b) in enumerate(zip(act_lines, exp_lines), 1):
                    if a != b:
                        diffs.append(f"L{i}: have {a!r} want {b!r}")
                        if len(diffs) >= 5:
                            break
                if len(act_lines) != len(exp_lines):
                    diffs.append(f"line count have={len(act_lines)} want={len(exp_lines)}")
                record("RESULTS.md matches re-sum", False, "; ".join(diffs) or "content mismatch")
        finally:
            tmp_path.unlink(missing_ok=True)
    else:
        record("RESULTS.md matches re-sum", False, "RESULTS.md missing")

    # --- 3 + 4. Trace completeness and consistency ---
    if not traces_dir.is_dir():
        record("traces/ present", False, "missing traces directory")
    else:
        on_disk = {p.name: p for p in traces_dir.glob("*.json")}
        expected_names: set[str] = set()
        state_trace_mismatches = 0
        missing = 0
        field_mismatches = 0
        for r in results:
            name = f"{r['task_id']}__{r['level']}__{safe_model(r['model'])}__t{r['trial']}.json"
            expected_names.add(name)
            path = traces_dir / name
            if not path.is_file():
                missing += 1
                continue
            try:
                tr = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                field_mismatches += 1
                errors.append(f"trace {name}: invalid JSON: {exc}")
                continue
            absent = REQUIRED_TRACE_KEYS - set(tr)
            if absent:
                field_mismatches += 1
                errors.append(f"trace {name}: missing keys {sorted(absent)}")
                continue
            for key in ("task_id", "level", "model", "trial", "passed"):
                if tr.get(key) != r.get(key):
                    field_mismatches += 1
                    errors.append(
                        f"trace {name}: {key} state={r.get(key)!r} trace={tr.get(key)!r}"
                    )
            if tr.get("machine") != r.get("machine"):
                field_mismatches += 1
                errors.append(
                    f"trace {name}: machine state={r.get('machine')!r} trace={tr.get('machine')!r}"
                )
            # state may store absolute desktop path; only compare basename if present
            st_trace = r.get("trace")
            if st_trace and Path(st_trace).name != name:
                state_trace_mismatches += 1

        orphans = sorted(set(on_disk) - expected_names)
        record(
            "trace completeness",
            missing == 0 and not orphans,
            f"expected={len(expected_names)} on_disk={len(on_disk)} missing={missing} orphans={len(orphans)}"
            + (f" orphan_sample={orphans[:3]}" if orphans else ""),
        )
        record(
            "state↔trace field consistency",
            field_mismatches == 0,
            f"mismatches={field_mismatches}"
            + (f"; first={errors[-1]}" if field_mismatches and errors else ""),
        )
        if state_trace_mismatches:
            record(
                "state.trace basename",
                False,
                f"{state_trace_mismatches} results whose trace basename ≠ naming convention",
            )
        else:
            record("state.trace basename", True, "all basenames match naming convention (or absent)")

    # --- 5. Model tags ---
    observed_models = set(by_model)
    if expected_models is not None:
        ok = observed_models == expected_models
        record(
            "model tags",
            ok,
            f"observed={sorted(observed_models)} expected={sorted(expected_models)}"
            if not ok
            else f"{sorted(observed_models)}",
        )
    else:
        record("model tags", True, f"observed={sorted(observed_models)} (no --expected-models)")

    # --- 6. Machine provenance ---
    machines = Counter(r.get("machine", "unknown") for r in results)
    ok_mach = set(machines) == {expected_machine}
    record(
        "machine provenance",
        ok_mach,
        f"counts={dict(machines)} expected={expected_machine!r}",
    )

    # --- 7. GPU residency ---
    ps_path = evidence_dir / "ollama_ps_samples.log"
    if not ps_path.is_file():
        record("GPU residency evidence", False, "evidence/ollama_ps_samples.log missing")
        residency = None
    else:
        residency = parse_ollama_ps(ps_path.read_text(encoding="utf-8", errors="replace"))
        # Only score models that appear both in the matrix and in the ps log.
        relevant = {m: residency["by_model"].get(m, {}) for m in observed_models}
        spill = {
            m: v
            for m, v in relevant.items()
            if v.get("cpu", 0) or v.get("mixed", 0)
        }
        missing_ps = [m for m, v in relevant.items() if not v]
        # Empty ps for a model can happen if sampling gap between loads — warn but
        # do not auto-fail if the log has *some* 100% GPU rows for every model that
        # was sampled. Missing entirely is a soft fail.
        if spill:
            record(
                "GPU residency (no CPU spill)",
                False,
                f"spill observations: {spill}",
                residency=residency,
            )
        elif missing_ps:
            record(
                "GPU residency (no CPU spill)",
                False,
                f"models never seen in ollama_ps samples: {missing_ps}; "
                f"seen={ {m: relevant[m] for m in observed_models if relevant[m]} }",
                residency=residency,
            )
        else:
            record(
                "GPU residency (no CPU spill)",
                True,
                f"samples={residency['samples']} all matrix models 100% GPU in every observation; "
                f"by_model={relevant}",
                residency=residency,
            )

    # --- git_rev coherence across traces ---
    revs = Counter()
    if traces_dir.is_dir():
        for p in traces_dir.glob("*.json"):
            try:
                revs[json.loads(p.read_text(encoding="utf-8")).get("git_rev", "unknown")] += 1
            except Exception:
                revs["unreadable"] += 1
    record(
        "trace git_rev coherence",
        len(revs) == 1 and "unreadable" not in revs,
        f"revs={dict(revs)}",
    )

    extras = {
        "n_results": len(results),
        "total_pass": total_pass,
        "model_totals": model_totals,
        "task_totals": task_totals,
        "machines": dict(machines),
        "models": sorted(observed_models),
        "state_sha256": sha256_file(state_path),
        "results_md_sha256": sha256_file(results_path) if results_path.is_file() else None,
        "ps_sha256": sha256_file(ps_path) if ps_path.is_file() else None,
        "git_revs": dict(revs),
    }
    return _finish(pack_dir, checks, errors, extras)


def _finish(pack_dir: Path, checks: list, errors: list, extras: dict) -> dict:
    ok = all(c["ok"] for c in checks) and not errors
    # errors may double-count field mismatches already in checks; only keep if a check failed
    return {
        "pack": str(pack_dir),
        "pack_name": pack_dir.name,
        "ok": ok,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "checker": {
            "uid": os.getuid(),
            "user": os.environ.get("USER") or os.environ.get("LOGNAME") or "unknown",
            "hostname": platform.node().split(".")[0],
            "argv": sys.argv,
        },
        "checks": checks,
        "errors": errors if not ok else [],
        **extras,
    }


def render_md(report: dict) -> str:
    lines = [
        f"# Pack re-derive — `{report.get('pack_name', report['pack'])}`",
        "",
        f"**Verdict:** `{'PASS' if report['ok'] else 'FAIL'}`",
        f"**Checked at:** {report['checked_at_utc']}",
        f"**Checker:** uid={report['checker']['uid']} user={report['checker']['user']} "
        f"host={report['checker']['hostname']}",
        f"**Pack path:** `{report['pack']}`",
        "",
        "## Checks",
        "",
        "| Check | Result | Detail |",
        "|---|---|---|",
    ]
    for c in report["checks"]:
        mark = "PASS" if c["ok"] else "FAIL"
        detail = c["detail"].replace("|", "\\|").replace("\n", " ")
        if len(detail) > 180:
            detail = detail[:177] + "…"
        lines.append(f"| {c['name']} | **{mark}** | {detail} |")
    lines.append("")
    if report.get("model_totals"):
        lines.append("## Re-derived postcondition totals (from state.json)")
        lines.append("")
        lines.append("| Model | Pass | N | Rate |")
        lines.append("|---|---:|---:|---:|")
        for m, v in report["model_totals"].items():
            rate = v["pass"] / v["n"] if v["n"] else 0
            lines.append(f"| `{m}` | {v['pass']} | {v['n']} | {rate:.0%} |")
        lines.append("")
        lines.append(
            f"Overall: **{report.get('total_pass')}/{report.get('n_results')}**"
        )
        lines.append("")
    if report.get("task_totals"):
        lines.append("## Per-task × model")
        lines.append("")
        lines.append("| Task | Model | Pass | N |")
        lines.append("|---|---|---:|---:|")
        for k, v in report["task_totals"].items():
            task, model = k.split("|", 1)
            lines.append(f"| `{task}` | `{model}` | {v['pass']} | {v['n']} |")
        lines.append("")
    lines.append("## Digests")
    lines.append("")
    lines.append(f"- `state.json` sha256: `{report.get('state_sha256')}`")
    lines.append(f"- `RESULTS.md` sha256: `{report.get('results_md_sha256')}`")
    lines.append(f"- `ollama_ps_samples.log` sha256: `{report.get('ps_sha256')}`")
    lines.append(f"- trace git_revs: `{report.get('git_revs')}`")
    lines.append(f"- machines: `{report.get('machines')}`")
    lines.append("")
    if report.get("errors"):
        lines.append("## Errors")
        lines.append("")
        for e in report["errors"][:50]:
            lines.append(f"- {e}")
        if len(report["errors"]) > 50:
            lines.append(f"- … and {len(report['errors']) - 50} more")
        lines.append("")
    lines.append(
        "This report re-derives aggregates from retained artifacts only. "
        "It does not re-run models or re-grade discarded temp fixtures."
    )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pack", type=Path, help="Path to pack directory (contains state.json)")
    ap.add_argument("--expected-machine", default="desktop")
    ap.add_argument(
        "--expected-models",
        nargs="*",
        default=None,
        help="If set, model set must match exactly",
    )
    ap.add_argument("--json-out", type=Path, default=None)
    ap.add_argument("--md-out", type=Path, default=None)
    ap.add_argument(
        "--write-into-pack",
        action="store_true",
        help="Write REDERIVE.json and REDERIVE.md into the pack directory",
    )
    args = ap.parse_args()
    expected_models = set(args.expected_models) if args.expected_models is not None else None
    report = rederive_pack(
        args.pack,
        expected_machine=args.expected_machine,
        expected_models=expected_models,
    )
    md = render_md(report)
    if args.write_into_pack:
        pack = args.pack.resolve()
        (pack / "REDERIVE.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        (pack / "REDERIVE.md").write_text(md)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if args.md_out:
        args.md_out.parent.mkdir(parents=True, exist_ok=True)
        args.md_out.write_text(md)
    # Always print the markdown summary for the verifier log.
    print(md)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
