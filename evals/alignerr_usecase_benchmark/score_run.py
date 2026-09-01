#!/usr/bin/env python3
"""Deterministic scorer for Alignerr-derived benchmark runs.

Replaces the original keyword scorer, which had four defects documented in
FINDING.md:

  1. No null-guard. An empty output scored 0/N, indistinguishable from a
     maximally wrong answer. qwen3-next's 0-byte AUB-3 output was reported
     as a capability score of 0/8.
  2. It measured vocabulary, not judgment. `recompute_arithmetic` matched the
     bare word "sum"; `gpu_cpu_crossover` matched the regex `3\\.0`, which
     hits any version number.
  3. It summed a correctness check and keyword hits into one integer, so
     gpt-oss:120b could pick the WRONG response on AUB-1 and still score 4/5 --
     identical to a model that picked right.
  4. It did not implement the 0-3 rubric the task specs declared, and printed
     a single collapsed total the README explicitly says not to produce.

Design: four classes, reported separately and never summed.

  STATUS    OK / INVALID (no output) / MALFORMED (contract sections missing)
  VERDICT   objectively right or wrong -- the point of the task
  COVERAGE  a consideration was mentioned; weak signal, explicitly labeled
  MANUAL    rubric dimensions no regex can judge; emitted unscored

Checks live in the task YAMLs, so this stays generic. Matching is anchored to
the output section a check belongs in, so a keyword in a preamble earns
nothing.

This scorer is still not an LLM judge. It reports what is mechanically
checkable and refuses to fake the rest.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
TASKS_DIR = ROOT / "tasks"

# Maps the task_id used in run filenames to its YAML spec.
TASK_FILES = {
    "aub1_code_preference": "aub_1_code_preference.yaml",
    "aub2_dispute_rederivation": "aub_2_dispute_rederivation.yaml",
    "aub3_mujoco_verification": "aub_3_mujoco_verification.yaml",
}


def load_specs() -> dict:
    specs = {}
    for task_id, fname in TASK_FILES.items():
        specs[task_id] = yaml.safe_load((TASKS_DIR / fname).read_text())
    return specs


def split_sections(text: str, section_names: list[str]) -> dict[str, str]:
    """Split model output into its declared contract sections.

    Returns {SECTION: body}. A section absent from the output is absent from
    the dict -- that is what MALFORMED is computed from.
    """
    if not section_names:
        return {}
    # Underscore and space are interchangeable in header names: models write
    # both "CORE_RULE:" and "**CORE RULE:**". Treating those as different
    # sections would report a missing section for what is a cosmetic variant,
    # which would zero every check in it.
    pattern = "|".join(re.escape(n).replace("_", "[_ ]") for n in section_names)
    # A section header is the name at line start, with optional markdown
    # decoration, terminated by EITHER a colon or end-of-line.
    #
    # The colon must be optional: models commonly emit "**MEASURED_CLAIMS**"
    # with no colon at all. Requiring one made every such output parse as
    # MALFORMED with all checks zeroed -- a scorer artifact indistinguishable
    # from a model that ignored the output contract. Caught by gpt-oss:120b's
    # AUB-3 output, which scored 0/2 verdict and 0/5 coverage on 4,672
    # characters of correctly-sectioned text.
    header_re = re.compile(
        rf"^[ \t]*(?:#{{1,6}}[ \t]*)?(?:\*\*|__|\*)?[ \t]*({pattern})"
        rf"[ \t]*(?:\*\*|__|\*)?[ \t]*(?::|$)",
        re.IGNORECASE | re.MULTILINE,
    )
    matches = list(header_re.finditer(text))
    out: dict[str, str] = {}
    for i, m in enumerate(matches):
        # Normalize back to the declared form: the regex accepts "CORE RULE"
        # as well as "CORE_RULE", so the captured text must be canonicalized
        # or the lookup misses what the split just found.
        name = re.sub(r"\s+", "_", m.group(1).strip()).upper()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        # Later duplicates append rather than clobber.
        out[name] = (out.get(name, "") + "\n" + text[start:end]).strip()
    return out


def scope_text(check: dict, sections: dict[str, str], full: str) -> str:
    """The text a check is allowed to match against.

    Section-anchored by default. Falls back to the whole document only when a
    check declares no section -- and if the declared sections are missing from
    a malformed output, the check simply has nothing to match, which is the
    honest result.
    """
    names = check.get("sections") or ([check["section"]] if check.get("section") else [])
    if not names:
        return full
    return "\n".join(sections.get(n.upper(), "") for n in names)


def run_check(check: dict, sections: dict[str, str], full: str) -> bool:
    body = scope_text(check, sections, full)
    if not body.strip():
        return False
    hit = any(re.search(p, body, re.IGNORECASE | re.DOTALL) for p in check["patterns"])
    if not hit:
        return False
    for bad in check.get("forbidden", []):
        if re.search(bad, body, re.IGNORECASE | re.DOTALL):
            return False
    return True


def score_one(text: str, spec: dict) -> dict:
    scoring = spec.get("scoring", {})
    contract = [s.upper() for s in scoring.get("contract_sections", [])]

    if not text.strip():
        return {
            "status": "INVALID",
            "status_detail": "empty output -- model produced nothing; not a score of 0",
            "contract": {"present": [], "missing": contract},
            "verdict": {}, "coverage": {},
            "manual": [m["name"] for m in scoring.get("manual", [])],
            "chars": 0,
        }

    sections = split_sections(text, contract)
    present = [s for s in contract if s in sections]
    missing = [s for s in contract if s not in sections]

    verdict = {c["name"]: run_check(c, sections, text) for c in scoring.get("verdict", [])}
    coverage = {c["name"]: run_check(c, sections, text) for c in scoring.get("coverage", [])}

    return {
        "status": "OK" if not missing else "MALFORMED",
        "status_detail": "" if not missing else f"missing contract sections: {', '.join(missing)}",
        "contract": {"present": present, "missing": missing},
        "verdict": verdict,
        "coverage": coverage,
        "manual": [m["name"] for m in scoring.get("manual", [])],
        "chars": len(text),
    }


def fmt(d: dict) -> str:
    if not d:
        return "-"
    return " ".join(f"{'+' if v else '.'}{k}" for k, v in d.items())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    args = ap.parse_args()

    specs = load_specs()
    manifest = json.loads((args.run_dir / "manifest.json").read_text())

    rows = []
    for item in manifest["results"]:
        spec = specs[item["task"]]
        text = (args.run_dir / item["stdout_path"]).read_text(errors="replace")
        rows.append({**item, **score_one(text, spec)})

    report = {"run_dir": str(args.run_dir), "scorer": "v2-split-classes", "rows": rows}
    (args.run_dir / "scores.json").write_text(json.dumps(report, indent=2))

    print("# Alignerr use-case benchmark scores\n")
    print("> VERDICT and COVERAGE are reported separately and never summed. VERDICT is")
    print("> the objectively-correct conclusion; COVERAGE is a weak presence signal.")
    print("> INVALID means no output was produced -- it is not a score of zero.\n")

    for task_id in TASK_FILES:
        task_rows = [r for r in rows if r["task"] == task_id]
        if not task_rows:
            continue
        print(f"## {task_id}\n")
        print("| model | status | verdict | coverage | chars |")
        print("|---|---|---|---:|---:|")
        for r in sorted(task_rows, key=lambda x: x["label"]):
            v = sum(r["verdict"].values())
            vt = len(r["verdict"])
            c = sum(r["coverage"].values())
            ct = len(r["coverage"])
            vs = "-" if r["status"] == "INVALID" else f"{v}/{vt}"
            cs = "-" if r["status"] == "INVALID" else f"{c}/{ct}"
            print(f"| {r['label']} | {r['status']} | {vs} | {cs} | {r['chars']} |")
        print()
        for r in sorted(task_rows, key=lambda x: x["label"]):
            detail = f" -- {r['status_detail']}" if r["status_detail"] else ""
            print(f"- **{r['label']}**{detail}")
            if r["status"] != "INVALID":
                print(f"  - verdict:  {fmt(r['verdict'])}")
                print(f"  - coverage: {fmt(r['coverage'])}")
        print()

    manual = sorted({m for r in rows for m in r["manual"]})
    print("## Unscored (require a human pass)\n")
    print("These rubric dimensions are not mechanically checkable. They are listed")
    print("rather than approximated, because a keyword match cannot judge them:\n")
    for m in manual:
        print(f"- {m}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
