# Repository Guide Workflow Spec

Status: EXPERIMENTAL. Written 2026-08-15 after `OPENCODE-INIT-001` exposed a
nested-workspace targeting failure in OpenCode's `/init` adapter.

## Purpose

Repository scanning is a basic, useful LLM task: inspect a workspace and produce or improve
the `AGENTS.md` that future agents will inherit. The output is also unusually high leverage.
A plausible guide written for the wrong directory can silently redirect every later session.

This workflow makes repository-guide generation a governed Operator task. The model authors a
candidate; deterministic checks establish where it was allowed to read and write; an independent
review decides whether the candidate becomes accepted instruction. A model's completion message is
narration, not evidence that the requested file exists or that it describes the intended workspace.

## Boundary contract

The Product Behavior Contract supplies the upper boundary:

- the exact workspace to inspect;
- the exact output path;
- the allowed read and write sets;
- whether an existing guide may be replaced; and
- the commands, if any, that may be run as validation.

The Operator ledger is the enforcement middle. It records assignment, session provenance,
candidate evidence, review, and acceptance. The lower boundary is filesystem and VCS evidence:
resolved paths, hashes, diffs, command results, and source references. Agent prose, `/init` output,
crystals, and completion summaries remain untrusted narration until checked against that evidence.

## Target resolution

Every run has one canonical `workspace_realpath` and one canonical `output_realpath`.

1. An explicit workspace argument wins.
2. Otherwise use the harness session's active directory.
3. A discovered VCS root is context only. It must never replace the active directory implicitly.
4. Unless the contract names another file, `output_realpath` must equal
   `workspace_realpath/AGENTS.md`.
5. Resolve symlinks before dispatch. Reject a missing workspace, an output outside the allowed
   write set, or an output whose parent escapes through a symlink.

A nested project is therefore a first-class target. If the session directory is
`/repo/component`, finding `/repo/.git` does not authorize reading all of `/repo` or writing
`/repo/AGENTS.md`.

## Run manifest

Record this immutable manifest before model dispatch:

```yaml
workflow: repo-guide-v1
task_id: task-0001
workspace_realpath: /absolute/path/to/component
output_realpath: /absolute/path/to/component/AGENTS.md
vcs_root_realpath: /absolute/path/to/repo  # optional context
allowed_reads:
  - /absolute/path/to/component
allowed_writes:
  - /absolute/path/to/component/AGENTS.md
assigned_harness: opencode-local-a
review_harness: opencode-local-b
source_revision: <commit-or-null>
prompt_digest: <sha256>
```

Harness names identify peers and provenance, not rank. `assigned_harness` and `review_harness`
should differ. A frontier seat may author directly, but it is still subject to the same path and
evidence checks.

## Workflow

### 1. Prepare

- Resolve and record the manifest paths.
- Capture the pre-run status and output-file hash or absence.
- Create the Operator task and start a lane-tagged session.
- Give the author a plan-shaped prompt naming the exact output path and bounded read/write sets.

### 2. Draft

The author scans only the allowed read set and writes only the declared output. It should prefer
commands and conventions verified from repository files over generic advice. It must not run commands
merely because a repository document mentions them.

Two-author mode may collect candidates in isolated disposable copies. Candidates do not write the
accepted path concurrently; the reviewer merges or selects them after comparison.

### 3. Check

Before semantic review, collect deterministic evidence:

- the output exists at the exact resolved path;
- no undeclared path was changed by the run;
- every concrete repository path named in the guide exists, unless clearly marked as an example;
- claimed commands are present in repository configuration or documentation; and
- the resulting diff contains no secrets, local runtime ledger state, or generated bulk data.

A model saying that it wrote the file is not a substitute for these checks. Wrong-target output is a
hard failure even when its contents are otherwise good.

### 4. Review

The reviewer receives the manifest, candidate diff, deterministic check results, and a compact source
index. Review checks accuracy, omission of high-signal instructions, contradictions with inherited
guides, and accidental promotion of guesses into rules. Failures return to Draft with a specific
finding; the author does not self-verify.

### 5. Accept

Acceptance requires the exact-path check, declared-write check, and semantic review to pass. Attach
the diff and re-runnable checks as Operator evidence, then transition the task under the normal
identity and verification rules. A completion summary may report the result, but it cannot create the
accepted state itself.

## OpenCode `/init` adapter

OpenCode's adapter must:

- substitute the active session directory into the `/init` prompt;
- state the exact `${directory}/AGENTS.md` output path;
- explicitly forbid creating or updating an `AGENTS.md` outside that directory;
- retain the VCS root only as optional context; and
- have a regression test where `directory` is nested below `worktree`.

The regression passes only when the rendered prompt names the nested output and does not name the
parent guide as its target.

## Thin implementation and dogfood

The first implementation should compose existing `task-create`, `session-start`, evidence, review,
and transition surfaces rather than adding a new Operator subcommand. Automate it only after repeated
runs stabilize the manifest and checks.

Dogfood runs use a disposable nested Git repository containing small, inspectable configuration and
source files. A passing run must show:

1. `/init` targets the nested workspace;
2. only the nested `AGENTS.md` is created or changed;
3. deterministic checks agree with the model's claims;
4. review evidence is recorded separately from authorship; and
5. the run can be reproduced from the recorded prompt and manifest.

## Non-goals

- Trusting a guide because it sounds repository-specific.
- Treating Git-root discovery as workspace authorization.
- Letting a model approve its own output.
- Executing arbitrary commands extracted from the generated guide.
- Replacing repository-specific inherited instructions or the canonical BT/PBC/Logbook taxonomy.

## First dogfood result (2026-08-15)

The first disposable run used `ollama/gemma4:26b` through the patched OpenCode `/init` command. The
active directory was `/tmp/operator-repo-guide-dogfood-20260815/component`, nested beneath the Git
worktree `/tmp/operator-repo-guide-dogfood-20260815` and beside a parent `AGENTS.md` distractor.

The run passed the path boundary:

- OpenCode inspected the child `README.md`, `pyproject.toml`, source, and test files;
- it created only `component/AGENTS.md` outside Operator runtime state;
- the parent guide's SHA-256 remained
  `2c7117f94d8e52c796870af2e5bc9c58c49abe5c400a39943a42e932a5daabeb`; and
- the generated guide's `python -m unittest discover -s tests` command passed one test.

Operator task `repo-guide-dogfood` recorded the manifest, generated guide, two verified claims, and
independent check report. Verification was advisory because the disposable ledger used single-user
identity; it does not demonstrate `uid_isolated` review. The run also exposed a manifest-shaping
detail: `test_passes --gate` is an artifact path, not a prose success condition. The original prose
gate was superseded by a claim naming `tests/test_widget.py`; `doctor` then reported only non-fatal
advisory/superseded-record warnings.
