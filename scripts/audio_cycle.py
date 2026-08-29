from audio_ports import Output, discover, parse_cards


def sink_name(output) -> str:
    card = output.card.replace("alsa_card.", "alsa_output.")
    profile = output.profile.removeprefix("output:")
    return f"{card}.{profile}"


def next_output(outputs):
    if not outputs:
        return None
    for i, output in enumerate(outputs):
        if output.active:
            return outputs[(i + 1) % len(outputs)]
    return outputs[0]


def switch_commands(output) -> list:
    return [
        ["pactl", "set-card-profile", output.card, output.profile],
        ["pactl", "set-default-sink", sink_name(output)],
    ]


def cycle(dry_run=False):
    """Advance to the next live audio output. Returns its label, or None."""
    import subprocess

    text = subprocess.run(["pactl", "list", "cards"], capture_output=True, text=True).stdout
    target = next_output(discover(parse_cards(text)))
    if target is None:
        return None
    for cmd in switch_commands(target):
        if dry_run:
            print(" ".join(cmd))
        else:
            subprocess.run(cmd, capture_output=True, text=True)
    return target.label


if __name__ == "__main__":
    import sys

    label = cycle(dry_run="--dry-run" in sys.argv)
    print(label if label else "no live audio output")
