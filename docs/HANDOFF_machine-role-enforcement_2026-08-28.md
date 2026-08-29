# Luna Handoff — machine-role-enforcement

## What changed
- Updated `operator` with `init --role {seat,outbox}` and `--seat-machine`.
- New stores write `role` and `seat_machine` to `operator.yaml`; default role is `seat` and default machine is the executing machine.
- Seat initialization rejects an explicitly different machine unless `--role outbox` is used.
- `doctor` structurally reads store role metadata, defaults absent role to seat with one Info diagnostic, errors on seat/machine mismatch, and warns with counts and destination for outbox stores.
- Added machine-role integration tests in `tests/test_operator.py` using the required test identity and machine hooks.

## What was verified
Actual command output:

```text
$ python3 -m unittest tests.test_operator
...........................................................................
----------------------------------------------------------------------
Ran 75 tests in 80.466s

OK

$ ./operator init --help
usage: operator init [-h] [--role {seat,outbox}] [--seat-machine SEAT_MACHINE]
```

`git diff --check` exited 0. The configured `pytest` launcher could not run because its stale virtualenv interpreter was missing; the equivalent unittest suite passed.

## What is claimed
- Claim `claim-0115` was registered on `machine-role-enforcement` by session `01a04bef-2cf3-737a-bfae-d904c99aca3b`.
- Evidence `evidence-0001` and updated `evidence-0002` contain full suite output and are attached to that claim.
- The claim and evidence remain unverified, as required.

## Open items
- Distinct review identity `claude` must verify the claim/evidence and inspect the implementation against acceptance criteria 1–7.
- Enrolled/broker-backed doctor behavior was not separately exercised; no changes were made to broker authority semantics.
- The existing stale pytest environment should be repaired independently if pytest invocation is required.

## Proposed next action
Have the distinct Claude review harness run the machine-role tests and review the diff, then attach verification status using its separate identity.
