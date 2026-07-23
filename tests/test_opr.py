import importlib.machinery
import importlib.util
import os
import shutil
import stat
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

import harness_adapter as ha

# Dynamically load the extensionless 'opr' script as a module
opr_path = str(Path(__file__).resolve().parents[1] / "opr")
loader = importlib.machinery.SourceFileLoader("opr", opr_path)
spec = importlib.util.spec_from_loader("opr", loader)
opr = importlib.util.module_from_spec(spec)
loader.exec_module(opr)


class TestOprSafePath(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp()).resolve()

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)

    def test_resolve_safe_path_inside(self):
        target = self.temp_dir / "subdir" / "file.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("hello")

        resolved = opr.resolve_safe_path("subdir/file.txt", self.temp_dir)
        self.assertEqual(resolved, target)

    def test_resolve_safe_path_outside(self):
        with self.assertRaises(PermissionError):
            opr.resolve_safe_path("../outside.txt", self.temp_dir)

    def test_resolve_safe_path_absolute_outside(self):
        with self.assertRaises(PermissionError):
            opr.resolve_safe_path("/etc/passwd", self.temp_dir)


class TestOprConfig(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp()).resolve()

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)

    def test_load_config_defaults(self):
        config = opr.load_config("/nonexistent/opr.yaml")
        self.assertEqual(config["default_model"], "gemma4:26b")
        self.assertFalse(config["frontier"]["enabled"])
        self.assertFalse(config["tools"]["write"])

    def test_load_config_custom(self):
        yaml_content = """
default_model: my-custom-model
frontier:
  enabled: true
tools:
  write: true
"""
        cfg_file = self.temp_dir / "custom_opr.yaml"
        cfg_file.write_text(yaml_content)

        config = opr.load_config(str(cfg_file))
        self.assertEqual(config["default_model"], "my-custom-model")
        self.assertTrue(config["frontier"]["enabled"])
        self.assertTrue(config["tools"]["write"])


class TestOprGovernanceSetup(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp()).resolve()

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)

    def test_initialize_ledger_requires_operator_when_governed(self):
        with self.assertRaises(FileNotFoundError) as ctx:
            opr.initialize_ledger(str(self.temp_dir), None, govern=True)
        self.assertIn("Governed ledger binary not found", str(ctx.exception))

    def test_initialize_ledger_skips_operator_when_not_governed(self):
        result = opr.initialize_ledger(str(self.temp_dir), None, govern=False)
        self.assertEqual(result, str(self.temp_dir))
        self.assertFalse((self.temp_dir / ".operator").exists())

    def test_configured_operator_bin_can_be_found_on_path(self):
        with mock.patch.object(opr.shutil, "which", return_value="/usr/local/bin/operator"):
            self.assertEqual(
                opr.find_operator_bin({"operator_bin": "custom-operator"}),
                "/usr/local/bin/operator",
            )


class TestOprRouting(unittest.TestCase):
    def test_is_frontier_model(self):
        self.assertTrue(opr.is_frontier_model("claude-3-5-sonnet"))
        self.assertTrue(opr.is_frontier_model("gpt-4o"))
        self.assertTrue(opr.is_frontier_model("antigravity-v2"))
        self.assertTrue(opr.is_frontier_model("grok-4"))
        self.assertTrue(opr.is_frontier_model("copilot"))
        self.assertFalse(opr.is_frontier_model("gemma4:26b"))
        self.assertFalse(opr.is_frontier_model("llama3:8b"))

    def test_default_config_agy_fallback_is_real_binary(self):
        config = opr.load_config("/nonexistent/opr.yaml")
        self.assertEqual(config["frontier"]["commands"]["agy"], "agy")
        self.assertNotEqual(config["frontier"]["commands"]["agy"], "antigravity")

    def test_local_ollama_model_overrides_frontier_name_heuristic(self):
        config = opr.load_config("/nonexistent/opr.yaml")
        config["_local_ollama_models"] = {"gpt-oss:latest"}
        self.assertTrue(opr.is_frontier_model("gpt-oss:latest"))
        self.assertFalse(opr.is_effective_frontier_model("gpt-oss:latest", config))

    def test_get_frontier_lane(self):
        self.assertEqual(opr.get_frontier_lane("review the code changes"), "frontier_driver")
        self.assertEqual(opr.get_frontier_lane("write a python script"), "frontier_author")

    def test_route_task_default(self):
        config = opr.load_config("/nonexistent/opr.yaml")
        result = opr.route_task("implement feature", config)
        self.assertEqual(result.worker["model"], "gemma4:26b")
        self.assertEqual(result.lane, "lane_1_local_repair")

    def test_route_task_frontier_disabled(self):
        config = opr.load_config("/nonexistent/opr.yaml")
        config["frontier"]["enabled"] = False
        result = opr.route_task("use claude to write a compiler", config)
        # Even with 'claude' keyword, fallback to default local model since frontier is disabled
        self.assertEqual(result.worker["model"], "gemma4:26b")

    def test_route_task_frontier_enabled(self):
        config = opr.load_config("/nonexistent/opr.yaml")
        config["frontier"]["enabled"] = True
        result = opr.route_task("use claude to write a compiler", config)
        self.assertEqual(result.worker["model"], "claude")
        self.assertEqual(result.lane, "lane_3_strong_model")

    def test_route_task_default_gpt_oss_local(self):
        config = opr.load_config("/nonexistent/opr.yaml")
        config["default_model"] = "gpt-oss:latest"
        config["_local_ollama_models"] = {"gpt-oss:latest"}
        result = opr.route_task("implement feature", config)
        self.assertEqual(result.worker["model"], "gpt-oss:latest")
        self.assertEqual(result.worker["provider"], "local_ollama")


