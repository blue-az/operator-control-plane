#!/usr/bin/env python3
"""Postcondition suite for port-based output discovery (task `gated-runner-p0`).

Author-pinned gate. Fixture `pactl_cards_two_live.txt` was captured on the live
desktop with two displays powered on the same GPU:

    hdmi-output-0  available      device.product.name = "XB271HU"   -> output:hdmi-stereo
    hdmi-output-1  available      device.product.name = "LG TV"     -> output:hdmi-stereo-extra1
    hdmi-output-2  not available
    hdmi-output-3  not available

The port section binds the EDID name to the port and the port names its own
profiles, so no ELD parsing or pin/device inference is required. An earlier
ELD-rank implementation paired these two backwards; test_pairing_is_not_rank_based
pins the correct binding so that regression cannot return.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import audio_ports  # noqa: E402

FIX = Path(__file__).parent / "fixtures" / "audio"
TWO_LIVE = (FIX / "pactl_cards_two_live.txt").read_text()
ONE_LIVE = (FIX / "pactl_cards.txt").read_text()
GPU2 = "alsa_card.pci-0000_03_00.1"


class ParsePortsTests(unittest.TestCase):
    def test_parses_all_four_ports_on_the_gpu(self):
        cards = {c.name: c for c in audio_ports.parse_cards(TWO_LIVE)}
        ports = audio_ports.parse_ports(cards[GPU2])
        self.assertEqual(
            [p.name for p in ports],
            ["hdmi-output-0", "hdmi-output-1", "hdmi-output-2", "hdmi-output-3"],
        )

    def test_reads_availability(self):
        cards = {c.name: c for c in audio_ports.parse_cards(TWO_LIVE)}
        by = {p.name: p for p in audio_ports.parse_ports(cards[GPU2])}
        self.assertTrue(by["hdmi-output-0"].available)
        self.assertTrue(by["hdmi-output-1"].available)
        self.assertFalse(by["hdmi-output-2"].available)
        self.assertFalse(by["hdmi-output-3"].available)

    def test_reads_edid_product_name(self):
        cards = {c.name: c for c in audio_ports.parse_cards(TWO_LIVE)}
        by = {p.name: p for p in audio_ports.parse_ports(cards[GPU2])}
        self.assertEqual(by["hdmi-output-0"].product_name, "XB271HU")
        self.assertEqual(by["hdmi-output-1"].product_name, "LG TV")

    def test_unavailable_port_has_no_product_name(self):
        cards = {c.name: c for c in audio_ports.parse_cards(TWO_LIVE)}
        by = {p.name: p for p in audio_ports.parse_ports(cards[GPU2])}
        self.assertEqual(by["hdmi-output-2"].product_name, "")

    def test_reads_profiles_the_port_belongs_to(self):
        cards = {c.name: c for c in audio_ports.parse_cards(TWO_LIVE)}
        by = {p.name: p for p in audio_ports.parse_ports(cards[GPU2])}
        self.assertEqual(by["hdmi-output-0"].profiles, ["output:hdmi-stereo"])
        self.assertIn("output:hdmi-stereo-extra1", by["hdmi-output-1"].profiles)
        self.assertIn("output:hdmi-surround-extra1", by["hdmi-output-1"].profiles)


class StereoProfileTests(unittest.TestCase):
    def test_picks_the_stereo_profile_not_surround(self):
        cards = {c.name: c for c in audio_ports.parse_cards(TWO_LIVE)}
        by = {p.name: p for p in audio_ports.parse_ports(cards[GPU2])}
        self.assertEqual(
            audio_ports.stereo_profile(by["hdmi-output-1"]), "output:hdmi-stereo-extra1"
        )

    def test_returns_empty_when_port_has_no_stereo_profile(self):
        port = audio_ports.Port(
            name="x", description="x", available=True, product_name="", profiles=[]
        )
        self.assertEqual(audio_ports.stereo_profile(port), "")


class DiscoverTests(unittest.TestCase):
    def _discover(self, text):
        return audio_ports.discover(audio_ports.parse_cards(text))

    def test_two_live_displays_yield_two_outputs(self):
        self.assertEqual(len(self._discover(TWO_LIVE)), 2)

    def test_pairing_is_not_rank_based(self):
        """Regression pin: pin order is the reverse of device order on this codec."""
        by = {o.label: o for o in self._discover(TWO_LIVE)}
        self.assertEqual(by["XB271HU"].profile, "output:hdmi-stereo")
        self.assertEqual(by["LG TV"].profile, "output:hdmi-stereo-extra1")

    def test_surround_profiles_do_not_become_separate_outputs(self):
        labels = [o.label for o in self._discover(TWO_LIVE)]
        for label in labels:
            self.assertNotIn("Surround", label)
        self.assertEqual(sorted(labels), ["LG TV", "XB271HU"])

    def test_marks_the_active_output(self):
        active = [o for o in self._discover(TWO_LIVE) if o.active]
        self.assertEqual([o.label for o in active], ["XB271HU"])

    def test_ignores_the_display_less_gpu(self):
        for o in self._discover(TWO_LIVE):
            self.assertNotEqual(o.card, "alsa_card.pci-0000_01_00.1")

    def test_single_live_display_fixture_still_resolves(self):
        outs = self._discover(ONE_LIVE)
        self.assertEqual([o.label for o in outs], ["XB271HU"])

    def test_output_carries_card_and_port(self):
        o = [x for x in self._discover(TWO_LIVE) if x.label == "LG TV"][0]
        self.assertEqual(o.card, GPU2)
        self.assertEqual(o.port, "hdmi-output-1")


if __name__ == "__main__":
    unittest.main()
