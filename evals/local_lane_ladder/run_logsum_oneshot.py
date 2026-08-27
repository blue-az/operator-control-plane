#!/usr/bin/env python3
"""One-shot strict-log-format: file in the prompt, no opr.

Asks whether qwen3.6 beautifies when it actually writes, vs leaving the
stub in the tool loop. Grade is the same check_logsum.py battery.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import requests

API = "http://127.0.0.1:11434/api/generate"
PACK = Path(__file__).resolve().parent / "fixtures" / "logsum-oneshot"
MODELS = ("qwen3.6:27b", "qwen3.8:27b", "gemma4:26b")
TRIALS = 6
NUM_CTX = 16384

STUB = '''def error_report(log_text):
    """Summarise ERROR lines per UTC hour.

    Each log line looks like:
        2026-08-11T14:23:05Z LEVEL message

    LEVEL is one of INFO, WARN, ERROR and is matched case-sensitively.
    Return a list of strings, one per hour that has at least one ERROR,
    formatted exactly as "HH: N errors" -- two-digit hour, then a colon and
    a single space, then the count, then a single space and the literal word
    "errors" even when the count is 1. Sort ascending by hour. Ignore lines
    that do not match the shape above. Return [] when there are no errors.
    """
    raise NotImplementedError
'''

TEST = r'''import sys
sys.dont_write_bytecode = True
sys.path.insert(0, ".")
from src.logsum import error_report

BASIC = (
    "2026-08-11T09:15:00Z ERROR disk full\n"
    "2026-08-11T14:23:05Z INFO started\n"
    "not a log line at all\n"
    "2026-08-11T14:41:00Z ERROR timeout\n"
    "2026-08-11T14:52:00Z ERROR timeout again\n"
    "2026-08-11T15:00:00Z WARN slow\n"
)
got = error_report(BASIC)
assert got == ["09: 1 errors", "14: 2 errors"], f"got {got!r}"
assert error_report("2026-08-11T10:00:00Z INFO fine\n") == [], "no errors must give []"
assert error_report("") == [], "empty input must give []"
midnight = error_report("2026-08-12T00:04:00Z ERROR boom\n")
assert midnight == ["00: 1 errors"], f"midnight hour must zero-pad, got {midnight!r}"
assert error_report("2026-08-11T11:00:00Z error lowercase\n") == [], "LEVEL is case-sensitive"
print("LOGSUM_OK")
'''

PROMPT = f"""Implement error_report. Reply with only the complete contents of src/logsum.py.
No markdown, no preamble.

The function must satisfy this docstring and these exact strings:
["09: 1 errors", "14: 2 errors"]
["00: 1 errors"]
[] when there are no ERROR lines.
The word is the literal "errors" even when the count is 1. Zero-pad the hour.

Current file:
{STUB}
"""


def extract_py(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    m = re.search(r"```(?:python)?\s*\n(.*?)```", t, re.S | re.I)
    if m:
        t = m.group(1).strip()
    # drop a leading "src/logsum.py" filename line
    lines = t.splitlines()
    if lines and lines[0].strip() in {"src/logsum.py", "# src/logsum.py"}:
        t = "\n".join(lines[1:]).strip()
    return t


def classify(src: str, test_out: str, rc: int) -> str:
    if not src.strip():
        return "no_code"
    if "raise NotImplementedError" in src and "def error_report" in src:
        if src.count("def error_report") == 1 and src.strip().endswith("raise NotImplementedError"):
            return "left_stub"
    if rc == 0 and "LOGSUM_OK" in test_out:
        return "pass"
    blob = test_out
    if re.search(r"1 error(?!s)", blob) or "'09: 1 error'" in blob or '"09: 1 error"' in blob:
        return "nicer_singular"
    if "00: 0" in blob or "0: 1" in blob or "midnight" in blob.lower():
        return "pad_or_hour"
    if "NotImplementedError" in blob:
        return "left_stub"
    if "AssertionError" in blob and "got" in blob:
        return "wrong_strings"
    if rc != 0:
        return "crash_or_syntax"
    return "other"


def unload(model: str) -> None:
    try:
        requests.post(API, json={"model": model, "keep_alive": 0}, timeout=120)
    except Exception:
        pass


def main() -> int:
    PACK.mkdir(parents=True, exist_ok=True)
    (PACK / "traces").mkdir(exist_ok=True)
    rows = []
    print(f"logsum-oneshot models={MODELS} n={TRIALS} think=off no opr", flush=True)
    for model in MODELS:
        unload(model)
        for trial in range(1, TRIALS + 1):
            print(f"[{model} t{trial}] running...", flush=True)
            r = requests.post(
                API,
                json={
                    "model": model,
                    "prompt": PROMPT,
                    "stream": False,
                    "think": False,
                    "keep_alive": "3m",
                    "options": {
                        "num_ctx": NUM_CTX,
                        "temperature": 0.8,
                        "num_predict": 1024,
                    },
                },
                timeout=600,
            )
            r.raise_for_status()
            d = r.json()
            content = d.get("response") or ""
            src = extract_py(content)
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                (root / "src").mkdir()
                (root / "src" / "__init__.py").write_text("", encoding="utf-8")
                (root / "src" / "logsum.py").write_text(src or "raise NotImplementedError\n", encoding="utf-8")
                (root / "tests").mkdir()
                (root / "tests" / "check_logsum.py").write_text(TEST, encoding="utf-8")
                proc = subprocess.run(
                    ["python3", "tests/check_logsum.py"],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                test_out = (proc.stdout or "") + (proc.stderr or "")
                rc = proc.returncode
            kind = classify(src, test_out, rc)
            rec = {
                "model": model,
                "trial": trial,
                "kind": kind,
                "rc": rc,
                "eval_count": d.get("eval_count"),
                "think_chars": len(d.get("thinking") or ""),
                "src_chars": len(src),
                "test_out": test_out[-500:],
                "src_head": src[:400],
                "recorded_utc": datetime.now(timezone.utc).isoformat(),
            }
            rows.append(rec)
            (PACK / "traces" / f"{model.replace(':', '-')}__t{trial}.json").write_text(
                json.dumps(rec, indent=2), encoding="utf-8"
            )
            print(f"[{model} t{trial}] {kind} rc={rc} src={len(src)}", flush=True)
        unload(model)

    (PACK / "state.json").write_text(json.dumps({"results": rows}, indent=2), encoding="utf-8")
    lines = [
        "# logsum one-shot — no opr",
        "",
        "File in the prompt. Grade is `check_logsum.py`. think off, ctx 16384.",
        "",
        "| model | t | kind | rc | src_ch | think_ch |",
        "|---|---:|---|---:|---:|---:|",
    ]
    from collections import Counter, defaultdict

    bag: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        lines.append(
            f"| `{r['model']}` | {r['trial']} | {r['kind']} | {r['rc']} | "
            f"{r['src_chars']} | {r['think_chars']} |"
        )
        bag[r["model"]][r["kind"]] += 1
    lines += ["", "## Totals", "", "| model | pass | nicer_singular | left_stub | other |",
              "|---|---:|---:|---:|---:|"]
    for m in MODELS:
        c = bag[m]
        other = TRIALS - c["pass"] - c["nicer_singular"] - c["left_stub"]
        lines.append(
            f"| `{m}` | {c['pass']}/{TRIALS} | {c['nicer_singular']} | "
            f"{c['left_stub']} | {other} |"
        )
    (PACK / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {PACK / 'RESULTS.md'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
