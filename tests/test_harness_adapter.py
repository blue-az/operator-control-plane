#!/usr/bin/env python3
"""Unit tests for harness_adapter.py using fake CLI executables.

No real claude/agy/codex/grok binary is ever invoked here -- every test
points a HarnessProfile at a small fake script under a temp dir so the exit
states, prompt transport, and legacy-config paths can be exercised for free.
"""

from __future__ import annotations

import shutil
import stat
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import harness_adapter as ha  # noqa: E402


def write_fake_cli(directory: Path, name: str, body: str) -> str:
    path = directory / name
    path.write_text("#!/usr/bin/env python3\n" + textwrap.dedent(body))
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return str(path)


class TestHarnessAdapter(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.workspace = self.tmp / "workspace"
        self.workspace.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def make_profile(self, executable_path: str, **overrides) -> ha.HarnessProfile:
        base = dict(
            harness_id="claude",
            executable=executable_path,
            base_args=("-p", "--output-format", "json"),
            prompt_transport=ha.PromptTransport.STDIN,
            output_format="json",
            role_args={
                ha.Role.SUPERVISOR.value: ("--permission-mode", "plan"),
                ha.Role.JUDGE.value: ("--permission-mode", "plan"),
                ha.Role.IMPLEMENTER.value: ("--permission-mode", "acceptEdits"),
            },
        )
        base.update(overrides)
        return ha.HarnessProfile(**base)

    # ---- exit-state classification ----

    def test_success_json(self) -> None:
        exe = write_fake_cli(
            self.tmp,
            "fake-success",
            """
            import sys, json
            data = sys.stdin.read()
            print(json.dumps({"result": "ok", "echo": data, "session_id": "abc-123"}))
            """,
        )
        profile = self.make_profile(exe)
        ha.PROFILES["_test_claude"] = profile
        try:
            result = ha.invoke(
                "_test_claude", ha.Role.SUPERVISOR, "test-model-1", "hello", self.workspace
            )
        finally:
            del ha.PROFILES["_test_claude"]
        self.assertEqual(result.exit_state, ha.ExitState.SUCCESS)
        self.assertEqual(result.returncode, 0)
        self.assertIsNotNone(result.parsed_output)
        self.assertEqual(result.parsed_output["echo"], "hello")

    def test_nonzero_exit(self) -> None:
        exe = write_fake_cli(
            self.tmp,
            "fake-nonzero",
            """
            import sys
            sys.stderr.write("boom: internal error\\n")
            sys.exit(2)
            """,
        )
        profile = self.make_profile(exe)
        ha.PROFILES["_test_claude"] = profile
        try:
            result = ha.invoke("_test_claude", ha.Role.SUPERVISOR, "m", "hi", self.workspace)
        finally:
            del ha.PROFILES["_test_claude"]
        self.assertEqual(result.exit_state, ha.ExitState.NONZERO_EXIT)
        self.assertEqual(result.returncode, 2)
        self.assertIn("boom", result.stderr)
        # stderr must never be treated as apparent success.
        self.assertIsNone(result.parsed_output)

    def test_malformed_output(self) -> None:
        exe = write_fake_cli(
            self.tmp,
            "fake-malformed",
            """
            print("this is not json at all")
            """,
        )
        profile = self.make_profile(exe)
        ha.PROFILES["_test_claude"] = profile
        try:
            result = ha.invoke("_test_claude", ha.Role.SUPERVISOR, "m", "hi", self.workspace)
        finally:
            del ha.PROFILES["_test_claude"]
        self.assertEqual(result.exit_state, ha.ExitState.MALFORMED_OUTPUT)
        self.assertEqual(result.returncode, 0)

    def test_timeout(self) -> None:
        exe = write_fake_cli(
            self.tmp,
            "fake-slow",
            """
            import time
            time.sleep(5)
            print("{}")
            """,
        )
        profile = self.make_profile(exe)
        ha.PROFILES["_test_claude"] = profile
        try:
            result = ha.invoke(
                "_test_claude", ha.Role.SUPERVISOR, "m", "hi", self.workspace, timeout_seconds=1
            )
        finally:
            del ha.PROFILES["_test_claude"]
        self.assertEqual(result.exit_state, ha.ExitState.TIMEOUT)
        self.assertIsNone(result.returncode)

    def test_missing_executable(self) -> None:
        profile = self.make_profile(str(self.tmp / "does-not-exist-binary"))
        ha.PROFILES["_test_claude"] = profile
        try:
            result = ha.invoke("_test_claude", ha.Role.SUPERVISOR, "m", "hi", self.workspace)
        finally:
            del ha.PROFILES["_test_claude"]
        self.assertEqual(result.exit_state, ha.ExitState.MISSING_EXECUTABLE)
        self.assertIsNone(result.returncode)

    def test_quota_exhausted(self) -> None:
        exe = write_fake_cli(
            self.tmp,
            "fake-quota",
            """
            import sys
            sys.stderr.write("Error: rate limit exceeded, please retry after reset\\n")
            sys.exit(1)
            """,
        )
        profile = self.make_profile(exe)
        ha.PROFILES["_test_claude"] = profile
        try:
            result = ha.invoke("_test_claude", ha.Role.SUPERVISOR, "m", "hi", self.workspace)
        finally:
            del ha.PROFILES["_test_claude"]
        self.assertEqual(result.exit_state, ha.ExitState.QUOTA_EXHAUSTED)

    def test_quota_exhausted_takes_priority_over_nonzero_exit(self) -> None:
        # Quota markers are checked before the plain nonzero-exit classification,
        # since a quota-exhausted call and a "generic broken" call both usually
        # exit nonzero -- distinguishing them by state, not just exit code, is
        # the entire point of the quota_markers check.
        exe = write_fake_cli(
            self.tmp,
            "fake-quota-nonzero",
            """
            import sys
            print("partial output before failure")
            sys.stderr.write("429 Too Many Requests\\n")
            sys.exit(1)
            """,
        )
        profile = self.make_profile(exe)
        ha.PROFILES["_test_claude"] = profile
        try:
            result = ha.invoke("_test_claude", ha.Role.SUPERVISOR, "m", "hi", self.workspace)
        finally:
            del ha.PROFILES["_test_claude"]
        self.assertEqual(result.exit_state, ha.ExitState.QUOTA_EXHAUSTED)

    # ---- prompt transport ----

    def test_stdin_transport_carries_prompt_verbatim(self) -> None:
        exe = write_fake_cli(
            self.tmp,
            "fake-stdin-echo",
            """
            import sys, json
            print(json.dumps({"stdin_content": sys.stdin.read()}))
            """,
        )
        profile = self.make_profile(exe, prompt_transport=ha.PromptTransport.STDIN)
        ha.PROFILES["_test_claude"] = profile
        prompt = "multi\nline\nprompt with 'quotes' and \"double quotes\""
        try:
            result = ha.invoke("_test_claude", ha.Role.SUPERVISOR, "m", prompt, self.workspace)
        finally:
            del ha.PROFILES["_test_claude"]
        self.assertEqual(result.parsed_output["stdin_content"], prompt)

    def test_prompt_file_transport_writes_and_passes_real_path(self) -> None:
        exe = write_fake_cli(
            self.tmp,
            "fake-promptfile-echo",
            """
            import sys, json
            path = None
            for i, a in enumerate(sys.argv):
                if a == "--prompt-file":
                    path = sys.argv[i + 1]
            with open(path) as f:
                content = f.read()
            print(json.dumps({"file_content": content, "path_existed": True}))
            """,
        )
        profile = self.make_profile(
            exe,
            prompt_transport=ha.PromptTransport.PROMPT_FILE,
            prompt_file_flag="--prompt-file",
        )
        ha.PROFILES["_test_grok"] = profile
        prompt = "grok gets this via a file, not argv"
        try:
            result = ha.invoke("_test_grok", ha.Role.SUPERVISOR, "m", prompt, self.workspace)
        finally:
            del ha.PROFILES["_test_grok"]
        self.assertEqual(result.exit_state, ha.ExitState.SUCCESS)
        self.assertEqual(result.parsed_output["file_content"], prompt)

    def test_prompt_injection_shell_metacharacters_never_execute(self) -> None:
        # A prompt containing shell metacharacters must never be interpreted by
        # a shell -- it only ever reaches the child process as literal stdin
        # bytes or literal file content, never as an argv token or shell string.
        marker = self.tmp / "should-not-exist"
        exe = write_fake_cli(
            self.tmp,
            "fake-injection-check",
            """
            import sys, json
            data = sys.stdin.read()
            print(json.dumps({"received": data}))
            """,
        )
        profile = self.make_profile(exe)
        ha.PROFILES["_test_claude"] = profile
        malicious_prompt = f"; touch {marker} #"
        try:
            result = ha.invoke(
                "_test_claude", ha.Role.SUPERVISOR, "m", malicious_prompt, self.workspace
            )
        finally:
            del ha.PROFILES["_test_claude"]
        self.assertEqual(result.exit_state, ha.ExitState.SUCCESS)
        self.assertEqual(result.parsed_output["received"], malicious_prompt)
        self.assertFalse(marker.exists())

    # ---- jsonl (codex-shaped) parsing ----

    def test_jsonl_output_uses_last_object(self) -> None:
        exe = write_fake_cli(
            self.tmp,
            "fake-jsonl",
            """
            import json
            print(json.dumps({"event": "start"}))
            print(json.dumps({"event": "turn", "n": 1}))
            print(json.dumps({"event": "final", "result": "done"}))
            """,
        )
        profile = self.make_profile(exe, output_format="jsonl")
        ha.PROFILES["_test_codex"] = profile
        try:
            result = ha.invoke("_test_codex", ha.Role.SUPERVISOR, "m", "hi", self.workspace)
        finally:
            del ha.PROFILES["_test_codex"]
        self.assertEqual(result.exit_state, ha.ExitState.SUCCESS)
        self.assertEqual(result.parsed_output["event"], "final")

    def test_jsonl_malformed_line_is_malformed_output(self) -> None:
        exe = write_fake_cli(
            self.tmp,
            "fake-jsonl-bad",
            """
            import json
            print(json.dumps({"event": "start"}))
            print("not json")
            """,
        )
        profile = self.make_profile(exe, output_format="jsonl")
        ha.PROFILES["_test_codex"] = profile
        try:
            result = ha.invoke("_test_codex", ha.Role.SUPERVISOR, "m", "hi", self.workspace)
        finally:
            del ha.PROFILES["_test_codex"]
        self.assertEqual(result.exit_state, ha.ExitState.MALFORMED_OUTPUT)

    # ---- text output_format ----

    def test_text_output_format_never_parses_as_json(self) -> None:
        exe = write_fake_cli(
            self.tmp,
            "fake-text",
            """
            print("plain text response, not json")
            """,
        )
        profile = self.make_profile(exe, output_format="text")
        ha.PROFILES["_test_agy"] = profile
        try:
            result = ha.invoke("_test_agy", ha.Role.SUPERVISOR, "m", "hi", self.workspace)
        finally:
            del ha.PROFILES["_test_agy"]
        self.assertEqual(result.exit_state, ha.ExitState.SUCCESS)
        self.assertIsNone(result.parsed_output)
        self.assertIn("plain text response", result.stdout)

    # ---- freeze() ----

    def test_freeze_aborts_without_model(self) -> None:
        exe = write_fake_cli(self.tmp, "fake-version", "print('1.0.0')")
        profile = self.make_profile(exe)
        ha.PROFILES["_test_claude"] = profile
        try:
            with self.assertRaises(ha.AdapterError):
                ha.freeze("_test_claude", ha.Role.SUPERVISOR, "", self.workspace)
        finally:
            del ha.PROFILES["_test_claude"]

    def test_freeze_aborts_when_executable_missing(self) -> None:
        profile = self.make_profile(str(self.tmp / "nope"))
        ha.PROFILES["_test_claude"] = profile
        try:
            with self.assertRaises(ha.AdapterError):
                ha.freeze("_test_claude", ha.Role.SUPERVISOR, "test-model", self.workspace)
        finally:
            del ha.PROFILES["_test_claude"]

    def test_freeze_records_version_argv_and_workspace(self) -> None:
        exe = write_fake_cli(self.tmp, "fake-version-ok", "print('9.9.9-fake')")
        profile = self.make_profile(exe)
        ha.PROFILES["_test_claude"] = profile
        try:
            frozen = ha.freeze("_test_claude", ha.Role.IMPLEMENTER, "test-model-x", self.workspace)
        finally:
            del ha.PROFILES["_test_claude"]
        self.assertEqual(frozen.cli_version, "9.9.9-fake")
        self.assertEqual(frozen.model, "test-model-x")
        self.assertEqual(frozen.workspace, str(self.workspace.resolve()))
        self.assertIn("--permission-mode", frozen.argv)
        self.assertIn("acceptEdits", frozen.argv)
        self.assertIn("--model", frozen.argv)
        self.assertIn("test-model-x", frozen.argv)

    # ---- role_args wiring for the real profiles ----

    def test_real_profile_role_args_are_distinct_for_read_only_vs_implementer(self) -> None:
        for harness_id in ("claude", "agy", "codex", "grok"):
            profile = ha.get_profile(harness_id)
            supervisor_args = profile.role_args[ha.Role.SUPERVISOR.value]
            implementer_args = profile.role_args[ha.Role.IMPLEMENTER.value]
            self.assertNotEqual(
                supervisor_args, implementer_args, f"{harness_id} role_args must differ by role"
            )

    def test_grok_base_args_disable_web_and_subagents(self) -> None:
        profile = ha.get_profile("grok")
        self.assertIn("--no-subagents", profile.base_args)
        self.assertIn("--no-memory", profile.base_args)
        self.assertIn("--disable-web-search", profile.base_args)

    # ---- legacy config path ----

    def test_legacy_argv_placeholder_substitution_no_shell(self) -> None:
        argv, has_placeholder = ha.build_legacy_argv("some-cli --prompt '{prompt}'", "hello world")
        self.assertTrue(has_placeholder)
        self.assertEqual(argv, ["some-cli", "--prompt", "hello world"])

    def test_legacy_argv_without_placeholder_reports_no_placeholder(self) -> None:
        argv, has_placeholder = ha.build_legacy_argv("some-cli --flag", "hello world")
        self.assertFalse(has_placeholder)
        self.assertEqual(argv, ["some-cli", "--flag"])

    def test_legacy_agy_fallback_is_real_binary_not_antigravity_string(self) -> None:
        self.assertEqual(ha.LEGACY_FALLBACK_COMMANDS["agy"], "agy")
        self.assertNotEqual(ha.LEGACY_FALLBACK_COMMANDS["agy"], "antigravity")


if __name__ == "__main__":
    unittest.main()
