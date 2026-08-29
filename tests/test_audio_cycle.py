#!/usr/bin/env python3
"""Postcondition suite for audio_cycle.py (task `gated-runner-p0`).

Author-pinned gate. Cycling between two outputs on the SAME card is a card
*profile* switch, not a sink switch -- a card holds one profile at a time. The
sink name that results is derivable from the card and profile names, which is
what lets the switch be planned before it is applied.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))  # audio_* moved to scripts/ 2026-08-29

import audio_cycle
from audio_ports import Output

CARD = "alsa_card.pci-0000_03_00.1"
XB = Output("XB271HU", CARD, "output:hdmi-stereo", True, "hdmi-output-0")
LG = Output("LG TV", CARD, "output:hdmi-stereo-extra1", False, "hdmi-output-1")


class SinkNameTests(unittest.TestCase):
    def test_derives_sink_name_from_card_and_profile(self):
        self.assertEqual(
            audio_cycle.sink_name(XB), "alsa_output.pci-0000_03_00.1.hdmi-stereo"
        )

    def test_derives_sink_name_for_extra_profile(self):
        self.assertEqual(
            audio_cycle.sink_name(LG), "alsa_output.pci-0000_03_00.1.hdmi-stereo-extra1"
        )


class NextOutputTests(unittest.TestCase):
    def test_advances_from_active_to_the_next(self):
        self.assertEqual(audio_cycle.next_output([XB, LG]).label, "LG TV")

    def test_wraps_around_at_the_end(self):
        outs = [Output("XB271HU", CARD, "p0", False, "a"), Output("LG TV", CARD, "p1", True, "b")]
        self.assertEqual(audio_cycle.next_output(outs).label, "XB271HU")

    def test_falls_back_to_first_when_none_is_active(self):
        outs = [Output("A", CARD, "p0", False, "a"), Output("B", CARD, "p1", False, "b")]
        self.assertEqual(audio_cycle.next_output(outs).label, "A")

    def test_single_output_returns_itself(self):
        self.assertEqual(audio_cycle.next_output([XB]).label, "XB271HU")

    def test_empty_list_returns_none(self):
        self.assertIsNone(audio_cycle.next_output([]))


class SwitchCommandTests(unittest.TestCase):
    def test_sets_card_profile_before_default_sink(self):
        cmds = audio_cycle.switch_commands(LG)
        self.assertEqual(cmds[0][:2], ["pactl", "set-card-profile"])
        self.assertEqual(cmds[1][:2], ["pactl", "set-default-sink"])

    def test_uses_the_right_card_and_profile(self):
        cmds = audio_cycle.switch_commands(LG)
        self.assertEqual(cmds[0][2], CARD)
        self.assertEqual(cmds[0][3], "output:hdmi-stereo-extra1")

    def test_targets_the_derived_sink(self):
        cmds = audio_cycle.switch_commands(LG)
        self.assertEqual(cmds[1][2], "alsa_output.pci-0000_03_00.1.hdmi-stereo-extra1")

    def test_never_emits_a_shell_string(self):
        for cmd in audio_cycle.switch_commands(LG):
            self.assertIsInstance(cmd, list)


if __name__ == "__main__":
    unittest.main()
