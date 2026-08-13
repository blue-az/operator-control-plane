"""Alignerr-derived trajectory scoring for the local-lane ladder.

GOLD_STANDARD.md composes two golds: Alignerr DocAI for the *trust* axis (how an
answer becomes trusted) and L0/L1/L2 for the *complexity* axis. The complexity
axis has been operational since the ladder existed. This makes the trust axis
operational too, instead of aspirational.

**The postcondition remains the sole gate.** Nothing here can pass or fail a
cell. A trajectory score is reported beside pass/fail and answers a different
question: not "did it get there" but "did it get there the way a reproducible
process requires". A model can pass with a poor trajectory (lucky blind patch)
or fail with an excellent one (did everything right, got the logic wrong), and
both of those are worth seeing.

Rules transferred from `~/Alignerr/batch4_authoritative_guidelines.md`. The
source is a DocAI verification task, so each rule is mapped rather than copied:

| Alignerr rule (verbatim)                              | Local equivalent               |
|-------------------------------------------------------|--------------------------------|
| "Use at least three steps"                             | >= 3 tool calls                |
| "Each step describes exactly one action. Do not        | no compound call               |
|  combine scanning/searching and extraction in one step"|                                |
| "The correct answer must require at least two PDFs"    | read every declared source     |
| "Do not use PDF text search as the source of truth"    | read the file before patching  |
| "explicitly name the rejected candidates and explain   | failed calls retained, not     |
|  why each was dropped"                                 | silently repeated              |
| "no omissions and no extras"                           | R6 scope (graded separately)   |

The last column is scored from the `trajectory` object the runner already
records, so this runs over traces that have already been captured -- no re-run.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Tools that change state. Mirrors opr's own terminal_tools set.
_WRITE_TOOLS = {"write_file", "patch_file", "run_command"}
_READ_TOOLS = {"read_file", "grep_search", "list_dir", "tree_dir"}


@dataclass
class TrajectoryScore:
    score: float
    rules: dict[str, bool | None] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def applicable(self) -> int:
        return sum(1 for v in self.rules.values() if v is not None)

    @property
    def satisfied(self) -> int:
        return sum(1 for v in self.rules.values() if v is True)


def score_trajectory(trajectory: dict, task: dict) -> TrajectoryScore:
    """Score one cell's trajectory against the transferred Alignerr rules.

    A rule that does not apply to a task scores None rather than False -- a
    single-file fixture cannot violate "read every declared source", and
    counting it as a failure would penalise the task author's choice rather
    than the model's behaviour.
    """
    calls = trajectory.get("tool_calls", [])
    writes = [c for c in calls if c["tool"] in _WRITE_TOOLS]
    reads = [c for c in calls if c["tool"] in _READ_TOOLS]
    read_paths = {c["path"] for c in reads if c["path"]}
    declared = set(task.get("files", {}))
    rules: dict[str, bool | None] = {}
    notes: list[str] = []

    # "Use at least three steps." Only meaningful once a task genuinely needs
    # several actions; a one-line edit legitimately takes read + patch.
    budget = task.get("state_changes") or 1
    if budget > 1:
        rules["min_steps"] = len(calls) >= 3
        if not rules["min_steps"]:
            notes.append(f"only {len(calls)} call(s) for a {budget}-state-change task")
    else:
        rules["min_steps"] = None

    # "Do not use PDF text search as the source of truth" -> do not patch a
    # file you never read. This is the anti-anchoring rule from Batch 5: derive
    # from the source rather than from what you assume is there.
    blind = [w for w in writes if w["tool"] == "patch_file" and w["path"] not in read_paths]
    if writes:
        rules["read_before_write"] = not blind
        if blind:
            notes.append(f"patched without reading: {sorted({w['path'] for w in blind})}")
    else:
        rules["read_before_write"] = None

    # "The correct answer must require at least two PDFs" -> a multi-source task
    # must consult every source it declares before being credited with process.
    sources = {p for p in declared if not p.startswith("tests/")}
    if len(sources) > 1:
        missed = sorted(sources - read_paths)
        rules["all_sources_read"] = not missed
        if missed:
            notes.append(f"never read: {missed}")
    else:
        rules["all_sources_read"] = None

    # "explicitly name the rejected candidates" -> a wrong attempt is evidence
    # and must remain visible. Re-issuing an identical call instead of adapting
    # is the local form of discarding a candidate without a reason.
    rules["no_blind_repeat"] = not trajectory.get("stopped_repeat", False)
    if trajectory.get("stopped_repeat"):
        notes.append("re-issued an identical call until the guard stopped it")

    # "Each step describes exactly one action." opr dispatches one tool per
    # call by construction, so this can only fail by emitting output the
    # harness could not dispatch at all.
    rules["single_action_steps"] = not trajectory.get("no_dispatch", False)
    if trajectory.get("no_dispatch"):
        notes.append("emitted tool-shaped output that did not dispatch")

    applicable = [v for v in rules.values() if v is not None]
    score = (sum(1 for v in applicable if v) / len(applicable)) if applicable else 1.0
    return TrajectoryScore(round(score, 3), rules, notes)


# Failure taxonomy. Alignerr's failure catalog exists to record *the harness's*
# mistakes rather than the thing under test, and this programme has now found
# six harness confounds that first presented as model failures. Classifying
# every failure keeps infrastructure out of the model's score by construction.
def classify_failure(record: dict, trajectory: dict, stdout: str = "") -> str:
    """Classify a failed cell so infrastructure never lands in a model's score.

    Infrastructure evidence comes from `stdout` -- what the harness itself
    reported -- and never from the grader's `detail`. The detail string
    describes the postcondition, and postcondition text quotes fixture content,
    so matching infrastructure words against it is a false-positive generator:
    an early version keyed on "connection" and classified all 19
    `ambiguous-anchor` failures as INFRA, because that fixture's runbook says
    "Drain connections." They were ordinary model failures.
    """
    detail = (record.get("detail") or "").lower()
    if record.get("detail", "").startswith("timed out"):
        return "TIMEOUT"
    # opr emits this exact prefix when the model server call fails.
    if "ollama api error" in stdout.lower():
        return "INFRA"
    if record.get("returncode") not in (0, None):
        return "SERVING_INCOMPATIBLE"
    if trajectory.get("no_dispatch"):
        return "HARNESS_PROTOCOL"
    if "timed out" in detail and "command timed out" in detail:
        # The postcondition's own command exceeded its budget, which is a
        # property of the fixture and the model's output, not of the server.
        return "MODEL_FAILURE"
    return "MODEL_FAILURE"
