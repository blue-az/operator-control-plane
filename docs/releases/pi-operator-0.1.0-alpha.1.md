# Pi Operator 0.1.0-alpha.1 — release preparation

**Not yet tagged, published or independently accepted.** Small-audience Git alpha;
no more feature expansion. Scope freeze → bounded source/package audit → release
→ validate the exact released version. This document is not permission to execute
review workflows, install software, change credentials, commit, tag or publish.

## Boundary

The package is the Pi frontend, not a bundled Operator service/ledger. Core means
local doctor/status/tasks, task selection and confirmed claim/evidence/handoff
shortcuts. Repo-specific next-step/roadmap orientation also needs the PBC appendix
in the separate control-plane checkout. The original ladder's first four steps
are implemented; that is not completed dogfood or independent acceptance.

Optional capabilities remain optional: configured delegation/target editing,
model-based reviews, PBC drafts/validation, crystal workflows and experimental
GUI/UID review launchers. They are commands in one extension, not independently
loadable plugins. No new plugin framework or setup wizard is part of this alpha.

## Package payload (B1)

`package.json` is the package manifest. Its `files` field is the intended packed
frontend allowlist, enumerated here for static review:

```text
package.json                         # npm includes this automatically
LICENSE
README.md                            # repository/backend overview
.pi/extensions/operator/index.ts
.pi/extensions/operator/core.ts
.pi/extensions/operator/client.ts
.pi/extensions/operator/render.ts
.pi/extensions/operator/targets.json
.pi/extensions/operator/orientation/actions.ts
.pi/extensions/operator/workflows/commands.ts
.pi/extensions/operator/workflows/targets.ts
.pi/extensions/operator/workflows/verify.ts
.pi/extensions/operator/README.md     # frontend setup, commands and limitations
.pi/extensions/operator/install-guide.md
docs/releases/pi-operator-0.1.0-alpha.1.md
docs/specs/VERIFY_RUN_SPEC.md
```

No build, prepare, install or publish lifecycle scripts are declared.
Pi provides the two declared peer packages; they are not bundled. `private: true`
prevents accidental npm publishing and does not prevent local/Git consumption.
There is no npm release in this scope.

Excluded from the packed frontend: `.operator/`, `.agent-crystals/`, credentials,
local ledger contracts/settings, transcripts, generated boards, evaluation data,
tests, selftests, Python backend executables and unrelated worktree changes.
`.agent-crystals/` is now ignored at every directory depth. Ignore rules do not
remove files already tracked; tracked-tree inspection remains necessary.

**Git is different:** npm's `files` list does not restrict what a Git clone
contains. An alpha tag in the existing source repository includes its whole
tracked tree (and the repository contains prior history), not just this frontend
allowlist. Before sharing a Git source, the supervisor/owner must inspect the
actual candidate tree and approve that boundary. If only the listed frontend
files should be distributed, use a separate distribution repository containing
that payload. Do not mistake `private: true` for repository access control.
No package archive, installation, or tagged-tree acceptance was run in this pass.

**Decision (2026-09-23):** the owner chose to tag the existing public source
repository (`blue-az/operator-control-plane`); no separate distribution repository.
Recipients of the tag get the whole tracked tree, which is already public.

## Prerequisites and versions

- Compatibility target: **Pi 0.87.1**, observed in the installed package metadata
  during static release preparation. This is not a fresh validation result.
- Node: **>=22.19.0**, matching that Pi version's minimum. Earlier local test output
  recorded **22.22.2**; no release compatibility matrix is claimed.
- Pi peer ranges are `*`, following Pi package conventions. This is not a promise
  of compatibility with all Pi releases. Prefer the stated target for the alpha.
- Backend: separate Operator checkout from the same supervisor-approved source
  revision as this release, Python **>=3.12**, PyYAML, and an intended local ledger.
  The backend revision cannot be pinned until the scoped release commit exists;
  record that exact revision with the tag. Do not point at a moving worktree.
- PBC commands additionally require the pinned `pbc-spec` checkout/build used by
  `scripts/pbc_validate_operator.py` and `scripts/poe_fut014_audit.py` (commit
  `ca97caf63329cee5ecf2b92dfe1120374ab90a81`). Set `POE_FUT014_PBC_SPEC` explicitly;
  `/home/blueaz/Python/Evaluation/pbc-spec` is a legacy host-specific fallback.
