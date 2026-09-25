"""Triage a reported failure before it is allowed to count against a model.

Every scorer in this tree has, at least once, reported a model failure that was
its own artifact:

  * Fusion L3 v2 (2026-09-22): 17 apparent failures, all deterministic-grader
    false negatives -- negated one-to-one language, equivalent negative-state
    words, explicitly headed sections. Reconciled to 18/18 per model.
  * Staged frontier control (2026-09-23): the scope check compared file CONTENTS
    against a hash manifest, so an untouched fixture reported its test files
    "modified out of scope". Two of three tasks were unpassable by anyone and
    every staged run was capped at 6/18.
  * PAI (2026-09-24, first run ever): `scope` failed all three probes with
    `directives: []` and `refusal_hits: []` -- every model refused the planted
    clinical question correctly, in its own words, and none happened to use one
    of four required literal phrases. `anchor` failed PAI-001 for "missing"
    3576 and 92071191 while the brief contained 1892+1271+413 and
    48343280+29111911+14616000, which sum to exactly those values.

In all three the number was reported first and investigated afterwards, and in
two of three it was published or nearly published before anyone looked.

This module makes that investigation automatic and model-free. It does not
decide whether a model is good. It decides whether a reported failure has
earned the right to be called one.

Outcome vocabulary matches runner.py: a failure that cannot be trusted is
`unproven` -- evidence about the harness, not poolable as a model result.
"""
from __future__ import annotations

import itertools
import re
from collections.abc import Iterable, Sequence

__all__ = [
    "empty_evidence",
    "derivable_by_sum",
    "uniform_across_models",
    "triage_dimension",
    "triage_matrix",
]

# A dimension that fails while reporting nothing it objected to. The check ran,
# found no violation, and failed anyway -- which means its pass condition, not
# the model, decided the outcome.
def empty_evidence(dimension: dict, evidence_keys: Sequence[str] = ()) -> bool:
    """True when a failing dimension carries no positive evidence.

    `evidence_keys` names the fields that would hold a violation if one existed.
    When omitted, every list/tuple/set field is treated as evidence.
    """
    if dimension.get("pass", False):
        return False
    keys = evidence_keys or [
        k for k, v in dimension.items() if isinstance(v, (list, tuple, set))
    ]
    if not keys:
        return False
    return all(not dimension.get(k) for k in keys)


_NUM = re.compile(r"-?\d[\d,]*\.?\d*")


def _numbers(text: str) -> list[float]:
    out = []
    for raw in _NUM.findall(text or ""):
        try:
            out.append(float(raw.replace(",", "")))
        except ValueError:
            continue
    return out


def derivable_by_sum(required: str, text: str, max_terms: int = 4) -> list[float] | None:
    """Return the subset of numbers in *text* summing to *required*, if any.

    An exact-token check calls a value "missing" when the model reported its
    components instead of the aggregate. PAI-001 is the worked example: the
    brief gave three per-company figures and was failed for not printing their
    total. That is a presentation difference, not a wrong answer.
    """
    try:
        target = float(str(required).replace(",", ""))
    except (TypeError, ValueError):
        return None
    pool = [n for n in _numbers(text) if n != target]
    for size in range(2, max_terms + 1):
        for combo in itertools.combinations(pool, size):
            if abs(sum(combo) - target) < 1e-6:
                return list(combo)
    return None


def uniform_across_models(results: Iterable[dict], dimension: str) -> bool:
    """True when every model failed *dimension* on every cell.

    This is the operator's standing rule -- "when every model agrees, suspect
    the bench" -- enforced rather than remembered. Uniform total failure across
    independent models is far more likely to be one shared instrument than one
    shared incapacity.
    """
    rows = [r for r in results if dimension in r]
    if not rows:
        return False
    models = {r.get("model") for r in rows}
    if len(models) < 2:
        return False
    return all(not (r[dimension] or {}).get("pass", False) for r in rows)


def triage_dimension(
    dimension: dict,
    *,
    name: str,
    text: str = "",
    required: Sequence[str] = (),
    evidence_keys: Sequence[str] = (),
) -> dict:
    """Decide whether one failing dimension may be reported as a model failure.

    Returns {"outcome": "fail"|"unproven"|"pass", "reasons": [...], "detail": {...}}.
    `fail` means the failure survived triage and is evidence about the model.
    """
    if dimension.get("pass", False):
        return {"outcome": "pass", "reasons": [], "detail": {}}

    reasons: list[str] = []
    detail: dict = {}

    if empty_evidence(dimension, evidence_keys):
        reasons.append(
            f"{name} failed with no positive evidence: every evidence field is empty, "
            "so the pass condition decided this, not the model"
        )

    derivations = {}
    for token in required or dimension.get("missing", []) or []:
        combo = derivable_by_sum(token, text)
        if combo:
            derivations[str(token)] = combo
    if derivations:
        detail["derivable"] = derivations
        reasons.append(
            f"{name} reported tokens missing that are derivable from the text by "
            f"summation: {sorted(derivations)} -- components present, aggregate absent"
        )

    return {
        "outcome": "unproven" if reasons else "fail",
        "reasons": reasons,
        "detail": detail,
    }


def triage_matrix(results: Sequence[dict], dimensions: Sequence[str]) -> dict:
    """Cross-model check. Returns {dimension: {"uniform_failure": bool, "note": str}}.

    Run this before publishing any aggregate. A dimension flagged here should not
    be reported as a model result until a human has cleared it.
    """
    out = {}
    for dim in dimensions:
        uniform = uniform_across_models(results, dim)
        out[dim] = {
            "uniform_failure": uniform,
            "note": (
                f"{dim} failed for every model on every cell. Suspect the instrument "
                "before the roster; do not publish as a model result until cleared."
                if uniform else ""
            ),
        }
    return out
