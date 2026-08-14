#!/usr/bin/env python3
"""
BT floor — HARD probes (cross-document assembly).

Why this exists
---------------
The five original probes (p1..p5) saturated: gemma4:26b and gemma4:31b both
score 5/5 on both funnels, so the battery has no resolving power above ~12B.
Every one of those probes is answerable by locating a single passage.

These probes are built to a different rule:

    NO SINGLE DOCUMENT IN THE FUNNEL CONTAINS THE ANSWER.

Each answer must be assembled from two or more sources, and the conclusion
itself is stated nowhere in the corpus. A model that greps well but does not
compose will fail these while still passing p1..p5.

A probe was rejected during authoring for violating that rule: "which machines
have divergent ledgers and why is merging unsafe" reads like assembly but
BOTTLENECKS.md's Front H entry states the spec, the gitignore, both machine
names and the sequential-ID reason in one bullet. Retrieval in an assembly
costume. If you add a probe here, verify the negative first.

Grading: the confabulation check
--------------------------------
Keyword grading cannot tell a correct answer from a correct answer wearing
invented supporting detail. Observed 2026-08-14: gemma4:26b answered the
Hyperlambda question by naming `magic_bridge/hyperlambda_bridge.py` and the
term "Hansen-lite". Both real. But the keyword grader would have scored an
invented `magic_bridge/hyperlambda_runtime.py` and "Magic-lite adapter"
identically, because the graded keywords sit in the *conclusion*, not the
detail. Elaboration is exactly where hallucination hides.

So every probe is graded on two axes:

  1. `requires`  — did the answer reach the conclusion (concept groups, any-of)
  2. citations   — does every repo-local path it cites actually exist

Axis 2 is the new one and it is fail-closed. Under funnel conditions the model
has documents and no tools, so it cannot have discovered a path that is not in
the corpus: any unresolvable repo-local path is fabricated by construction.
"""

import json
import re
import sys
from pathlib import Path

REPO_ROOTS = [
    Path("/home/blueaz/Python/project-phoenix"),
    Path("/home/blueaz/operator-control-plane"),
]

# ---------------------------------------------------------------- probes

# `sources` is documentation of the intended assembly, not used in grading.
# It is the authoring record that the single-document negative was checked.
HARD_PROBES = [
    {
        "id": "h1_hyperlambda_impl",
        "question": (
            "Does a Hyperlambda runtime execute anywhere in this system? "
            "If not, what actually produces the Hyperlambda-style dashboard "
            "output, and what is it written in?"
        ),
        "sources": [
            "project-phoenix/AGENTS.md — lineage note: no runtime exists",
            "project-phoenix/BOTTLENECKS.md:106 — magic_bridge/report.html (Hansen-lite)",
        ],
        "why_assembly": (
            "AGENTS.md establishes the absence; BOTTLENECKS.md names the artifact "
            "that stands in for it. Neither says 'the dashboard is a Python shim "
            "imitating Hyperlambda' — that is the composed conclusion."
        ),
        "requires": [
            ["no runtime", "not a runtime", "does not execute", "no hyperlambda runtime",
             "never executed", "no functional", "not functional", "illustrative"],
            ["magic_bridge", "magic bridge"],
            ["report.html", "dashboard", "command center"],
        ],
        # Naming the language is the discriminator: it separates a model that
        # read the lineage note from one that also worked out what replaced it.
        "bonus": [["python", "shim", "hansen-lite", "hansen lite"]],
    },
    {
        "id": "h2_crystal_status_today",
        "question": (
            "Can an agent-crystallize crystal set a verification status in the "
            "ledger today? Say what governs the answer, and whether the mechanism "
            "that would permit it exists yet."
        ),
        "sources": [
            "operator-control-plane/AGENTS.md:10-14 — crystals are untrusted "
            "narration at the lower boundary, never trusted status; canonical "
            "taxonomy is BULKHEAD_TAU_BOUNDARIES.md",
            "operator-control-plane/AGENTS.md:90 — CRYSTAL_LEDGER_INTEROP_SPEC.md "
            "is a draft proposal, nothing implemented",
            "operator-control-plane/CRYSTAL_LEDGER_INTEROP_SPEC.md — the spec itself",
        ],
        "why_assembly": (
            "The trust rule and the implementation status are ~80 lines apart and "
            "neither mentions the other. A model that finds only the trust rule "
            "answers 'no, by policy'; one that finds only the draft status answers "
            "'not yet, unimplemented'. The complete answer is that BOTH hold, and "
            "that they are independent reasons."
        ),
        "requires": [
            ["no", "cannot", "can not", "never", "not able", "may not"],
            ["untrusted", "never trusted status", "not a boundary", "narration",
             "lower boundary"],
            ["draft", "proposal", "not implemented", "nothing.*implemented",
             "unimplemented", "does not exist yet"],
        ],
        "bonus": [["bulkhead_tau_boundaries", "bulkhead tau boundaries", "canonical"]],
    },
    {
        "id": "h3_cross_machine_verify",
        "question": (
            "A claim is registered in the ledger on the z13 laptop. Can a session "
            "running on the desktop verify that claim? Explain what makes it "
            "possible or impossible."
        ),
        "sources": [
            "operator-control-plane/AGENTS.md:63 — .operator/ is gitignored and "
            "per-machine; a harness registered on z13 does not exist on desktop",
            "operator-control-plane/AGENTS.md:160 — only a registered verifier OS "
            "UID distinct from the claim author is uid_isolated",
            "project-phoenix/BOTTLENECKS.md:131 — Front H: two ledgers exist, git "
            "never reconciles them, nothing detects the divergence",
        ],
        "why_assembly": (
            "Strongest of the three. The verification-identity rule lives in one "
            "repo, the observed two-ledger divergence in another, and the "
            "conclusion -- that cross-machine verification is not merely "
            "unperformed but structurally impossible today -- appears in neither. "
            "A model can quote both halves and still not join them."
        ),
        "requires": [
            ["no", "cannot", "can not", "not possible", "impossible", "unable"],
            ["gitignored", "per-machine", "per machine", "not shared", "separate ledger",
             "two ledgers", "does not exist on", "never reconcile"],
        ],
        "bonus": [["uid", "uid_isolated", "distinct", "verifier"],
                  ["front h", "divergence", "660", "asymmetry"]],
    },
]

