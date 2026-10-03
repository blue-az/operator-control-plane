# ABORTED — desktop disk full (environment), not a model or serving fault

2026-10-01 06:19 UTC, canary cell 3 of 3 (booking L2): the before-gate could not
write its capture: `OSError: [Errno 28] No space left on device`. Cause: Chrome on
the desktop crashed (NVRM VA-space errors) and systemd-coredump filled the
remaining ~20 GiB of `/` before discarding the dump. Space returned within a minute.
Two canary cells were qualified passes; nothing scored. Rerun in `-r3`.
