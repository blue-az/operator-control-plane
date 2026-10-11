from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from runner import build_carrier_command, provision_carrier_config


class CarrierIsolationTest(unittest.TestCase):
    def test_provider_config_is_copied_outside_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = root / "fixture"
            fixture.mkdir()
            (fixture / "main.py").write_text("pass\n")
            source = root / "models.json"
            source.write_text('{"models": []}\n')

            config_dir = provision_carrier_config(source)
            try:
                self.assertFalse(config_dir.is_relative_to(fixture))
                self.assertEqual((config_dir / "models.json").read_text(), source.read_text())
                self.assertEqual(sorted(path.name for path in fixture.iterdir()), ["main.py"])
            finally:
                shutil.rmtree(config_dir, ignore_errors=True)

    def test_carrier_receives_external_config_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = root / "fixture"
            config = root / "config"
            fixture.mkdir()
            config.mkdir()
            script = root / "carrier.sh"
            argv, env = build_carrier_command(
                ["pi", "--print"], fixture, script, "local", config
            )

        self.assertEqual(argv[:4], [str(script), str(fixture), str(config), "env"])
        self.assertIn("PI_CODING_AGENT_DIR=/pi-config", argv)
        self.assertEqual(env["PI_CODING_AGENT_DIR"], "/pi-config")

    def test_native_carrier_keeps_pi_runtime_on_tmpfs(self):
        carrier = Path(__file__).with_name("native_carrier.sh").read_text()
        self.assertIn('--tmpfs /pi-config', carrier)
        self.assertIn('"$pi_config/models.json" /pi-config/models.json', carrier)
        self.assertNotIn('"$work/pi-config/models.json"', carrier)
        self.assertIn('--dir /tmp/pi-home', carrier)

    def test_carrier_requires_external_config_source(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "isolated carrier config"):
                build_carrier_command(["pi"], Path(directory), Path("carrier.sh"))


if __name__ == "__main__":
    unittest.main()
