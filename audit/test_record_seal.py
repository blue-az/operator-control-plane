"""Tests for record_seal (evidence-chain audit). python3 -m unittest test_record_seal -v"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import record_seal as rs  # noqa: E402


def make_run(d: Path, manifest: dict, files: list[str]) -> Path:
    run = d / ("r" + manifest.get("out_dir", "x").replace("/", "_")[-6:])
    run.mkdir()
    manifest = dict(manifest, out_dir=str(run))
    run.joinpath("manifest.json").write_text(json.dumps(manifest))
    for f in files:
        p = run / f
        p.parent.mkdir(parents=True, exist_ok=True)
        if f.endswith(".json"):
            p.write_text(json.dumps(manifest.get("_payloads", {}).get(f, {})))
        else:
            p.write_text("evidence")
    manifest.pop("_payloads", None)
    run.joinpath("manifest.json").write_text(json.dumps(manifest))
    return run


BASE_ROWS = [
    {"task": "t1", "label": "m_r1", "base_label": "m", "repeat": 1,
     "stdout_path": "t1__m_r1.out.md", "returncode": 0,
     "num_ctx": 16384, "request_model": "tag-m"},
    {"task": "t1", "label": "m_r2", "base_label": "m", "repeat": 2,
     "stdout_path": "t1__m_r2.out.md", "returncode": 0,
     "num_ctx": 16384, "request_model": "tag-m"},
]
BASE_FILES = ["t1__m_r1.out.md", "t1__m_r2.out.md",
              "t1__m_r1.json", "t1__m_r2.json"]
BASE_MANIFEST = {"repeats": 2,
                 "model_configs": {"m": {"tag": "tag-m"}},
                 "results": BASE_ROWS}


class TestSealedRun(unittest.TestCase):
    def test_clean_dir_seals(self):
        with tempfile.TemporaryDirectory() as d:
            run = make_run(Path(d), BASE_MANIFEST, BASE_FILES)
            a = rs.audit_run(run)
            self.assertTrue(a.sealed, a.violations)
            self.assertIn("V-RC-ERR", a.active_checks)
            self.assertIn("V-REPEATS", a.active_checks)


class TestViolationClasses(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.d = Path(self._t.name)

    def tearDown(self):
        self._t.cleanup()

    def _audit(self, manifest, files):
        return rs.audit_run(make_run(self.d, manifest, files))

    def _fails(self, a, code):
        self.assertFalse(a.sealed, "expected a failure")
        self.assertTrue(any(v.startswith(code) for v in a.violations),
                        f"{code} not in {a.violations}")

    def test_missing_stdout(self):
        a = self._audit(BASE_MANIFEST, ["t1__m_r1.out.md"])  # missing r2
        self._fails(a, "V-OUT")

    def test_orphan_evidence(self):
        a = self._audit(BASE_MANIFEST, BASE_FILES + ["t1__m_r3.out.md"])
        self._fails(a, "V-ORPHAN")

    def test_duplicate_rows(self):
        m = dict(BASE_MANIFEST)
        m["results"] = BASE_ROWS + [dict(BASE_ROWS[0])]
        a = self._audit(m, BASE_FILES)
        self._fails(a, "V-DUP")

    def test_repeat_gap(self):
        m = dict(BASE_MANIFEST, repeats=3)  # declared 3, only 2 rows
        a = self._audit(m, BASE_FILES)
        self._fails(a, "V-REPEATS")

    def test_ctx_mix(self):
        rows = [dict(r) for r in BASE_ROWS]
        rows[1]["num_ctx"] = 8192
        a = self._audit(dict(BASE_MANIFEST, results=rows), BASE_FILES)
        self._fails(a, "V-CTX")

    def test_tag_drift(self):
        rows = [dict(r) for r in BASE_ROWS]
        rows[0]["request_model"] = "other-tag"
        a = self._audit(dict(BASE_MANIFEST, results=rows), BASE_FILES)
        self._fails(a, "V-TAG")

    def test_error_row_with_completion_payload(self):
        rows = [dict(r) for r in BASE_ROWS]
        rows[1]["returncode"] = 500
        payloads = {"t1__m_r2.json": {"raw_response": "fabricated completion",
                                      "returncode": 500}}
        manifest = dict(BASE_MANIFEST, results=rows)
        manifest["_payloads"] = payloads
        a = self._audit(manifest, BASE_FILES)
        self._fails(a, "V-RC-ERR")

    def test_error_row_without_payload_is_ok(self):
        """500 row with NO payload file is a recordless error — the honest
        shape (this is how the qwen36 column must look). Must still seal."""
        rows = [dict(BASE_ROWS[0]),
                {"task": "t1", "label": "m_r2", "base_label": "m", "repeat": 2,
                 "stdout_path": "t1__m_r2.out.md", "returncode": 500}]
        files = ["t1__m_r1.out.md", "t1__m_r2.out.md", "t1__m_r1.json"]
        a = self._audit(dict(BASE_MANIFEST, results=rows), files)
        self.assertTrue(a.sealed, a.violations)

    def test_schema_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            run = Path(d) / "bad"
            run.mkdir()
            run.joinpath("manifest.json").write_text('{"results": []}')
            with self.assertRaises(SystemExit):
                rs.audit_run(run)


class TestLivePinnedRun(unittest.TestCase):
    """Location-coupled: the real pinned run must seal clean. If it fails,
    that is a genuine record finding — file it, don't fix the audit."""

    PINNED = Path.home() / "operator-control-plane/evals/ppr_agent_benchmark/" \
               "runs/pinned-20260908-200455"

    def test_pinned_seals(self):
        if not self.PINNED.exists():
            self.skipTest("pinned run not present")
        a = rs.audit_run(self.PINNED)
        self.assertTrue(a.sealed, a.violations)
        self.assertIn("V-RC-ERR", a.active_checks)


if __name__ == "__main__":
    unittest.main(verbosity=2)
