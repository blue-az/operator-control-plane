# Harness turn cost — anecdotes, not measurements

Backup data. Filed so a future investigation starts from a record instead of a
memory, and knows what to control for. **Nothing here is citable as a model
comparison.**

---

## 2026-08-15 — Antigravity CLI, Google free plan, one-word turn

Operator sent the single prompt `hello` to five model settings and read the
free-plan quota consumed by each.

| Model setting | Quota per `hello` |
|---|---:|
| GPT-OSS 120B (Medium) | **~0.1%** |
| Gemini 3.7 Flash (High) | <1% |
| Gemini 3.1 Pro (Low) | ~1% |
| Claude Sonnet 4.6 (Thinking) | ~5% |
| Claude Opus 4.6 (Thinking) | **~7%** |

### Why this is not a model comparison

**Reasoning mode varies across the rows and cannot be held constant.** The
settings are `(Thinking)`, `(Medium)`, `(Low)`, `(High)` — different reasoning
budgets, not one setting applied uniformly. The transcript shows the cost
directly: Gemini 3.1 Pro spent **485 thinking tokens** deciding how to answer
`hello`.

This is the same confound as `--think` in the local ladder, where uncontrolled
reasoning produced a 5–32x token spread and collapsed E4's 19x latency gap to
1.2x once pinned. The ~70x Opus-to-GPT-OSS ratio here is reasoning budget times
quota weighting, not model economics.

**Other limits, recorded so nobody re-derives them:**

- n=1 per setting.
- Gemini 3.7 Flash was measured in a **separate fresh session**, not by
  switching in place, so its accumulated context differs from the rest.
- "% of free plan" is a **quota unit**, weighted by Google's own pricing tiers.
  It is not tokens and not dollars.
- Antigravity's harness owns the reasoning mode; the operator cannot pin it.
  That is why this stays an anecdote rather than becoming an experiment.

### What it does support

Read as a **harness** observation rather than a model one, it is sound and
useful — and the harness-at-defaults question is the operationally relevant one,
since defaults are what actually gets paid:

> On agy's free plan at harness defaults, a trivial turn costs ~0.1% on GPT-OSS
> and ~7% on Opus.

No reasoning-mode claim attached. Order-of-magnitude gaps from n=1 are good
enough to route on; a 70x gap does not need a p-value to justify keeping
transcript chores off the expensive seat.

The routing consequence is real and currently unhandled: the policy in
`LOCAL_LANE_ROUTER_STUDY.md` gates `conversational` versus `delegated` on
**tok/s**, and has no notion of reasoning budget or quota cost per turn. A
one-word greeting costing 7% of a daily quota is a routing gap, not a model
property.

### What would make it an experiment

Only worth doing if the harness ever exposes the control:

1. Same prompt, same fresh-session state for every row.
2. Reasoning **off** on all of them, or pinned to one identical level.
3. n>=3.
4. Record the quota unit's definition, or convert to tokens via the harness log
   and use `usage-import`.

Until then it stays here.

---

## 2026-08-16 — Claude Code, accidental `/claude-api` in the logsum fixture

Operator meant to paste a Fable control task into a fresh session at
`/home/blueaz/Public/LinkedIn/fable-control/logsum`. Typed `/claude-api`
instead. Session `1b6c0f9e-b075-40aa-9c68-1a9288c3c820`. Interrupted at
`2026-08-16T19:33:27.648Z`. No files were edited. The fixture is still
`raise NotImplementedError`.

What the command actually did:

1. Loaded the bundled skill “Building LLM-Powered Applications with Claude.”
2. Wrote **372,998** tokens into a 1-hour cache on `claude-opus-5`.
3. Wrote **373,607** tokens again on `claude-fable-5`.
4. `ls`, `find`, then `Read` of `src/logsum.py` and `tests/check_logsum.py`.
5. Operator cancel.

The bill was about **$7**. Remaining usage limit showed **$0.75**. Extra
usage overflowed onto credit. Cancel stopped the turn, not the bill: cache
writes are charged when the request is accepted, not when the assistant
finishes. The $7 was the skill ingest, not any implementation work.

### Sonnet’s later read of the same session

Asked how close the cancelled turn was to “the end,” Sonnet scored the
28-line transcript as:

- “harmless — just skill context loaded and two files read”
- “under 10% in, still at the look-around phase”
- next step would have been asking what to build, not writing code
- “nothing consequential was skipped by cancelling”

That is true of **edits** and false of **spend**. There was no cheap “ask
what you wanted” left. The skill was already in context; every later turn
would have kept that cache hot. Left running, Fable would have drained the
account.

### Why this is not a model comparison

The intended logsum task never ran. This is not evidence that Fable cannot
implement `error_report`. It is not a Fable-vs-Sonnet quality result. It is
not a measurement of slash-command pricing in general — n=1, one skill, one
harness version (`2.1.233`), extra usage already enabled.

### What it does support

Read as a **harness** observation, it is the complement of the 2026-08-15
`hello` row:

> A one-token slash command can front-load hundreds of thousands of cache
> tokens onto the expensive seat. A remaining-limit readout of $0.75 is not
> a hard stop. Progress scored on file edits will call that “harmless”
> after the money is already gone.

Same routing hole as `ROUTING_COST_GAP_PLAN.md`: once the turn is on a
frontier seat, there is no cost gate, and cancel does not unwind ingest.

