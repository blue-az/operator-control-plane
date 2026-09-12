# VOID RUN — do not use these numbers

**Run:** 2026-09-11, desktop (i9-9900KF + RTX 2080). All 8 cells failed in
0.5-0.6 s. No model was ever loaded; GPU utilisation never left 0%.

## Cause: the pinned tag was passed to a runner that does its own pinning

`runner.py` takes the **base** tag and appends `-e9pin-ctx16384-t0p8` itself.
It was given the already-pinned tag, so it built:

    gemma4-26b-e9pin-ctx16384-t0p8-e9pin-ctx16384-t0p8:latest

which does not exist. `pi` warned `Model ... not found for provider "ollama".
Using custom model id` and **continued instead of failing**. The agent did
nothing, source files were never edited, and the postconditions failed against
unmodified fixtures. The 0.6 s wall clock is the scoring step alone.

Note the side effect: that doubled tag now exists in `ollama list` on this host,
created by the pinning step. It is an artifact of this void run, not a model.

## Second fault found while diagnosing: localhost is not this machine

    ssh -f -N -L 11434:127.0.0.1:11434 testbench    # pid 1399563, started 17:01

`getent ahosts localhost` returns `::1` first, so `localhost:11434` reaches
**testbench**, while `127.0.0.1:11434` reaches the local daemon. Both report
ollama 0.32.12. The tunnel endpoint had `qwen3.8:27b` resident at 25,107 MiB
fully in VRAM, impossible on this 8 GiB card.

`runner.py` hardcodes `http://localhost:11434` (lines 206, 615, 619) and
`~/.pi/agent/models.json` sets `baseUrl: http://localhost:11434/v1`. Neither
accepts a host argument. **`gemma4:26b` and its pinned variant exist on both
endpoints**, so a misrouted run loads successfully and returns plausible
numbers from the wrong GPU, with no error.

`OPERATOR_MACHINE=desktop` is set by hand and does not witness which daemon
answered.

**Consequence: no 2080 measurement can be trusted from this host until the
endpoint is pinned to 127.0.0.1 or the tunnel is down.** Not yet resolved.
