# Review request: frozen-scope Operator Pi alpha

## Owner intent

Prepare a small-audience Git-distributed `v0.1.0-alpha.1` release. Stop feature
expansion. Sequence: scope freeze → bounded source/package audit → release →
validate the exact released version. This is not authorization to publish, tag,
commit, run privileged commands, or start model reviews automatically.

The owner reports prior feature validation, with crystal workflows still pending.
Do not repeat validation or invent new acceptance gates. Existing automated test
results are supporting history, not a claim of live cross-UID/provider acceptance.

## Material to review

At request creation, HEAD was `1567d3ece3420963fb49bbe40ec47077d4a615f7`.
The implementation includes **uncommitted changes and untracked files**. Review
this scoped worktree, not HEAD alone. This request is not an immutable release
snapshot; the eventual release must bind the reviewed content to a commit/tag.

- `.pi/extensions/operator/` — include `workflows/{commands,targets,verify}.ts`
- `scripts/install-operator-extension.py`
- `scripts/pbc_validate_operator.py`, `scripts/poe_fut014_audit.py`
- `scripts/operator_verify_run.py`
- `docs/specs/VERIFY_RUN_SPEC.md`
- `owners-manual/pbc/appendix-pi-operator-extension.pbc.md`
- `tests/test_pi_operator_extension.py`, `tests/test_install_operator_extension.py`
- `tests/test_operator_verify_run.py`
- `tests/pi_operator_{workflows,targets,verify}.ts`
- Relevant Operator identity/evidence/review-delegation backend code, when needed
  to check a specific integration boundary. Do not expand into a repo-wide audit.

At initial review no package manifest existed. The bounded follow-up now proposes
`package.json`, `.gitignore` exclusions and `docs/releases/pi-operator-0.1.0-alpha.1.md`;
include these plus the root README pointer in the release diff. MIT licensing is
present. Ledger state, crystals, transcripts, credentials, evaluation data and
unrelated worktree changes are not packed frontend payload. Git distribution also
requires review of the actual tagged tree: npm's allowlist does not filter a clone.
Do not inspect private auth files or unrelated session logs.

## Proposed release boundary: core plus optional capabilities

Core: local task/status orientation, task selection, claim/evidence/handoff
shortcuts and their confirmation/provenance boundaries. Operator remains a
separately installed control plane, not bundled runtime ledger state.

Optional capabilities:

- Delegation, target registry editing and model-based supervisor review: require
  configured harnesses/carriers/models. External Claude may perform review for
  now; in-extension launching is not a prerequisite to the release audit.
- PBC validation/draft authoring: requires the pinned validator and wrapper.
- Crystal capture/attach/import: capture requires supported crystallize CLI;
  owner validation is deferred until after release.
- GUI authorization and trusted verifier execution: require a configured distinct
  Unix verifier, enforced policy, askpass and verifier-side provider authentication.

Review whether this split is accurately communicated and optional dependencies
fail locally without preventing core use. Do not add a plugin framework, settings
wizard, new integrations or more features to achieve it. Recommend a small gating
or documentation change only when needed for a concrete release blocker.

## Known live-launch incident (owner supplied)

An `/op:popup` attempt for `review-claim-0182-2026-09-22T042134Z0000` reported:

- `ksshaskpass: Unable to parse phrase "[sudo] password for blueaz: "`
- Pi warned that session `claude-supervisor-claim-0182` did not exist and would
  be created.
- Pi reported `No API key found for openai-codex`.
- `/op:popup` reported sudo exit 1.

The owner confirms the GUI popup worked correctly; the failure occurred during
reviewer execution, not authorization UI. The shown invocation used
`sudo -A -u operator-verifier bash -lc ...`. This is the existing popup path, not
evidence that the new `/op:verify-run` helper was exercised. Pi was reached, but
the selected provider lacked usable authentication in that launch environment.
The askpass warning is not evidence of popup failure. No completed review or
verification verdict is established. The reviewer label alone does not establish
intended provider.

The owner called this **involuntary validation**. Do not retry it, log in, copy
credentials, change provider routing, alter sudo/account configuration, or launch
another workflow. Treat it as a known optional-review setup limitation and inspect
whether errors/preconditions are documented honestly. External review is an
acceptable temporary workflow; do not turn authentication repair into release scope.

## Audit only — no execution validation

Allowed: source/document reading, scoped Git inspection, static inspection of
package metadata/payload lists and dependency/configuration boundaries.

Not requested: tests, smoke runs, installation, `/op:popup`, `/op:verify-run`,
reviewer/model launches, `sudo`, stored verification commands, credential access,
account/policy changes, or external publication. If a question cannot be answered
statically, mark it **post-release validation needed**, rather than executing it.

Inspect only:

1. Release payload completeness and exclusion of private/local runtime artifacts.
2. Entry point, peer/runtime dependencies, backend version/installation contract,
   host-specific paths, and behavior when optional dependencies are absent.
3. Confirmation/cancellation, explicit task/session provenance, fixed argv,
   filesystem write boundaries, and privileged-run identity/decision boundaries.
4. Documentation versus actual behavior, especially experimental/optional status
   and the distinction between process success, model approval and verification.

The distinct-UID reviewer is not an OS sandbox. Input hashes establish freshness,
not code signing. Inspect whether the implementation/docs overstate protection;
do not assume separate UID alone proves semantic correctness or malicious-code
isolation. External Claude's audit likewise is not automatically Operator
UID-isolated verification and must not mark claims verified.

## Bounded follow-up for supervisor disposition

Implementation-side edits are ready for static review, not claimed accepted:

- **B1:** explicit frontend `files` list and Pi entry point in `package.json`;
  Git-first alpha marked private against accidental npm publication. Crystal and
  transient registry files are ignored. Release notes distinguish packed payload
  from the whole tracked Git tree; no archive or install was exercised.
- **B2:** `/op:popup` confirmation requests full, shell-quoted argv. The existing
  abbreviated format remains only for compact reports. Regression assertions
  were added to the selftest source but not executed in this pass.
- **B3:** both authorization dialogs, extension README and verifier spec disclose
  author-writable code running with verifier permissions/credentials. The decision
  file gate is the helper's intended path, not an enforcement boundary against
  that code. Hashes establish freshness, and UID records do not prove independent
  judgment. `/op:verify-run` is labeled experimental.
- Release wording covers core/optional scope, provider fallback, weak auth
  preflight, declared compatibility target/minimum Node, and the host-specific
  PBC path override. Pi 0.87.1 was observed in package metadata; no fresh runtime
  compatibility result is claimed.
- The PBC's prose now reflects owner-confirmed popup success. Its historical
  popup task was inspected read-only and still says assigned with empty
  claims/evidence; no ledger status was changed. Fenced contract blocks were not
  rewritten for this follow-up.

No tests, workflow validation, dependency installation, privileged/model launch,
credential repair, commit, tag or publication was run for this follow-up. The
supervisor should inspect the source/payload intent only and identify any remaining
concrete blocker before the owner decides how to commit/tag/distribute.

## Requested result

Provide a short report with file/line references and three buckets:

- **Blocker:** concrete disclosure/security/correctness/packaging defect that must
  be fixed or excluded before this small-audience alpha.
- **Release note / optional prerequisite:** document it; does not block core alpha.
- **After release:** validation and nonessential improvements, including crystals.

State coverage and uncertainties. Do not turn suggestions into requirements or
reopen the feature backlog. Recommend the smallest safe release, not more scope.
Only a concrete release blocker reopens frozen implementation; fixes must be
scoped and reviewed separately. A scoped commit/tag and packaging work are still
needed before any publication.
