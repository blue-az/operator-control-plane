"""Deterministic grader for the repo-orientation probe.

Grades ONLY the model's final answer (the span after opr's '--- Output ---').
Tool dumps contain the gold files; scoring those is a false pass.

Facets are the five the prompt asked for. Concise answers can pass.
Length is recorded, never used as a gate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_OUTPUT_MARK = "--- Output ---"


def extract_answer(stdout: str) -> str:
    if _OUTPUT_MARK not in stdout:
        return ""
    body = stdout.split(_OUTPUT_MARK, 1)[1]
    body = re.sub(r"\[Task complete[^\]]*\]", "", body)
    body = re.sub(r"(?m)^-+\s*$", "", body)
    return body.strip()


def _has(rx: str, text: str) -> bool:
    return re.search(rx, text, flags=re.IGNORECASE) is not None


def grade_answer(answer: str) -> dict:
    """Return per-facet sourced/missing and pass=all five sourced."""
    a = answer or ""
    facets = {
        "what_for": _has(
            r"\b(sop|deterministic|tau-bench|consultant|evaluation|substrate|expert system|tooling)\b",
            a,
        ),
        "names": (
            _has(r"\bproject[ -]?phoenix\b", a)
            and _has(r"\bbulkhead\b", a)
            and (_has(r"\bbottlenecks\.md\b", a) or _has(r"\bbn\b", a))
            and _has(r"\b(operator-control-plane|operator)\b", a)
        ),
        "authority": _has(
            r"\b(substrate|database|schema|solver|file|grounded|not (an? )?llm|not the (model|runtime|source))\b",
            a,
        ),
        "open_now": _has(
            r"\b(labwired|grafana|proximity|shm_imu|tempo|observability|hil)\b",
            a,
        ),
        "read_first": (
            _has(r"\bagents\.md\b", a)
            and (_has(r"\bbottlenecks\.md\b", a) or _has(r"\bbn\b", a))
            and _has(r"\b(claude\.md|onboarding\.md)\b", a)
        ),
    }
    # Order is asked in the prompt but not auto-graded: BN/BOTTLENECKS
    # correctly appears in facet 2, so a whole-answer "AGENTS.md first"
    # check false-fails a short sourced answer.

    return {
        "facets": {k: ("sourced" if v else "missing") for k, v in facets.items()},
        "n_sourced": sum(facets.values()),
        "passed": all(facets.values()),
    }


@dataclass
class Length:
    wall_clock_s: float
    answer_chars: int
    answer_words: int
    n_calls: int
    completion_tokens: int
    prompt_tokens: int
    n_rounds: int
    files_read: list[str] = field(default_factory=list)


def measure(stdout: str, wall_clock_s: float, trajectory: dict) -> Length:
    answer = extract_answer(stdout)
    files = []
    for c in trajectory.get("tool_calls") or []:
        if c.get("tool") == "read_file" and c.get("path"):
            files.append(c["path"])
    return Length(
        wall_clock_s=round(wall_clock_s, 1),
        answer_chars=len(answer),
        answer_words=len(answer.split()),
        n_calls=int(trajectory.get("n_calls") or 0),
        completion_tokens=int(trajectory.get("completion_tokens") or 0),
        prompt_tokens=sum(int(m) for m in re.findall(r"prompt=(\d+)", stdout)),
        n_rounds=len(re.findall(r"\[tokens\] prompt=", stdout)),
        files_read=files,
    )


PROMPT = """This workspace holds the governing docs of project-phoenix as they are on disk today. Answer from files you open here, not from memory of other trees.

Cover these five, briefly:
1. What this repo is for (one or two sentences).
2. The names that must not be collapsed: the folder, the public line, the open-work board, the enforcement CLI — and where each lives.
3. Where authoritative answers are supposed to come from.
4. What is open *right now* (not a greatest-hits list).
5. The first three files a new agent should read, in order.

If a file you need is missing, say so. Do not invent a current task. Prefer short and sourced over long and complete-sounding."""
