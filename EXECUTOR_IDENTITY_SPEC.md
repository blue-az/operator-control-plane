# Operator Executor Identity and UID Isolation

This spec defines the authority boundary for claim authorship and verification. The CLI consumes an
OS isolation boundary; it does not create one.

## Authority Rule

A verification is trusted as `uid_isolated` only when all of these are true:

1. `.operator/identity.yaml` uses `mode: enforced`.
2. The claim records its author from `os.getuid()` and `pwd.getpwuid()`.
3. The executing verifier UID is registered with the `verifier` role.
4. The verifier UID differs from the claim author's UID.

Names, harness assignments, environment variables, and role labels do not create isolation. Agents
running as the same OS UID cannot be meaningfully isolated by this CLI. In `single_user` mode,
verification remains usable but is always `advisory`.

## Identity Registry

The structured registry is:

```yaml
mode: enforced
uids:
  1001:
    name: codex
    roles: [builder]
  1002:
    name: claude
    roles: [verifier]
```

Valid roles are `builder` and `verifier`. A UID may hold both roles, but it still cannot verify its
own claim. For compatibility, a scalar entry such as `1001: codex` is normalized to the name
`codex` with both roles. Missing configuration defaults to `single_user`. Malformed configuration
fails role-gated writes and is an error in `doctor`.

## Recorded Fields

Claim creation records both the compatibility `executor` field and explicit authorship context:

```yaml
author_executor:
  uid: 1001
  user: builder-user
```

A status-bearing evidence attachment records:

```yaml
verification_executor:
  uid: 1002
  user: verifier-user
verification_authority: uid_isolated  # or advisory
verification_mode: enforced           # or single_user
```

The existing `executor`, `made_by`, `verified_by`, outcome, and status fields remain available for
compatibility. Verification does not overwrite `author_executor`. Legacy claims are never backfilled
or inferred from a harness name.

## Write Gates

In `mode: enforced`:

- `claim-add` requires a registered UID with the `builder` role.
- Status-free `evidence-attach` requires a registered UID with the `builder` role.
- Any status-bearing `evidence-attach` requires a registered UID with the `verifier` role.
- `--verified-by` is a required assertion and must equal the registered verifier name.
- A status write fails when the claim lacks a valid author UID or the verifier UID equals it.

Authorization completes before evidence fingerprinting or copying and before IDs, YAML projections,
SQLite events, or task/claim status are written.

In `single_user`, those workflows remain usable. Every status write records
`verification_authority: advisory`; it never records `uid_isolated`.

## Doctor

`doctor` is structural and read-only. It never executes `verification_command`.

- Valid distinct-UID verification is reported as `uid_isolated`.
- `advisory` verification is reported as a non-fatal warning.
- Legacy verified claims without the new fields are reported as legacy/advisory and remain readable.
- Malformed `uid_isolated` records are errors, including missing or equal UIDs, a recorded mode other
  than `enforced`, an unregistered verifier UID, a missing verifier role, or a `verified_by` mismatch.
- Guarded test-UID markers are errors and are not proof of real UID isolation.
- A later policy-mode change is visible but does not relabel the authority recorded on an event.

## Test Hook

`OPERATOR_TEST_UID` is honored only when `OPERATOR_TEST_SENTINEL` is `1` or `true`. Writes produced
through that guarded simulation record `test_override_active`; `doctor` treats them as test artifacts.
An override request without the sentinel records `test_override_unauthorized`, which is also an error.

Passing simulated-UID tests proves the gate logic, not real isolation. A real isolation claim requires
dogfood with genuinely distinct OS users and confirmation that the recorded author UID, verifier UID,
and SQLite event actor UID differ as expected.

## Out of Scope

- Provisioning OS users or containers
- Cryptographic keys or signatures
- Immutable policy or ledger configuration (P3)
- Semantic evidence judgment
- Executing stored verification commands
- Rooms, orchestration, or UI