### What would make it an experiment

Only worth doing if the question is “how does slash-command ingest bill,”
not “can Fable write logsum”:

1. Same cwd, extra usage **off**, so leftover limit is a hard stop.
2. Same `/claude-api` vs a one-line paste that does not load a skill.
3. Record billed dollars and `cache_creation_input_tokens` from the
   session JSONL, not from the TUI remaining-limit line.
4. Do not leave the session running. The 2026-08-16 cancel is the stop
   condition.

Until then it stays here.

---

## 2026-08-20 — task shape, not task difficulty

One session delegated coding work to local models through the opencode harness. Each task was gated by a pytest suite written before the code. The work was split by task shape. Writing a new self-contained module passed 6 of 8. Editing an existing file across several sites passed 0 of 3. gemma4:26b, gemma4:31b and qwen3.8:27b each independently passed the same 14-test gate on a new-file task. The models agreed on the result. The two new-file failures were qwen3.8:27b hitting a timeout. The models did not produce wrong answers. Verification overhead was held constant across both shapes. The same gate was used. The same tests were used. Only the shape changed. Confounds: one session, no per-turn token accounting, and the supervisor was also the person reporting the result. This is an anecdote. It is not citable as a rate.

### Provenance of this entry

Drafted by `gemma4:26b` through opencode against a pytest gate written first,
which checked structural anchors, the voice-signature blocklist from
`AGENT_AUDIT_PROTOCOL.md`, and an allowlist of the only figures measured that
day. The number check is the load-bearing one: a paper arguing that unaudited
local output invents numbers should not accept a draft containing invented
numbers. Two gate defects were found by running it — model tags such as
`qwen3.8:27b` were parsed as numeric claims, and the length bound was missing
on this entry. Both were the supervisor's errors, not the model's.

---

## 2026-08-23 — gemma4:31b with git write, claim-state cleanup

This was an experiment: the human allowed `gemma4:31b` git write on
`operator-control-plane` and asked it to clean the dirty tree and stabilize
claim state. Default policy is the opposite. Local seats do not get git unless
that experiment is on. Do not cite this as a ranking of 31B against 26B or
against OpenCode.

### Why the task is hard

The tree was not “commit the one file you just edited.” It was several
unfinished concerns in one working copy: an in-progress `opr` → OpenCode
deprecation, untracked R6/R3 runners, fifty-plus eval fixtures, Operator
ahead of `origin` and behind it, and two copies of Paper 1.45 (Phoenix
manifest = source of truth, Operator markdown = a drifted working copy).
Lifecycle (`active draft` / frozen / published) is not verification. The
standing instruction on `local-model-task-fit-r3` was already **do not freeze
1.45**. The model also cannot reliably spell the word “claim” (it writes
“laim”), and had already produced a false Phoenix freeze (`ee9c5ce3`,
reverted `b7649920`) when given publication plus grid plus lifecycle in one
prompt.

Git write is how that class of failure stops being a recap and becomes an
object in the database. Collapsing history, setting `FROZEN (Published)`,
and leaving a test that cannot import the stub are all durable.

### Recap versus git

The recap said: history collapsed into three clean commits; claim lifecycle
aligned to Active Draft / private; repo cleaned; supervisor can freeze.

Git said:

- History was **not** collapsed. Reflog is three new commits on `747cf5e`,
  all timestamped `2026-08-23 16:20:34 -0700`: `73fcf61`, `2d74c45`,
  `e30cd83`. Branch remained ahead of origin and behind it.
- `73fcf61` is a grab-bag (opr stub, README/PBC, eval docs) and changed
  `EMPIRICAL_ANALYSIS_R1_R6.md` from `VERIFIED` to **`FROZEN (Published)`**.
  Phoenix 1.45 stayed `lifecycle: active draft`, `publish: false`.
- Commit subjects contain “laim”.
- `2d74c45` and `e30cd83` did land real untracked code: `gated_runner.py`,
  R6 tests, `r3_grid_comparison.py` (including `harness-r3`). Outcome JSON
  dirs stayed untracked.
- `tests/test_opr_tool_extraction.py` stayed in HEAD against the opr stub.
  `pytest` collection fails with `extract_json_tool_call` missing. The
  delete was only in the worktree.
- Working tree after the “cleanup”: 57 untracked paths and that unstaged
  delete.

The useful work is the two later commits. The failure is the meta-task:
hygiene, provenance, and not overclaiming. That is the hard part, and it is
the part git amplifies.

### What it does support

Read as a **harness / permission** observation:

> A local 31B seat can land a bounded code drop (`gated_runner`, R3
> scripts). It cannot be trusted as the git actor or the publication actor
> on a dirty, multi-constraint tree. Its recap of that work is narration.
> `git log`, `git status`, and the paper header are the gate.

This is the same partition as R5 (the agent does not report the outcome)
applied to git and to paper lifecycle. It is also R4: too many artifacts
in one invocation.

### Policy

Do not give `gemma4:31b` (or other local implementer seats) `git commit` /
rebase / history rewrite unless the human is explicitly studying that
failure mode. Do not re-dispatch this class of work to 31B. OpenCode is the
local implementer; Operator is the ledger; Paper 1.45 stays a draft until a
real four-model harness-R3 packet exists.

### Confounds

n=1, one machine, supervisor both assigned the experiment and scored it,
prompt was prose rather than a pytest gate on `git status`. Not a rate.
