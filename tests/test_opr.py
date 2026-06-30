import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import importlib.machinery
import importlib.util

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


class TestOprRouting(unittest.TestCase):
    def test_is_frontier_model(self):
        self.assertTrue(opr.is_frontier_model("claude-3-5-sonnet"))
        self.assertTrue(opr.is_frontier_model("gpt-4o"))
        self.assertTrue(opr.is_frontier_model("antigravity-v2"))
        self.assertFalse(opr.is_frontier_model("gemma4:26b"))
        self.assertFalse(opr.is_frontier_model("llama3:8b"))

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


if __name__ == "__main__":
    unittest.main()
