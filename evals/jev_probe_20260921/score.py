"""Offline re-scoring of the Jev probe results; makes no network calls.

Operator ground-truth rankings come from ``operator_rankings.yaml``, which cites each
ranking's source. R4 is additionally derived from the in-repo USER_RANKING.txt + KEY.txt
of its eval dir and cross-checked; a mismatch raises rather than scoring against a
stale literal. R3's source is external to this repo (see that file) and is cited only.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

HERE = Path(__file__).parent
EVALS = HERE.parent
RANKINGS = yaml.safe_load((HERE / "operator_rankings.yaml").read_text())
TRUTH = {rnd: list(spec["ranking"]) for rnd, spec in RANKINGS.items()}  # operator ranking, best first


def derived_ranking(eval_dir: Path) -> list[str] | None:
    """Rebuild an operator ranking from an eval dir's own USER_RANKING.txt and KEY.txt."""
    ranking_file, key_file = eval_dir / "USER_RANKING.txt", eval_dir / "KEY.txt"
    if not (ranking_file.is_file() and key_file.is_file()):
        return None
    letters = [part.strip() for part in ranking_file.read_text().split(":", 1)[1].split(">")]
    key = dict(line.strip().split(" = ") for line in key_file.read_text().splitlines() if " = " in line)
    return [key[letter] for letter in letters]


def check_provenance() -> None:
    for rnd, spec in RANKINGS.items():
        derived = derived_ranking(Path(spec["eval_dir"]) if Path(spec["eval_dir"]).is_absolute()
                                  else EVALS.parent / spec["eval_dir"])
        if derived is None:
            print(f"truth {rnd} = {TRUTH[rnd]} (cited source, not derivable here: {spec['source'].split(':')[0]})")
            continue
        if derived != TRUTH[rnd]:
            raise SystemExit(f"provenance mismatch for {rnd}: file says {derived}, operator_rankings.yaml says {TRUTH[rnd]}")
        print(f"truth {rnd} = {TRUTH[rnd]} (derived from {spec['eval_dir']} and matches)")


def essay() -> None:
    rows = json.loads((HERE / "essay_rank_results.json").read_text())
    for rnd in TRUTH:
        for setup in ("orig", "shuffled"):
            sel = [r for r in rows if r["round"] == rnd and r["setup"] == setup]
            mean = {m: sum(r["scores"][m] for r in sel) / len(sel) for m in TRUTH[rnd]}
            order = sorted(mean, key=mean.get, reverse=True)
            same_both = sum(r["best"] == r["worst"] for r in sel)
            print(f"essay {rnd} {setup:8} jev={order} operator={TRUTH[rnd]} "
                  f"match={order == TRUTH[rnd]} best==worst in {same_both}/{len(sel)}")


def claims() -> None:
    rows = json.loads((HERE / "claim_check_results.json").read_text())
    graded = [r for r in rows if r["label"] is not None]
    right = sum((min(r["p"]) >= 0.5) == r["label"] and (max(r["p"]) >= 0.5) == r["label"] for r in graded)
    spread = max(max(r["p"]) - min(r["p"]) for r in rows)
    print(f"claims correct at 0.5 (both reps): {right}/{len(graded)}; max rep spread {spread:.2f}")
    for r in graded:
        if (sum(r["p"]) / 2 >= 0.5) != r["label"] or 0.4 <= sum(r["p"]) / 2 <= 0.6:
            print(f"  flag {r['id']} label={r['label']} p={r['p']} :: {r['claim']}")
    for r in rows:
        if r["label"] is None:
            print(f"  borderline {r['id']} p={r['p']} :: {r['claim']}")


if __name__ == "__main__":
    check_provenance()
    essay()
    claims()