- Crystal capture additionally requires installed
  `@stewie-sh/agent-crystallize@0.1.16`; configure `OPERATOR_CRYSTALLIZE_PACKAGE`
  if installed discovery does not find it. There is no automatic download.
  Attach/import use the Operator backend. Owner crystal validation is deferred.
- Review/delegation require configured harnesses, models, carriers and provider
  authentication. UID review launchers additionally require Unix/sudo/GUI askpass,
  an enforced verifier policy and appropriate account/filesystem permissions.

## Setup contract for recipients (after release, not executed now)

1. Obtain the separately versioned control-plane checkout and configure its ledger
   in the intended workspace. Do not ship or clone the author's `.operator/`.
2. Install **one** frontend: either the existing copy/link helper or the Pi package.
   Do not load both copies in the same project. The helper is not the package
   installer and does not publish anything.
3. In package mode, a consumer without its own control-plane sibling pair needs
   `.pi/operator-ledger.json`, for example:

   ```json
   {
     "schema": "operator-pi-extension-ledger-contract/v1",
     "ledger_root": "/absolute/path/to/operator-control-plane"
   }
   ```

   The referenced root must contain both `.operator/` and the `operator` file.
   This manual contract is not an installer ownership record; do not use the
   copy/link helper's uninstall command to remove a package installation.
4. A project-local Pi package/trusted resources still require the human's project
   trust decision. No installer changes trust or verifier/sudo policy implicitly.
5. Configure only the optional capabilities you intend to use. Declining to set up
   provider authentication must not be treated as failure of core ledger features.

Future Git installation uses
`pi install --local git:github.com/blue-az/operator-control-plane@TAG` once the
owner approves and creates the tag. Until then no released version exists. Package removal is through
Pi; separately managed ledgers and manual configuration are not deleted for you.

## Privileged review disclosures (B2/B3)

- Popup authorization now displays the **complete shell-quoted argv**, not the
  compact 72-character transcript summary. Compact reports may still shorten it.
- `/op:verify-run` is explicitly **experimental** in command help and confirmation.
  Its intended helper path requires a reviewer decision before attaching a log.
- The helper, Operator CLI and verification command execute from an
  **author-writable checkout** with the verifier's permissions and credentials.
  Author-controlled code can write verifier evidence without following the
  helper's decision-file path. This is not an OS sandbox or author-code isolation.
- Input hashes establish freshness since confirmation, not trustworthy code or
  independent judgment. `uid_isolated` records a distinct executing UID; it does
  not prove independence from author code or semantic correctness of the review.
- The slash interface exposes no verdict/status parameters. That restriction is
  not an enforcement boundary against code already running as the verifier.
- The legacy review launcher chooses an explicit model, then configured harness
  model, then persona defaults. Unrecognized/placeholder-only reviewer labels can
  silently fall back to `openai-codex/gpt-5.6-luna`; a Claude-shaped label alone is
  not an Anthropic provider selection. Inspect actual bundle/provider/model.
- Legacy auth preflight only checks readable `auth.json` or a nonempty mapped
  environment value. It does not authenticate to the selected provider or check
  credential validity/expiry. No credential copying or routing repair is included.

## Known incident and validation status

The owner confirms that the GUI askpass popup **worked**. The reported launch for
claim-0182 reached Pi and failed on missing `openai-codex` authentication. The
askpass warning is not evidence of popup failure. This was the `/op:popup` path,
not demonstrated execution of the new `/op:verify-run` helper and not completed
end-to-end verification. External Claude source review is an acceptable temporary
route; its output is not automatically Operator UID-isolated verification.

The owner reports previous feature validation, with crystals still pending.
Existing automated results remain historical evidence, not acceptance of these
release-preparation edits. No tests, workflow validation, package installation,
privileged launch, model call, credential change or publication was performed
for this pass. B2 has source-level regression assertions added but not executed.

## Supervisor handoff

Review only the bounded B1–B3 patch, documentation accuracy and intended payload.
Report concrete blockers separately from optional prerequisites and post-release
validation. Do not reopen the feature backlog or retry the failed reviewer setup.
The scope and permissions are in `docs/REVIEW_REQUEST_pi-operator-alpha.md`.

Still required before publication: supervisor disposition, a scoped commit
including all intended new files, approved Git distribution/tree boundary, exact
backend revision, and an owner-authorized immutable tag. No claim is made that
adding this manifest completed those steps. Validate crystals and other explicitly
deferred workflows **against that released version**, not by moving the freeze.
