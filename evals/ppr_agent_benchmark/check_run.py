#!/usr/bin/env python3
"""Typed gold-standard checker for the PPR agent benchmark.

Lane A claims grounded reproduction only; Lane B is the only
execution-competence lane.

  python3 check_run.py <run_dir>
  python3 check_run.py <run_dir> --write
  python3 check_run.py --lane-b [--cwd PATH] [--only id,...] [--write]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DEFAULT_MANIFEST = HERE / "manifests" / "gold_manifest_v1.json"
DEFAULT_PPR_CWD = Path("/home/blueaz/Python/ppr-agent")
LANE_B_TIMEOUT_S = 60
HHI_TOLERANCE = 0.01
NUMERIC_VALUE_RE = re.compile(r"^-?[0-9][0-9,]*(\.[0-9]+)?$")
PROTECTED_SCORE_NAMES = frozenset({"scores.json", "SCORES.md"})


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def lane_a_spec_by_id(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {task["id"]: task for task in manifest["lane_a"]}


def sidecar_json_path(run_dir: Path, result: dict[str, Any]) -> Path | None:
    stdout_path = result.get("stdout_path")
    if isinstance(stdout_path, str) and stdout_path.endswith(".out.md"):
        candidate = run_dir / stdout_path.replace(".out.md", ".json")
        if candidate.is_file():
            return candidate
    task = result.get("task")
    label = result.get("label")
    if task and label:
        candidate = run_dir / f"{task}__{label}.json"
        if candidate.is_file():
            return candidate
    return None


def extract_openai_content(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    """If raw_response is OpenAI-compatible, return (content, fail_reason).

    content is None when this payload is not that shape (caller should fall back).
    """
    raw = payload.get("raw_response")
    if not isinstance(raw, dict):
        return None, None
    choices = raw.get("choices")
    if not isinstance(choices, list) or not choices:
        return None, None
    first = choices[0]
    if not isinstance(first, dict):
        return None, None
    msg = first.get("message")
    if not isinstance(msg, dict):
        return None, None
    content = msg.get("content") or ""
    reasoning = msg.get("reasoning_content") or ""
    if str(content).strip():
        return str(content), None
    if str(reasoning).strip():
        return "", "finish_reason_length_or_reasoning_only"
    return "", "empty_content"


def extract_content(run_dir: Path, result: dict[str, Any]) -> tuple[str, str | None]:
    sidecar = sidecar_json_path(run_dir, result)
    payload: dict[str, Any] | None = None
    if sidecar is not None:
        try:
            loaded = json.loads(sidecar.read_text())
        except (OSError, json.JSONDecodeError):
            loaded = None
        if isinstance(loaded, dict):
            payload = loaded
            openai_content, reason = extract_openai_content(payload)
            if openai_content is not None:
                return openai_content, reason
            stdout = payload.get("stdout") or ""
            if str(stdout).strip():
                return str(stdout), None

    stdout_path = result.get("stdout_path")
    if isinstance(stdout_path, str):
        out_file = run_dir / stdout_path
        if out_file.is_file():
            text = out_file.read_text(errors="replace")
            if text.strip():
                return text, None
            return "", "empty_content"
    return "", "empty_content"


def looks_like_number(value: str) -> bool:
    return bool(NUMERIC_VALUE_RE.fullmatch(value.strip()))


def value_present(text: str, needle: str) -> bool:
    """Case-insensitive exact-substring; numbers are comma-tolerant."""
    hay = text.casefold()
    pin = str(needle).casefold()
    if pin in hay:
        if looks_like_number(needle):
            compact_pin = pin.replace(",", "")
            compact_hay = hay.replace(",", "")
            return (
                re.search(
                    r"(?<![0-9])" + re.escape(compact_pin) + r"(?![0-9])",
                    compact_hay,
                )
                is not None
            )
        return True
    if looks_like_number(needle):
        compact_pin = pin.replace(",", "")
        compact_hay = hay.replace(",", "")
        return (
            re.search(
                r"(?<![0-9])" + re.escape(compact_pin) + r"(?![0-9])",
                compact_hay,
            )
            is not None
        )
    return False


def weight_for(spec: dict[str, Any], check_id: str) -> int:
    weights = spec.get("score_weights") or {}
    try:
        return int(weights.get(check_id, 1))
    except (TypeError, ValueError):
        return 1


def score_lane_a_row(
    spec: dict[str, Any],
    content: str,
    content_reason: str | None,
    returncode: int,
) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    reasons: list[str] = []
    score = 0
    max_score = 0

    content_ok = content_reason is None and bool(content.strip())
    rc_ok = returncode == 0
    if not rc_ok:
        reasons.append(f"returncode={returncode}")
    if content_reason:
        reasons.append(content_reason)
    elif not content.strip():
        reasons.append("empty_content")
        content_reason = "empty_content"

    scorable = content_ok and rc_ok

    for heading in spec.get("required_headings") or []:
        cid = f"heading:{heading}"
        w = weight_for(spec, cid)
        max_score += w
        ok = scorable and value_present(content, heading)
        checks[cid] = ok
        if ok:
            score += w
        elif scorable:
            reasons.append(f"missing_heading:{heading}")

    for value in spec.get("required_values") or []:
        cid = f"value:{value}"
        w = weight_for(spec, cid)
        max_score += w
        ok = scorable and value_present(content, str(value))
        checks[cid] = ok
        if ok:
            score += w
        elif scorable:
            reasons.append(f"missing_value:{value}")

    for value in spec.get("forbidden_values") or []:
        cid = f"forbidden:{value}"
        w = weight_for(spec, cid)
        max_score += w
        present = bool(content.strip()) and value_present(content, str(value))
        ok = scorable and not present
        checks[cid] = ok
        if ok:
            score += w
        elif scorable and present:
            reasons.append(f"forbidden_present:{value}")

    fully = scorable and all(checks.values()) if checks else scorable
    return {
        "pass": fully,
        "score": score,
        "max_score": max_score,
        "checks": checks,
        "reason": reasons[0] if reasons else None,
        "reasons": reasons,
        "content_reason": content_reason,
        "returncode": returncode,
        "content_chars": len(content.strip()),
    }


def score_lane_a_run(run_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    run_manifest_path = run_dir / "manifest.json"
    if not run_manifest_path.is_file():
        raise FileNotFoundError(f"REQUIRE manifest.json: missing at {run_manifest_path}")
    run_manifest = json.loads(run_manifest_path.read_text())
    results = run_manifest.get("results")
    if not isinstance(results, list):
        raise TypeError("run manifest.json has no results list")

    specs = lane_a_spec_by_id(manifest)
    rows: list[dict[str, Any]] = []
    for item in results:
        task_id = item.get("task")
        spec = specs.get(task_id)
        if spec is None:
            row = {
                **item,
                "pass": False,
                "score": 0,
                "max_score": 0,
                "checks": {},
                "reason": f"unknown_task:{task_id}",
                "reasons": [f"unknown_task:{task_id}"],
            }
            rows.append(row)
            continue
        content, content_reason = extract_content(run_dir, item)
        scored = score_lane_a_row(spec, content, content_reason, int(item.get("returncode", 1)))
        rows.append({**item, **scored})

    fully_pass = bool(rows) and all(r.get("pass") for r in rows)
    reasons = sorted({r.get("reason") for r in rows if r.get("reason")})
    return {
        "checker": "check_run.py",
        "lane": "A",
        "gold_manifest": str(DEFAULT_MANIFEST),
        "run_dir": str(run_dir),
        "fully_pass": fully_pass,
        "rows": rows,
        "reasons": reasons,
        "note": (
            "Lane A claims grounded reproduction only; "
            "Lane B is the only execution-competence lane."
        ),
    }


def parse_tools_listing(stdout: str) -> dict[str, Any]:
    names: list[str] = []
    for line in stdout.splitlines():
        if not line or line[:1].isspace():
            continue
        if "tools registered" in line.lower():
            continue
        names.append(line.split()[0])
    return {"tools_count": len(names), "tool_names": names}


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def numbers_equal(expected: Any, actual: Any, key: str) -> bool:
    try:
        exp_f = float(expected)
        act_f = float(actual)
    except (TypeError, ValueError):
        return False
    if key in {"hhi", "share_pct"} or isinstance(expected, float) or isinstance(actual, float):
        return abs(act_f - exp_f) <= HHI_TOLERANCE
    return act_f == exp_f


def match_expected(expected: Any, actual: Any, key: str = "") -> list[str]:
    """Return a list of mismatch strings (empty means match)."""
    mismatches: list[str] = []
    path = key or "$"

    if key == "rule_hits" or path.endswith(".rule_hits"):
        if not isinstance(expected, list) or not isinstance(actual, list):
            return [f"{path}: rule_hits expected list, got {type(actual).__name__}"]
        missing = [item for item in expected if item not in actual]
        if missing:
            return [f"{path}: missing {missing}; actual={actual}"]
        return []

    if expected is None:
        if actual is not None:
            return [f"{path}: expected null, got {actual!r}"]
        return []

    if isinstance(expected, bool):
        if actual is not expected:
            return [f"{path}: expected {expected!r}, got {actual!r}"]
        return []

    if is_number(expected):
        if not numbers_equal(expected, actual, key.split(".")[-1] if key else ""):
            return [f"{path}: expected {expected!r}, got {actual!r}"]
        return []

    if isinstance(expected, dict):
        if (
            isinstance(actual, list)
            and actual
            and all(isinstance(item, dict) and "company" in item for item in actual)
        ):
            indexed = {item.get("company"): item for item in actual}
            for sub_key, sub_exp in expected.items():
                if sub_key not in indexed:
                    mismatches.append(f"{path}.{sub_key}: company not in actual")
                else:
                    mismatches.extend(
                        match_expected(sub_exp, indexed[sub_key], f"{path}.{sub_key}")
                    )
            return mismatches
        if not isinstance(actual, dict):
            return [f"{path}: expected object, got {type(actual).__name__}"]
        for sub_key, sub_exp in expected.items():
            mismatches.extend(match_expected(sub_exp, actual.get(sub_key), f"{path}.{sub_key}"))
        return mismatches

    if isinstance(expected, list):
        if not isinstance(actual, list):
            return [f"{path}: expected list, got {type(actual).__name__}"]
        dict_items = [item for item in expected if isinstance(item, dict)]
        if (
            dict_items
            and all("company" in item for item in dict_items)
            and actual
            and all(isinstance(item, dict) and "company" in item for item in actual)
        ):
            indexed = {item.get("company"): item for item in actual}
            for item in expected:
                company = item.get("company")
                if company not in indexed:
                    mismatches.append(f"{path}: missing company {company!r}")
                else:
                    mismatches.extend(match_expected(item, indexed[company], f"{path}[{company}]"))
            return mismatches
        if len(actual) < len(expected):
            return [f"{path}: expected at least {len(expected)} items, got {len(actual)}"]
        for i, item in enumerate(expected):
            mismatches.extend(match_expected(item, actual[i], f"{path}[{i}]"))
        return mismatches

    if actual != expected:
        return [f"{path}: expected {expected!r}, got {actual!r}"]
    return []


def run_lane_b_entry(entry: dict[str, Any], cwd: Path) -> dict[str, Any]:
    command = entry["command"]
    parse = entry.get("parse") or "json"
    expected = entry.get("expected") or {}
    try:
        proc = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=LANE_B_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "id": entry["id"],
            "command": command,
            "pass": False,
            "returncode": None,
            "mismatches": [f"timeout after {LANE_B_TIMEOUT_S}s"],
        }
    except OSError as exc:
        return {
            "id": entry["id"],
            "command": command,
            "pass": False,
            "returncode": None,
            "mismatches": [f"exec_error: {exc}"],
        }

    mismatches: list[str] = []
    if proc.returncode != 0:
        mismatches.append(f"returncode={proc.returncode}")

    parsed: Any
    if parse == "tools_listing":
        parsed = parse_tools_listing(proc.stdout)
    else:
        try:
            parsed = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            parsed = None
            mismatches.append(f"json_parse_error: {exc}")

    if parsed is not None:
        mismatches.extend(match_expected(expected, parsed))

    return {
        "id": entry["id"],
        "command": command,
        "pass": not mismatches,
        "returncode": proc.returncode,
        "mismatches": mismatches,
    }


def score_lane_b(
    manifest: dict[str, Any],
    cwd: Path,
    only_ids: set[str] | None,
) -> dict[str, Any]:
    entries = list(manifest.get("lane_b") or [])
    if only_ids:
        entries = [e for e in entries if e.get("id") in only_ids]
        missing = only_ids - {e.get("id") for e in entries}
        if missing:
            raise KeyError(f"unknown Lane B ids: {sorted(missing)}")
    rows = [run_lane_b_entry(entry, cwd) for entry in entries]
    fully_pass = bool(rows) and all(r["pass"] for r in rows)
    return {
        "checker": "check_run.py",
        "lane": "B",
        "gold_manifest": str(DEFAULT_MANIFEST),
        "cwd": str(cwd),
        "fully_pass": fully_pass,
        "rows": rows,
        "note": (
            "Lane A claims grounded reproduction only; "
            "Lane B is the only execution-competence lane."
        ),
    }


def print_lane_a_summary(report: dict[str, Any]) -> None:
    print(
        f"Lane A fully_pass={report['fully_pass']} "
        f"rows={len(report['rows'])} reasons={report.get('reasons')}"
    )
    print("| model | task | pass | score | reason |")
    print("|---|---|---|---:|---|")
    for row in report["rows"]:
        print(
            f"| {row.get('label', '')} | {row.get('task', '')} | "
            f"{row.get('pass')} | {row.get('score')}/{row.get('max_score')} | "
            f"{row.get('reason') or ''} |"
        )


def print_lane_b_summary(report: dict[str, Any]) -> None:
    print(f"Lane B fully_pass={report['fully_pass']} cwd={report['cwd']}")
    for row in report["rows"]:
        status = "PASS" if row["pass"] else "FAIL"
        extra = ""
        if row["mismatches"]:
            extra = " " + "; ".join(row["mismatches"])
        print(f"  {status} {row['id']} rc={row['returncode']}{extra}")


def write_if_allowed(path: Path, text: str) -> None:
    if path.name in PROTECTED_SCORE_NAMES:
        raise RuntimeError(f"refusing to write protected file {path}")
    path.write_text(text)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dir", nargs="?", type=Path)
    ap.add_argument("--lane-b", action="store_true")
    ap.add_argument("--cwd", type=Path, default=DEFAULT_PPR_CWD)
    ap.add_argument("--only", default=None, help="Comma-separated Lane B ids")
    ap.add_argument(
        "--write",
        action="store_true",
        help="Write scores_strict.json (Lane A) or lane_b_results.json (Lane B)",
    )
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    manifest = load_manifest(args.manifest)

    if args.lane_b:
        only = None
        if args.only:
            only = {item.strip() for item in args.only.split(",") if item.strip()}
        report = score_lane_b(manifest, args.cwd, only)
        print_lane_b_summary(report)
        print(json.dumps(report, indent=2, default=str))
        if args.write:
            out = Path.cwd() / "lane_b_results.json"
            write_if_allowed(out, json.dumps(report, indent=2, default=str) + "\n")
            print(f"wrote {out}", file=sys.stderr)
        return 0 if report["fully_pass"] else 2

    if args.run_dir is None:
        print("run_dir is required unless --lane-b", file=sys.stderr)
        return 2
    run_dir = args.run_dir.expanduser().resolve()
    try:
        report = score_lane_a_run(run_dir, manifest)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print_lane_a_summary(report)
    print(json.dumps(report, indent=2, default=str))
    if args.write:
        out = run_dir / "scores_strict.json"
        write_if_allowed(out, json.dumps(report, indent=2, default=str) + "\n")
        print(f"wrote {out}", file=sys.stderr)
    return 0 if report["fully_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
