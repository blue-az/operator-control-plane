"""Tool-call extraction in opr (regression: the greedy-span defect).

The original extractor regexed from the first '{' to the last '}'. A response
carrying two objects -- an edit plus a self-verification read, which several
local models emit routinely -- produced a span covering both, which is not
valid JSON. Extraction returned None, the caller handed the raw text back as a
final answer, and a correct tool call silently became prose.

The payloads below are verbatim from retained eval traces of the cells that
failed this way on 2026-08-12.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_loader(
    "opr_mod", importlib.machinery.SourceFileLoader("opr_mod", str(REPO_ROOT / "opr"))
)
opr = importlib.util.module_from_spec(_spec)
sys.modules["opr_mod"] = opr
_spec.loader.exec_module(opr)

extract = opr.extract_json_tool_call


PATCH = {
    "tool": "patch_file",
    "path": "config/settings.ini",
    "target_content": "debug = false",
    "replacement_content": "debug = true",
}


class ToolExtractionTest(unittest.TestCase):
    def test_single_bare_object(self) -> None:
        """The case that always worked; must keep working."""
        self.assertEqual(extract(opr.json.dumps(PATCH)), PATCH)

    def test_two_bare_objects_returns_the_first(self) -> None:
        """gemma3:27b, config-value-change t1/t3 -- verbatim shape."""
        text = (
            '{"tool": "patch_file", "path": "config/settings.ini", '
            '"target_content": "debug = false", "replacement_content": "debug = true"}\n'
            '{"tool": "grep_search", "pattern": "debug = true", "path": "config/settings.ini"}'
        )
        self.assertEqual(extract(text), PATCH)

    def test_two_fenced_objects_returns_the_first(self) -> None:
        """qwen2.5-coder:14b, config-value-change t1/t2 -- verbatim shape."""
        text = (
            "```json\n"
            '{\n  "tool": "patch_file",\n  "path": "config/settings.ini",\n'
            '  "target_content": "debug = false",\n'
            '  "replacement_content": "debug = true"\n}\n'
            "```\n\n"
            "```json\n"
            '{\n  "tool": "grep_search",\n  "pattern": "^debug = true$",\n'
            '  "path": "config/settings.ini"\n}\n'
            "```"
        )
        self.assertEqual(extract(text), PATCH)

    def test_single_fenced_object(self) -> None:
        text = "```json\n" + opr.json.dumps(PATCH) + "\n```"
        self.assertEqual(extract(text), PATCH)

    def test_prose_before_and_after(self) -> None:
        text = (
            "I'll update the config now.\n"
            + opr.json.dumps(PATCH)
            + "\nThat should do it."
        )
        self.assertEqual(extract(text), PATCH)

    def test_prose_brace_is_skipped(self) -> None:
        """A brace in prose must not abandon the rest of the response."""
        text = "Use the {patch_file} tool like so:\n" + opr.json.dumps(PATCH)
        self.assertEqual(extract(text), PATCH)

    def test_leading_non_tool_object_is_skipped(self) -> None:
        """A valid object without a 'tool' key is not a call; keep scanning."""
        text = '{"thinking": "I should patch the file"}\n' + opr.json.dumps(PATCH)
        self.assertEqual(extract(text), PATCH)

    def test_plain_prose_yields_nothing(self) -> None:
        self.assertIsNone(extract("The file already contains debug = true."))

    def test_truncated_object_yields_nothing(self) -> None:
        self.assertIsNone(extract('{"tool": "patch_file", "path": "config/set'))

    def test_looks_like_tool_call_flags_undispatchable_output(self) -> None:
        """Truncated tool-shaped output must be distinguishable from prose."""
        truncated = '{"tool": "patch_file", "path": "config/set'
        self.assertIsNone(extract(truncated))
        self.assertTrue(opr.looks_like_tool_call(truncated))
        self.assertFalse(opr.looks_like_tool_call("Just an ordinary answer."))


if __name__ == "__main__":
    unittest.main()
