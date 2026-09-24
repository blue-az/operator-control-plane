# Confirmed distinct-UID verifier runs

Status: experimental implementation contract; automated tests are not live privileged acceptance.
Tracks POE-FUT-009. The existing POE-FUT-007 popup acceptance task remains separate.

## Surfaces

- `/op:verify-run [review-bundle-id]`: human-only Pi shortcut; omitted ID opens a chooser.
- `python3 scripts/operator_verify_run.py inspect --root ROOT --bundle ID`: read-only preflight, JSON output.
- `python3 scripts/operator_verify_run.py run --root ROOT --bundle ID --expected TOKEN`: verifier-only runner. This is not a general command executor.

The extension confirms exact `sudo -A -H -u USER -- python3 ... run ...` argv,
claim/task, model, command to review, private log location, potential model usage,
and the helper's decision-gated evidence attachment. It never collects passwords
or explicitly forwards author credentials; sudo/account configuration still
controls the inherited environment. No `sudo -S`, `-E`, root verifier, advisory fallback, or user
supplied verdict/status flag is exposed. `SUDO_ASKPASS` uses the existing resolver.

## Preflight and authority

1. Require a local, non-broker ledger and a named `uid-isolated` review bundle.
2. Check bundle/claim/task/root relationships and a valid recorded author UID.
3. Resolve the Unix account; require non-root UID different from the author.
4. Reuse Operator's identity policy parser: enforced mode and verifier role required.
5. Refuse every `OPERATOR_TEST_*` environment override on this production path.
6. Hash bundle, claim, task, policy, runner and Operator CLI bytes into the confirmed
   token. Recheck immediately under the verifier UID and before evidence attachment.
7. Require real/effective UID and HOME to match the registered verifier account.

The script's stored shell command is **not executed**. The runner constructs fixed
Pi argv from validated model/provider fields, supplies a new session ID, and uses
`--no-approve --print`. The reviewer receives the bundle as untrusted input and is
asked to independently assess the named claim, rerun its verification command,
and avoid code/test/policy/ledger mutation. This is a review contract, **not an OS
sandbox**. The authorized verifier process has that Unix account's permissions.
The helper, Operator CLI and verification command come from the **author-writable
checkout** and execute with the verifier account's permissions and credentials.
Author-controlled code can therefore write verifier evidence without following
this helper's decision-file gate. The human must trust that code and the verifier's
Pi configuration before authorizing it. Input hashes establish only freshness
since confirmation, not code trust, signing, or independence from the author.
A resulting `uid_isolated` record demonstrates a distinct executing UID; it does
not establish independent judgment, isolation from author code, or a correct review.

## Logs and reviewer decision

Each run creates a new verifier-owned 0700 directory under
`$HOME/.operator-verifier-runs/<session-uuid>/`. Review stdout/stderr go to a 0600
`review.log`, not to the author session's transcript. The process group is killed
on a 600-second timeout. Errors and logs are retained for diagnosis.

The reviewer must create a fresh regular, verifier-owned `decision.json`, not
writable by other users, with exactly:

```json
{
  "claim_id": "claim-0001",
  "approve": false,
  "reason": "Independent assessment",
  "checks": ["Checks actually performed"]
}
```

No process exit code is a verdict. Wrong claim, missing/malformed decision,
rejection, launch failure, timeout, or input drift prevents this helper's automatic
attachment. The helper does not automatically quarantine or change prior status
on these failures. This says nothing about writes performed by the launched code,
which has the verifier's permissions and is not constrained by the decision gate.

On explicit approval and successful reviewer exit, the runner combines the
closed review log with the decision into `evidence.txt`. It invokes Operator's
existing `evidence-attach` **as the verifier UID**, with explicit task/claim,
`run_log`, session-derived author, registered verifier name, fixed verified
status, reviewer reason, verification command and artifact SHA-256. The backend's
identity/gate checks remain authoritative. Attachment failure is reported and
retains logs; there is no weaker fallback or automatic retry. `attachment.log`
and `result.json` record the outcome. Successful output is narration until the
claim/evidence records establish it.

The slash command does not accept `approve`, reason, a decision file, or
verification flags as inputs. The intended reviewer writes the decision in the
verifier's private run directory. This interface restriction is not an enforced
boundary against author-controlled code executing under the same verifier UID. Log content may become visible in the ledger only after approved
attachment; reviewers must not print credentials.

## Acceptance boundary

Automated tests use temporary ledgers and mock account lookup, reviewer execution
and/or attachment. They cover freshness, identity, protected decision paths,
rejection/failure/timeouts, fixed argv, confirmation cancellation and report
semantics. They do not establish GUI askpass success, real cross-UID filesystem
access, provider authentication, model judgment, or a live verifier attachment.
The owner separately confirms that the GUI popup worked in the reported launch;
reviewer execution then failed on missing `openai-codex` authentication. That is
not end-to-end provider-authenticated acceptance and does not exercise this helper
by itself. Remaining live acceptance is deferred to an explicitly authorized
post-release run; implementation does not silently close that gate.
