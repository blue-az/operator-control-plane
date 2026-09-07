# INVALID RUN — DO NOT SCORE. L0 prompt ambiguity, not a capability measurement.

**Status: quarantined.** These 46 traces must not enter any pass-rate, ranking or
seat-score analysis. Exclude this fixture by name.

**Run:** desktop, 2026-09-07. `qwen3.8:27b`, `qwen3.6:35b`, `gpt-oss:120b` ×
3 seat tasks × **L0** × n=6. Stopped at 46/54 by the operator because it was
raising repeated sudo password prompts on the desktop.

## Why the data is invalid

`strict-log-format` at L0 reads:

> *"I need a summary of how many errors happened each hour from my logs."*

The task's L2 prompt is about implementing `error_report(log_text)` in
`src/logsum.py` against `tests/check_logsum.py`. **L0 never names the artifact.**
Models reasonably interpreted "my logs" as the host's real system logs and ran

```
sudo grep -iE '\b(error|warning|critical)\b' /var/log/messages-20260830
sudo test -r /var/log/messages
sudo head -5 /var/log/messages-20260906
```

They never touched `src/logsum.py`, so they failed a postcondition about a file
the prompt never mentioned. **The failures measure prompt ambiguity, not model
capability.** A model doing the sensible thing scores zero.

The same objection applies to the 13 pre-existing L0 trials elsewhere in the
corpus (2/13). Those are equally unusable and equally should not be cited.

## Secondary finding: trials are not confined to their fixture directory

Trials execute in `/tmp/local-lane-eval-*` but nothing restricts them there. At
L0 a model left that directory and read the host's `/var/log` under sudo. This is
a **harness blast-radius property, not a task bug** — it stays invisible at L2
only because L2 supplies exact paths, and it returns with any goal-shaped prompt.
Worth fixing before further L0 authoring.

## What would make an L0 run valid

- L0 prompts must **name the artifact** without restating the procedure — the
  point of L0 is that the model decides *how*, not that it guesses *what*.
- Graders must accept **correct-but-different** solutions; the current
  postconditions check one specified edit.
- Trials should be confined to the fixture directory.

Provenance: `HANDOFF_2026-09-06.md`, "New finding 2026-09-07".
