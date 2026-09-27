# native_carrier.sh — the bwrap carrier for native testbench runs

Deployed copy lives at `testbench:~/.local-lane-native-v1/native_carrier.sh`.
It was untracked until 2026-09-27; this is that file, brought into the repo so
its changes can be reviewed and cannot be lost with the host.

## Why it is here

On 2026-09-27 the carrier was found to bind the **entire harness directory**
into the sandbox:

    --ro-bind /home/ef-tb/.local-lane-native-v1 /work/native   ... --chdir /work

That put `native/tasks/*.yaml` — every task's exact postcondition regex and all
three prompt levels — inside the model's own working directory, one `ls` away.
Verified by running the carrier directly: from the model's cwd,
`native/tasks/ambiguous_anchor.yaml` was readable and supplied the L2 literal
`"Run: restart the service --force"` along with the grading pattern.

It existed to provide one two-line shell script (`pi-wrapper`, which execs
node). The whole directory came with it.

The fix binds only that file, outside `/work`:

    --dir /opt --ro-bind /home/ef-tb/.local-lane-native-v1/pi-wrapper /opt/pi-wrapper

and `runner.py`'s `PI_BIN` points at `/opt/pi-wrapper`. After the change, `ls`
in the model's cwd shows only the fixture.

## What it does not invalidate

L2 prompts already contain the exact literals, so reading the task file adds
nothing there. L1 and L0 were re-run clean on 2026-09-27 and both reproduced
their pre-fix results within one cell, so the leak was reachable but was not
being exploited. See the `answer_key_in_sandbox` entry in
`magic_bridge/benchmark_definitions.yaml`.
