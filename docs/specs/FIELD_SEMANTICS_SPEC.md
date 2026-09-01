# Field Semantics Specification

## Gate artifact and verification command

`claim.required_gate` is the required gate artifact path, relative to the task
repository unless absolute. For `test_passes` claims, `doctor` checks that it
exists. It is not a shell command and is never executed.

`claim.verify_cmd` is the exact command a reviewer may rerun. An explicit
`review-delegate --verify-cmd` takes precedence, then `claim.verify_cmd`;
delegation fails if neither is present. A delegate never derives a command from
`required_gate`.

## Reviewer routing

`task.review_harness` identifies a preferred routing destination only. It is not
verification authority. Authority comes from recorded verifier identity and,
in enforced mode, distinct OS-UID provenance. `review-delegate --reviewer` is
therefore explicit and never defaults from `review_harness`. `task-route` can
replace or clear the route with an operator rationale and records the prior/new
values in a dedicated `route_correction` record under
`.operator/route_corrections/`; the task's effective projection references the
correction and retains its prior history. Route correction requires the
executing identity to have the `operator` role in enforced mode.

## Quarantine correction

Quarantine recovery is intentionally a separate follow-up change. This field
semantics change does not alter quarantine promotion rules.
