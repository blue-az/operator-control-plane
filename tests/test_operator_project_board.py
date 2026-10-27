"""Focused static-board tests; all ledger mutations use temporary directories."""
from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("operator_project_board", ROOT / "scripts/operator_project_board.py")
board = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(board)

PBC = """## Future Feature Candidates
```pbc:grounding
future_features:
  - id: POE-FUT-006
    name: Target editor
  - id: POE-FUT-017
    name: Life boat
  - id: POE-FUT-099
    name: Unknown <candidate>
```
## Candidate Reconciliation
| ID | Reconciled status | Basis / remaining acceptance |
|---|---|---|
| POE-FUT-001–002 | Implemented; not independently accepted | Draft commands only. |
| POE-FUT-006 | Implemented; not independently accepted | `/op:targets` exists. |
| POE-FUT-010 | Implemented; local task verified | Local status is not independent acceptance. |
| POE-FUT-013 | Closed as guidance-only | Do not add a command. |
| POE-FUT-017 | Minimal slice implemented; supervisor launch not implemented | Acceptance pending. |
## Unrelated
| POE-FUT-099 | Implemented | Must not be consumed. |
"""


class BoardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pbc = self.root / "owners-manual/pbc/appendix-pi-operator-extension.pbc.md"
        self.pbc.parent.mkdir(parents=True)
        self.pbc.write_text(PBC)

    def test_inventory_retains_acceptance_and_partial_scope(self):
        data = board.collect(self.root, board.PREFIX_DEFAULT)
        features = {f["id"]: f for f in data["features"]}
        self.assertEqual(len(features), 6)
        self.assertEqual(features["POE-FUT-006"]["status"], "Implemented; not independently accepted")
        self.assertIn("supervisor launch not implemented", features["POE-FUT-017"]["status"])
        self.assertIn("unknown", features["POE-FUT-099"]["status"])
        self.assertIn("POE-FUT-001–002", features)
        page = board.render(data)
        self.assertNotIn("Recent future features", page)
        self.assertIn("Historical IDs are not an active-work queue", page)
        self.assertIn("Closed as guidance-only", page)
        self.assertIn("Implemented; local task verified", page)
        self.assertIn("Unknown &lt;candidate&gt;", page)
        self.assertIn("aggregate counts do not establish independent acceptance", page)

    def test_missing_reconciliation_is_unknown_not_unimplemented(self):
        self.pbc.write_text(PBC.split("## Candidate Reconciliation")[0])
        data = board.collect(self.root, board.PREFIX_DEFAULT)
        self.assertEqual(len(data["features"]), 3)
        for feature in data["features"]:
            self.assertIn("implementation/acceptance unknown", feature["status"])

    def test_missing_pbc_and_other_prefix(self):
        self.pbc.unlink()
        self.assertEqual(board.collect(self.root, board.PREFIX_DEFAULT)["features"], [])
        self.pbc.write_text(PBC)
        self.assertEqual(board.collect(self.root, "other-project")["features"], [])

    def test_real_inventory_is_complete_and_status_bearing(self):
        pbc = ROOT / "owners-manual/pbc/appendix-pi-operator-extension.pbc.md"
        _, candidates = board.parse_pbc_lists(pbc)
        features = {f["id"]: f for f in board.parse_feature_inventory(pbc, candidates)}
        self.assertGreater(len(features), 10)
        for fid in ("006", "008", "009", "010", "015"):
            self.assertTrue(features[f"POE-FUT-{fid}"]["status"].startswith("Implemented"))
        self.assertIn("not independently accepted", features["POE-FUT-015"]["status"])

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True, text=True).stdout.strip()

    def test_git_clean_dirty_tracked_untracked_and_staged(self):
        self.git("init")
        self.git("add", ".")
        self.git("-c", "user.name=Board Test", "-c", "user.email=board@example.invalid", "-c", "commit.gpgsign=false", "commit", "-m", "fixture")
        commit = self.git("rev-parse", "HEAD")
        self.assertEqual(board.source_provenance(self.root), {"commit": commit, "dirty": False})
        self.pbc.write_text(PBC + "\nchanged\n")
        self.assertEqual(board.source_provenance(self.root), {"commit": commit, "dirty": True})
        self.git("add", ".")
        self.assertTrue(board.source_provenance(self.root)["dirty"])
        self.git("reset", "--hard", "HEAD")
        (self.root / "untracked.txt").write_text("new")
        self.assertTrue(board.source_provenance(self.root)["dirty"])

    def test_git_unavailable_and_status_failure_are_unknown(self):
        self.assertEqual(board.source_provenance(self.root), {"commit": None, "dirty": None})
        with patch.object(board.subprocess, "run", side_effect=FileNotFoundError):
            self.assertIsNone(board.source_provenance(self.root)["dirty"])
        with patch.object(board.subprocess, "run", side_effect=[
            subprocess.CompletedProcess([], 0, "a" * 40 + "\n"),
            subprocess.TimeoutExpired("git", 10),
        ]):
            self.assertEqual(board.source_provenance(self.root), {"commit": "a" * 40, "dirty": None})

    def test_all_views_expose_provenance(self):
        source = {"commit": "b" * 40, "dirty": True}
        with patch.object(board, "source_provenance", return_value=source):
            pages = [
                board.render(board.collect(self.root, board.PREFIX_DEFAULT)),
                board.render_issues(board.collect_issues(self.root, board.PREFIX_DEFAULT)),
                board.render_resolution(board.collect_resolution(self.root, "missing")),
            ]
            graph = self.root / "graph.html"
            board.write_graph_html(self.root, board.PREFIX_DEFAULT, graph)
            pages.append(graph.read_text())
            vault = self.root / "vault"
            board.write_obsidian(self.root, board.PREFIX_DEFAULT, vault)
            pages.extend(p.read_text() for p in vault.glob("*.md"))
        for page in pages:
            self.assertIn("b" * 40, page)
            self.assertIn("worktree: dirty", page)
            self.assertIn("not an immutable commit", page)
            self.assertIn("separate local snapshot", page)


if __name__ == "__main__":
    unittest.main()
