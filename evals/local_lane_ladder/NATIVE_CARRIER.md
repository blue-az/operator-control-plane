# native_carrier.sh — the bwrap carrier for native testbench runs

The deployed copy lives at `testbench:~/.local-lane-native-v1/native_carrier.sh`.
This repository version now expects a separate Pi-config directory argument;
the remote copy was not changed here and must be updated or replaced by an
updated temporary carrier before another run. The file was untracked until
2026-09-27; this is the reviewed source copy.

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

## Pi runtime state is not fixture state

The carrier receives the task fixture and a separate, temporary directory
containing only `models.json`. It mounts that file read-only at
`/pi-config/models.json`; `/pi-config` and `/tmp/pi-home` are separate from
`/work` and live on tmpfs. Pi may create auth metadata, model-store metadata,
and session files there without those harness files entering the graded
fixture.
The temporary host config directory is removed after the cell. Do not restore a
config directory beneath the fixture or exempt such paths from scope grading.

## What it does not invalidate

L2 prompts already contain the exact literals, so reading the task file adds
nothing there. L1 and L0 were re-run clean on 2026-09-27 and both reproduced
their pre-fix results within one cell, so the leak was reachable but was not
being exploited. See the `answer_key_in_sandbox` entry in
`magic_bridge/benchmark_definitions.yaml`.
