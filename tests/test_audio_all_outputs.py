#!/usr/bin/env python3
"""Gate for non-HDMI output discovery (task `gated-runner-p0`).

Author-pinned. The F11 cycle historically included headphones/EarPods, so
discovery must not be limited to `output:hdmi-*`. Two fixtures:

  pactl_cards_three_live.txt  three displays live, nothing in the analog jacks
  pactl_cards_headphones.txt  same, with analog-output-headphones plugged in

Profile choice matters as much as port choice: the PCH card is currently
`input:analog-stereo` and carries the working microphone, so selecting the
output-only `output:analog-stereo` would silently kill the mic. When a duplex
profile exists for a port, it must win.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))  # audio_* moved to scripts/ 2026-08-29

import audio_ports

FIX = Path(__file__).parent / "fixtures" / "audio"
THREE = (FIX / "pactl_cards_three_live.txt").read_text()
HEADPHONES = (FIX / "pactl_cards_headphones.txt").read_text()
PCH = "alsa_card.pci-0000_00_1f.3"


def discover(text):
    return audio_ports.discover(audio_ports.parse_cards(text))


class HdmiUnchangedTests(unittest.TestCase):
    def test_three_displays_still_yield_three_outputs(self):
        labels = [o.label for o in discover(THREE)]
        self.assertEqual(sorted(labels), ["LG TV", "LG TV SSCR2", "XB271HU"])

    def test_hdmi_profiles_unchanged(self):
        by = {o.label: o for o in discover(THREE)}
        self.assertEqual(by["XB271HU"].profile, "output:hdmi-stereo")
        self.assertEqual(by["LG TV"].profile, "output:hdmi-stereo-extra1")
        self.assertEqual(by["LG TV SSCR2"].profile, "output:hdmi-stereo-extra2")

    def test_unplugged_analog_jacks_are_not_offered(self):
        for o in discover(THREE):
            self.assertNotEqual(o.card, PCH)


class HeadphoneTests(unittest.TestCase):
    def test_plugged_headphones_appear(self):
        labels = [o.label for o in discover(HEADPHONES)]
        self.assertIn("Headphones", labels)

    def test_headphones_added_without_displacing_displays(self):
        labels = sorted(o.label for o in discover(HEADPHONES))
        self.assertEqual(labels, ["Headphones", "LG TV", "LG TV SSCR2", "XB271HU"])

    def test_duplex_profile_wins_so_the_microphone_survives(self):
        by = {o.label: o for o in discover(HEADPHONES)}
        self.assertEqual(by["Headphones"].profile, "output:analog-stereo+input:analog-stereo")

    def test_headphones_bound_to_the_pch_card_and_port(self):
        by = {o.label: o for o in discover(HEADPHONES)}
        self.assertEqual(by["Headphones"].card, PCH)
        self.assertEqual(by["Headphones"].port, "analog-output-headphones")


class InputPortTests(unittest.TestCase):
    def test_microphone_ports_are_never_offered_as_outputs(self):
        for text in (THREE, HEADPHONES):
            for o in discover(text):
                self.assertNotIn("input", o.port)
                self.assertTrue(o.profile.startswith("output:"))

    def test_available_rear_mic_is_not_an_output(self):
        """analog-input-rear-mic is `available` but is an input."""
        labels = [o.label for o in discover(HEADPHONES)]
        self.assertNotIn("Rear Microphone", labels)


class ProfileChoiceTests(unittest.TestCase):
    def test_surround_never_chosen_over_stereo(self):
        for text in (THREE, HEADPHONES):
            for o in discover(text):
                self.assertNotIn("surround", o.profile)


if __name__ == "__main__":
    unittest.main()