def write_fake_cli(directory: Path, name: str, body: str) -> str:
    path = directory / name
    path.write_text("#!/usr/bin/env python3\n" + textwrap.dedent(body))
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return str(path)


class TestOprDispatchFrontier(unittest.TestCase):
    """opr's dispatch_frontier() must use the typed harness_adapter profile by
    default, and only fall back to the deprecated shlex string-template path
    when opr.yaml explicitly customizes a harness's command."""

    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp()).resolve()
        self.workspace = self.temp_dir / "workspace"
        self.workspace.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)

    def test_resolve_frontier_harness_id(self):
        self.assertEqual(opr.resolve_frontier_harness_id("claude-3-5-sonnet"), "claude")
        self.assertEqual(opr.resolve_frontier_harness_id("codex-large"), "codex")
        self.assertEqual(opr.resolve_frontier_harness_id("grok-4"), "grok")
        self.assertEqual(opr.resolve_frontier_harness_id("gemini-agy"), "agy")
        self.assertEqual(opr.resolve_frontier_harness_id("antigravity"), "agy")
        self.assertIsNone(opr.resolve_frontier_harness_id("gemma4:26b"))

    def test_dispatch_frontier_uses_typed_adapter_by_default(self):
        exe = write_fake_cli(
            self.temp_dir,
            "fake-claude",
            """
            import sys, json
            data = sys.stdin.read()
            print(json.dumps({"result": f"typed-adapter-saw:{data}"}))
            """,
        )
        real_profile = ha.PROFILES["claude"]
        ha.PROFILES["claude"] = ha.HarnessProfile(
            harness_id="claude",
            executable=exe,
            base_args=real_profile.base_args,
            prompt_transport=ha.PromptTransport.STDIN,
            output_format="json",
            role_args=real_profile.role_args,
        )
        try:
            config = opr.load_config("/nonexistent/opr.yaml")
            response = opr.dispatch_frontier("claude-3-5-sonnet", "hello", self.workspace, config)
        finally:
            ha.PROFILES["claude"] = real_profile
        self.assertEqual(response, "typed-adapter-saw:hello")

    def test_dispatch_frontier_falls_back_to_legacy_when_customized(self):
        exe = write_fake_cli(
            self.temp_dir,
            "fake-legacy-claude",
            """
            import sys
            print("legacy-path-response:" + sys.stdin.read())
            """,
        )
        config = opr.load_config("/nonexistent/opr.yaml")
        config["frontier"]["commands"]["claude"] = exe
        response = opr.dispatch_frontier("claude-3-5-sonnet", "hello", self.workspace, config)
        self.assertIn("legacy-path-response:hello", response)

    def test_dispatch_frontier_reports_typed_nonzero_exit_without_apparent_success(self):
        exe = write_fake_cli(
            self.temp_dir,
            "fake-claude-broken",
            """
            import sys
            sys.stderr.write("internal harness failure\\n")
            sys.exit(3)
            """,
        )
        real_profile = ha.PROFILES["claude"]
        ha.PROFILES["claude"] = ha.HarnessProfile(
            harness_id="claude",
            executable=exe,
            base_args=real_profile.base_args,
            prompt_transport=ha.PromptTransport.STDIN,
            output_format="json",
            role_args=real_profile.role_args,
        )
        try:
            config = opr.load_config("/nonexistent/opr.yaml")
            response = opr.dispatch_frontier("claude-3-5-sonnet", "hello", self.workspace, config)
        finally:
            ha.PROFILES["claude"] = real_profile
        self.assertIn("Frontier Subprocess Dispatch Error", response)
        self.assertIn("exited 3", response)
        self.assertIn("internal harness failure", response)


if __name__ == "__main__":
    unittest.main()
