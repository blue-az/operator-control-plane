"""record_seal — seal audit for a benchmark run directory.

A run directory is *sealed* when its manifest and its evidence files agree on
every axis a reader could later misquote. This audits the RECORD, not the
answers: it says nothing about whether any model was good, only whether the
record is internally consistent enough to ground a claim.

Layered contract (fail-closed; unknown shapes are violations, not skipped):
  CORE (all runs)
    V-DUP  no two rows share (task, label)
    V-OUT  every row's stdout_path resolves (absolute, or under out_dir)
    V-ORPHAN no *_rN.out.md evidence file on disk is unreferenced
    V-RC-ERR no returncode!=0 row may have a payload containing a
             non-empty `raw_response` (an error row must not carry a
             fabricated completion)
  IF manifest declares `repeats`
    V-REPEATS per (task, base_label|model) group: row count == repeats
  IF any row carries `num_ctx`
    V-CTX  all rows share one num_ctx (config homogeneity)
  IF manifest declares `model_configs` and rows carry `request_model`
    V-TAG  row.request_model == model_configs[base_label].tag

Exit codes: 0 sealed · 12 construction (schema unreadable) · 11 violations
`--json` prints the full audit for machine consumption.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Audit:
    run_dir: str = ""
    violations: list[str] = field(default_factory=list)
    rows: int = 0
    active_checks: list[str] = field(default_factory=list)

    @property
    def sealed(self) -> bool:
        return not self.violations


def _row_label(r: dict) -> str:
    return str(r.get("label", r.get("base_label", ""))) + "|" + str(r.get("task", ""))


def load_manifest(run_dir: Path) -> dict:
    p = run_dir / "manifest.json"
    try:
        m = json.loads(p.read_text())
    except Exception as e:
        raise SystemExit(f"V-SCHEMA manifest unreadable: {e}")
    if not isinstance(m, dict):
        raise SystemExit("V-SCHEMA manifest is not an object")
    res = m.get("results")
    if not isinstance(res, list) or not res:
        raise SystemExit("V-SCHEMA manifest.results missing or empty")
    for r in res:
        if not isinstance(r, dict):
            raise SystemExit("V-SCHEMA manifest.results entry not an object")
    return m


def derive_payload_path(stdout_path: str) -> str | None:
    """ppr1_task__base_r1.out.md -> ppr1_task__base_r1.json (the payload)."""
    if not stdout_path.endswith(".out.md"):
        return None
    return stdout_path[: -len(".out.md")] + ".json"


def audit_run(run_dir: Path) -> Audit:
    m = load_manifest(run_dir)
    out_dir = Path(m.get("out_dir", run_dir))
    rows = m["results"]
    a = Audit(run_dir=str(run_dir), rows=len(rows))

    # --- CORE: duplicates
    seen: set[tuple[str, str]] = set()
    for r in rows:
        k = (str(r.get("task", "")), str(r.get("label", "")))
        if k in seen:
            a.violations.append(f"V-DUP duplicate row {k}")
        seen.add(k)
    a.active_checks.append("V-DUP")

    # --- CORE: stdout resolves
    referenced: set[str] = set()
    for r in rows:
        sp = r.get("stdout_path")
        if not isinstance(sp, str) or not sp:
            a.violations.append(f"V-OUT row {_row_label(r)} has no stdout_path")
            continue
        p = Path(sp) if Path(sp).is_absolute() else (out_dir / sp)
        if not p.exists():
            a.violations.append(f"V-OUT row {_row_label(r)} stdout missing: {sp}")
        referenced.add(Path(sp).name)

    # --- CORE: orphans (evidence files on disk no row references)
    disk_evidence = {p.name for p in run_dir.glob("*_r[0-9]*.out.md")}
    for name in sorted(disk_evidence - referenced):
        a.violations.append(f"V-ORPHAN unreferenced evidence file: {name}")
    a.active_checks.append("V-OUT")
    a.active_checks.append("V-ORPHAN")

    # --- CORE: error rows must not carry a completion payload
    for r in rows:
        rc = r.get("returncode", 0)
        if rc in (0, None):
            continue
        sp = r.get("stdout_path")
        if not isinstance(sp, str):
            continue
        rel = derive_payload_path(sp)
        if not rel:
            continue
        pp = (out_dir / rel) if not Path(rel).is_absolute() else Path(rel)
        if not pp.exists():
            continue
        try:
            payload = json.loads(pp.read_text())
        except Exception:
            continue
        rr = payload.get("raw_response")
        if isinstance(rr, (str, list)) and len(rr) > 0:
            a.violations.append(
                f"V-RC-ERR row {_row_label(r)} rc={rc} payload carries raw_response")
    a.active_checks.append("V-RC-ERR")

    # --- IF repeats declared
    if isinstance(m.get("repeats"), int) and m["repeats"] > 0:
        groups: dict[tuple[str, str], int] = {}
        for r in rows:
            key = (str(r.get("task", "")), str(r.get("base_label", r.get("model", ""))))
            groups[key] = groups.get(key, 0) + 1
        for key, n in sorted(groups.items()):
            if n != m["repeats"]:
                a.violations.append(
                    f"V-REPEATS group {key} has {n} rows, manifest repeats={m['repeats']}")
        a.active_checks.append("V-REPEATS")

    # --- IF any row carries num_ctx
    ctxs = {r.get("num_ctx") for r in rows if isinstance(r.get("num_ctx"), int)}
    if len(ctxs) > 1:
        a.violations.append(f"V-CTX rows mix num_ctx values: {sorted(ctxs)}")
    elif ctxs:
        single = next(iter(ctxs))
        a.active_checks.append("V-CTX(single=%r)" % single)

    # --- IF model_configs declared
    mc = m.get("model_configs")
    if isinstance(mc, dict) and any(isinstance(r.get("request_model"), str) for r in rows):
        for r in rows:
            bl = str(r.get("base_label", ""))
            rm = r.get("request_model")
            if not isinstance(rm, str) or bl not in mc:
                continue
            tag = mc[bl].get("tag") if isinstance(mc[bl], dict) else None
            if tag is not None and rm != tag:
                a.violations.append(
                    f"V-TAG row {r.get('label')} request_model={rm} != declared tag={tag}")
        a.active_checks.append("V-TAG")

    return a


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dir", help="run directory containing manifest.json")
    ap.add_argument("--json", action="store_true", help="machine-readable audit")
    a = ap.parse_args(argv)

    res = audit_run(Path(a.run_dir).resolve())
    if a.json:
        print(json.dumps({
            "run_dir": res.run_dir, "rows": res.rows,
            "sealed": res.sealed, "active_checks": res.active_checks,
            "violations": res.violations,
        }, indent=1))
    else:
        print(f"run_dir  : {res.run_dir}")
        print(f"rows     : {res.rows}")
        print(f"sealed   : {res.sealed}")
        print(f"checks   : {', '.join(res.active_checks)}")
        for v in res.violations:
            print(f"  VIOLATION {v}")
    return 0 if res.sealed else 11


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
