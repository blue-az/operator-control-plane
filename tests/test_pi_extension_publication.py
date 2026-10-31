from __future__ import annotations

import hashlib
import os
import unittest
from pathlib import Path

from scripts.build_pi_extension_publication import (
    ARCHIVE_NAME,
    EXPECTED_PBC_SHA256,
    INVENTORY_NAME,
    MAIN_NAME,
    OUTPUT_DIR,
    parse_inventory,
    render_inventory_page,
    render_pages,
    replace_once,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PUBLISHER_ROOT = Path(os.environ.get("PUBLIC_PROTO_ROOT", Path.home() / "Public/Proto"))
EXPECTED_OUTPUT_HASHES = {
    MAIN_NAME: "cec2b759c1ef49bd041202f1487ce856152a75e55fb633a87069cd9b8085768e",
    ARCHIVE_NAME: "ab99b220529d322bd8afb5d4887432f37847101023aaf818a5a6db474ed78990",
    INVENTORY_NAME: "f081c6f97d283a58af91545c97ea259f6335e8a95228af99918415fafb47b08d",
}


class TestPiExtensionPublication(unittest.TestCase):
    def test_replace_once_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            replace_once("nothing here", "missing", "replacement", "fixture")
        with self.assertRaises(ValueError):
            replace_once("same same", "same", "replacement", "fixture")

    def test_inventory_renderer_escapes_source_text(self) -> None:
        sample_rows = [
            {
                "id": f"POE-FUT-{index:03d}",
                "status": "Not implemented",
                "basis": "<script>alert('x')</script>",
            }
            for index in range(1, 18)
        ]
        page = render_inventory_page(b"pinned source", sample_rows)
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn("<script", page.lower())
        self.assertIn("POE-FUT-017", page)
        self.assertIn("17 rows", page)

    def test_pinned_pbc_digest_and_inventory_shape(self) -> None:
        pbc, rows = parse_inventory(PROJECT_ROOT)
        self.assertEqual(hashlib.sha256(pbc).hexdigest(), EXPECTED_PBC_SHA256)
        self.assertEqual(len(rows), 17)
        self.assertEqual(rows[0]["id"], "POE-FUT-001–002")
        self.assertEqual(rows[-1]["id"], "POE-FUT-018")
        self.assertIn("Not implemented", {row.get("status") for row in rows})

    @unittest.skipUnless(PUBLISHER_ROOT.is_dir(), "Public/Proto checkout not available")
    def test_generated_bytes_match_published_pages(self) -> None:
        outputs = render_pages(PROJECT_ROOT, PUBLISHER_ROOT)
        self.assertEqual(set(outputs), {f"{OUTPUT_DIR}/{name}" for name in EXPECTED_OUTPUT_HASHES})
        for name, expected_hash in EXPECTED_OUTPUT_HASHES.items():
            relative_path = f"{OUTPUT_DIR}/{name}"
            generated = outputs[relative_path]
            current = (PUBLISHER_ROOT / relative_path).read_bytes()
            self.assertEqual(hashlib.sha256(generated).hexdigest(), expected_hash)
            self.assertEqual(generated, current, name)


if __name__ == "__main__":
    unittest.main()
