"""Discover live audio outputs and their EDID names from PipeWire card ports.

Implementation written by qwen3.8:27b via opencode against tests/test_audio_ports.py;
gemma4:26b and gemma4:31b independently produced passing implementations of the
same contract and agree with this one on live hardware.

`pactl list cards` already carries what every earlier approach tried to
reconstruct: each HDMI/DP port has a presence-detect flag, the connected
display's EDID name in `device.product.name`, and the profiles that port belongs
to. Reading it directly removes the ELD parsing, the pin/device inference, and
the rank-pairing heuristic used before -- which a second live display proved
wrong, since pin order is the reverse of device order on this codec and LG TV
and XB271HU came out swapped.

Nothing here keys on a sink index, a `pro-output-N` channel pair, an ALSA card
number, or a PCI path. The kernel reassigns all of those, which is why labels
built on them drift.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Port:
    name: str
    description: str
    available: bool
    product_name: str
    profiles: list


@dataclass
class Card:
    name: str
    active_profile: str
    ports_text: str = ""


@dataclass
class Output:
    label: str
    card: str
    profile: str
    active: bool
    port: str = ""


HEADER_RE = re.compile(r"^\t\t(\S+): (.*?) \(type:.*,\s*(not available|available)\)$")


def parse_cards(text):
    cards = []
    for match in re.finditer(r"Card #\d+\n(.*?)(?=Card #|\Z)", text, re.S):
        block = match.group(1)
        name = re.search(r"\tName: (.*)", block).group(1)
        active_match = re.search(r"\tActive Profile: (.*)", block)
        active_profile = active_match.group(1) if active_match else ""
        ports_match = re.search(r"\tPorts:\n(.*)", block, re.S)
        ports_text = ports_match.group(1) if ports_match else ""
        cards.append(Card(name, active_profile, ports_text))
    return cards


def _parse_block(name, description, available, body):
    prod_match = re.search(r'device\.product\.name = "([^"]*)"', body)
    product_name = prod_match.group(1) if prod_match else ""
    profiles_match = re.search(r"Part of profile\(s\): (.*)", body)
    if profiles_match:
        profiles = [p.strip() for p in profiles_match.group(1).split(",")]
    else:
        profiles = []
    return Port(name, description, available, product_name, profiles)


def parse_ports(card):
    ports = []
    name = None
    description = None
    available = False
    body_lines = []
    for line in card.ports_text.splitlines():
        match = HEADER_RE.match(line)
        if match:
            if name is not None:
                ports.append(_parse_block(name, description, available, "\n".join(body_lines)))
            name = match.group(1)
            description = match.group(2)
            available = match.group(3) == "available"
            body_lines = []
        elif name is not None:
            body_lines.append(line)
    if name is not None:
        ports.append(_parse_block(name, description, available, "\n".join(body_lines)))
    return ports


def stereo_profile(port):
    """The port's stereo profile, preferring a duplex one so a mic survives.

    Choosing the output-only `output:analog-stereo` on the PCH card would drop
    its `input:analog-stereo` microphone, so a `+input:` variant wins when the
    port offers one. Surround variants are never chosen over stereo.
    """
    candidates = [p for p in port.profiles if "stereo" in p and "surround" not in p]
    if not candidates:
        candidates = [p for p in port.profiles if p.startswith("output:")]
    if not candidates:
        return ""
    for profile in candidates:
        if "+input:" in profile:
            return profile
    return candidates[0]


def discover(cards):
    outputs = []
    for card in cards:
        for port in parse_ports(card):
            if not port.available:
                continue
            if "input" in port.name:
                continue
            if not any(p.startswith("output:") for p in port.profiles):
                continue
            profile = stereo_profile(port)
            if not profile:
                continue
            label = port.product_name or port.description
            outputs.append(
                Output(
                    label,
                    card.name,
                    profile,
                    card.active_profile == profile,
                    port.name,
                )
            )
    return outputs


def live_outputs():
    """Discover against the running PipeWire instance."""
    import subprocess

    text = subprocess.run(["pactl", "list", "cards"], capture_output=True, text=True).stdout
    return discover(parse_cards(text))


if __name__ == "__main__":
    for out in live_outputs():
        print(("* " if out.active else "  ") + out.label.ljust(14) + out.profile)