# ------------------------------------------------------------- grading

# Repo-local path: has a directory separator or a known source extension.
PATH_RE = re.compile(
    r"\b((?:[\w.-]+/)*[\w.-]+\.(?:py|md|sh|yaml|yml|json|html|hl))\b"
)

# Cited bare filenames that legitimately exist in several places, plus corpus
# docs referenced by name. Not treated as ungrounded when unresolvable alone.
CITATION_ALLOWLIST = {
    "AGENTS.md", "README.md", "BOTTLENECKS.md", "MEMORY.md", "CLAUDE.md",
}


_BASENAME_INDEX = None
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv"}


def _basename_index():
    """Every filename present under the repo roots, built once.

    A bare filename is grounded if some file by that name exists anywhere in
    the corpus. Without this, a model citing "report.html" -- correct, and the
    exact form BOTTLENECKS.md uses in prose -- was scored as fabricated
    because only <root>/report.html was tried, never magic_bridge/report.html.
    That false positive fired on a fully correct gemma4:31b answer.
    """
    global _BASENAME_INDEX
    if _BASENAME_INDEX is None:
        idx = set()
        for root in REPO_ROOTS:
            if not root.exists():
                continue
            for p in root.rglob("*"):
                if any(part in _SKIP_DIRS for part in p.parts):
                    continue
                if p.is_file():
                    idx.add(p.name)
        _BASENAME_INDEX = idx
    return _BASENAME_INDEX


def resolve_citation(path_str):
    """True if the cited path is grounded in the corpus.

    Grounding is corpus-relative, not strictly filesystem-relative: a model
    reading documents may legitimately name anything those documents name.
    Three ways to resolve, cheapest first.
    """
    if path_str in CITATION_ALLOWLIST:
        return True

    p = Path(path_str)
    if p.is_absolute():
        return p.exists()

    for root in REPO_ROOTS:
        if (root / p).exists():
            return True
        # Tolerate a repo-name prefix: "project-phoenix/AGENTS.md"
        parts = p.parts
        if len(parts) > 1 and (root / Path(*parts[1:])).exists():
            return True

    # Bare filename cited without its directory.
    if "/" not in path_str and path_str in _basename_index():
        return True

    return False


def check_citations(answer):
    """Every repo-local path cited must resolve. Fail-closed."""
    cited = sorted(set(PATH_RE.findall(answer)))
    ungrounded = [c for c in cited if not resolve_citation(c)]
    return {
        "cited": cited,
        "ungrounded": ungrounded,
        "ok": not ungrounded,
    }


def _group_hit(group, low):
    for term in group:
        if re.search(term, low) if any(ch in term for ch in ".*") else term in low:
            return term
    return None


def grade(probe, answer):
    low = answer.lower()

    missing, hit = [], []
    for group in probe["requires"]:
        m = _group_hit(group, low)
        (hit if m else missing).append(m or group[0])

    bonus_hit = []
    for group in probe.get("bonus", []):
        m = _group_hit(group, low)
        if m:
            bonus_hit.append(m)

    cites = check_citations(answer)

    # Fail-closed on fabricated citations even when the conclusion is right.
    if not cites["ok"]:
        verdict = "FAIL_UNGROUNDED"
    elif missing:
        verdict = "FAIL"
    else:
        verdict = "PASS"

    return {
        "probe": probe["id"],
        "verdict": verdict,
        "required_hit": hit,
        "required_missing": missing,
        "bonus_hit": bonus_hit,
        "citations": cites,
        "empty_output": len(answer.strip()) == 0,
    }


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nusage: hard_probes.py <results.json>   # grade captured answers")
        print("       hard_probes.py --list            # print probes + answer keys")
        return 0

    if sys.argv[1] == "--list":
        for p in HARD_PROBES:
            print(f"\n=== {p['id']} ===")
            print(f"Q: {p['question']}")
            print(f"Assembly: {p['why_assembly']}")
            print("Sources:")
            for s in p["sources"]:
                print(f"  - {s}")
        return 0

    data = json.loads(Path(sys.argv[1]).read_text())
    probes = {p["id"]: p for p in HARD_PROBES}
    results = []
    for key, rec in data.get("probes", {}).items():
        if key not in probes:
            continue
        r = grade(probes[key], rec.get("output", ""))
        results.append(r)
        flag = ""
        if r["citations"]["ungrounded"]:
            flag = f"  !! fabricated: {', '.join(r['citations']['ungrounded'])}"
        print(f"[{key}] {r['verdict']}"
              f"  missing={r['required_missing'] or '-'}"
              f"  bonus={len(r['bonus_hit'])}{flag}")
    passed = sum(1 for r in results if r["verdict"] == "PASS")
    print(f"\n{passed}/{len(results)} PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
