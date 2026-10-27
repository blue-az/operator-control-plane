# Repository evaluation request — Operator Control Plane

**Status:** preparation instructions; no external review requested or completed.

## Purpose

Request an independent, repository-level evaluation of `operator-control-plane` as a standalone, domain-neutral support/control plane. The evaluation should assess whether the repository's code, tests, documentation, security boundaries, and stated capabilities support its claims; identify concrete defects and important gaps; and distinguish verified behavior from design intent or historical evidence.

This is not an evaluation of Bulkhead Tau or another consumer, a model benchmark, a Pi-alpha-only release audit, or permission to run deployments or privileged operations.

## Freeze the review target first

The current worktree may contain unrelated or in-progress changes. Before inviting a reviewer:

1. Decide which changes belong in the review. In particular, explicitly include or exclude the edits to `evals/local_lane_ladder/COMPARISON_FIELD_PLAN_20261001.md`, `evals/local_lane_ladder/comparison_preflight.py`, `evals/local_lane_ladder/test_comparison_preflight.py`, `evals/local_lane_ladder/SCREENING_PROTOCOL.md`, and `docs/reviews/`.
2. Do not include `.operator/`, credentials, private transcripts, generated/local evaluation runs, or other machine-local state in the review packet. Do not commit local ledger data.
3. Produce a reviewable commit or immutable source archive and record its full Git commit ID (and archive digest if applicable). A branch name or moving worktree is not a frozen target. Record `git status` and the exact included paths.
4. Attach the target identity and review request to an Operator task. If the worktree is dirty, describe the included diff and provide the reviewer a bundle/snapshot that exactly corresponds to it; do not imply HEAD contains uncommitted work.

No commit, tag, push, publication, privileged command, or reviewer launch is authorized by this document.

## Track the review in Operator

Use a dedicated Operator task in the intended ledger. `operator init` creates local state; do not initialize a ledger in this repository merely to make the review appear tracked. Confirm the target ledger and identity mode before writing. In `single_user` mode any recorded verification is advisory, not independent.

Suggested sequence (adapt flags to the installed CLI's `--help`):

1. `task-create` with an objective naming the repository evaluation and frozen commit/snapshot.
2. Add separate, checkable claims for (a) review packet identity/scope, (b) deterministic checks actually run and their outcomes, and (c) the evaluator's findings and disposition. Do not make one blanket claim that the repository is "safe" or "fully evaluated."
3. Attach the request, snapshot manifest/diff, test logs, and final evaluator report as draft evidence. Record hashes and paths/URLs so the artifacts can be inspected. Keep the reviewer’s report separate from author summaries.
4. Route/request the evaluation from a distinct reviewer identity. Share the exact frozen snapshot, review question, scope, constraints, and evidence. Do not ask the reviewer to certify claims outside the evidence they inspect.
5. The reviewer returns findings with severity, file/line references, impact, reproduction or reasoning, and recommended disposition. Preserve disagreements and unresolved items; do not silently rewrite the report into consensus.
6. A distinct verifier independently checks the relevant evidence and records verification through Operator. `doctor` checks ledger consistency; it does not run stored verification commands or establish that a review was technically correct. Session/harness labels alone do not prove independent identity.
7. Close out with findings, accepted/deferred/rejected actions and rationale, remaining risks, exact reviewed snapshot, and whether follow-up changes received a separate review.

Operator command options and identity prerequisites are version-dependent. Check `./operator --help`, command-specific help, and the applicable identity/evidence specifications. Do not copy placeholder reviewer IDs or assume `review-delegate` supports arbitrary external reviewers.

## Proposed evaluation scope

Supplementary Pi-extension context: the externally hosted [Pi extension project board](https://bulkheadtau.com/bulkhead-tau/reflect/operator-boards/pi-operator-extension.html). Ask the evaluator to compare its depiction with the extension's documented and implemented behavior, and flag material discrepancies. Treat the page as an external, potentially version-skewed presentation—not as repository source, proof of implementation, or authority for Operator architecture. Operator remains standalone; Bulkhead Tau is an external consumer/context.

Ask for a broad but bounded source-based evaluation of:

- Core purpose, standalone boundary, architecture, and whether README/spec claims match implementation.
- Security and integrity boundaries: identity and verifier separation, evidence/ledger tamper assumptions, fail-closed behavior, filesystem/process/network boundaries, and privileged broker/admin paths.
- Correctness and maintainability of key CLI, broker/admin, projection, evidence, and runner workflows; focus on concrete high-impact risks rather than style preferences.
- Test coverage and reproducibility. Separate tests actually executed from static inspection, and report environment limitations or skipped tests.
- Operational/documentation usability, supported-runtime claims, failure/recovery behavior, and known limitations.
- Repository hygiene and reviewability, including generated/private data and mixed-purpose evaluation material.

Request an explicit coverage statement and findings categorized as **blocker/critical**, **high**, **medium**, **low**, or **observation**. For each finding request location, impact, evidence, confidence, and a minimal remediation. Ask the reviewer to identify areas not reviewed. No finding is implied merely because a feature is absent unless the reviewer explains why that absence violates a stated requirement.

## Execution boundaries

The initial review may be static and read-only. Do not grant access to secrets or private `.operator/` state. Tests may be run only on a clean, disposable checkout with dependencies installed and an agreed command list. No production service, real ledger, model inference, network deployment, account/policy mutation, `sudo`, or credential access is part of this request. A reviewer must request separate authorization before any such action.

## Completion criteria

The evaluation is ready to close when the exact snapshot is bound to the Operator task; the reviewer has returned a scoped report; actual test execution and static-review coverage are distinguished; findings and owner dispositions are recorded; and a distinct verifier has assessed the evidence at the identity level available. This records an evaluation—it does not guarantee absence of defects, security certification, or deployment approval.
