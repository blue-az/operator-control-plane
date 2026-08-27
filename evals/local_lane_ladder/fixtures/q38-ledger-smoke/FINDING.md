# ledger-gate smoke — workflow fixture, attach half is a floor

**Mined from:** this week's operator work. `claim-0014` was rejected because
`required_gate` was prose; T2 / `verified_by` forbids the builder flipping
`verification_status`; every real attach fingerprints the file.

**Smokes:** 2026-08-14, L2, n=2, `qwen3.8:27b` `gemma4:26b` `gemma3:27b`,
think off, ctx 16384. Three shapes, 18 cells, **0 full passes**.
Not UID-verified.

## Two halves, one of them is free

| Half | What it is | Smoke |
|---|---|---|
| gate | `required_gate` must be `ledger/notes.txt`, not "the attach tests pass" | **6/6** |
| integrity | sha256 of `ledger/notes.txt` written into evidence, and the claim left unverified | **0/6** |

**Pass 1** (two files, compute sha256): everyone patched the gate line
and stopped. One `qwen3.8` trial computed the correct digest and never
wrote it. `gemma4:26b` never hashed.

**Pass 2** (named `sha256sum`, 6 continue-steps): same 0/6, same missing write.

**Pass 3** (one record, digest precomputed in `notes.sha256`, concrete
four-line replacement — the `evidence-attach` shape): **0 writes**. All
six cells read the three files and stopped. Reconnaissance without a
state change.

That is the live attach workflow, not a puzzle. Local models will rewrite
a single visible YAML field when the L2 step is one line. They will not
fingerprint, and a multi-line record write is enough to stall the loop.

## What this is not

Not a mid-band Elo item. A 0/6 on the top *and* the floor is `csv-summarize-repair`
class — a ceiling marker for this workflow, not a ranking instrument. No
eight-model field was run; more n will not split 26b / 31b / q38.

Task file kept. Treat like csv: keep as a ceiling, do not read as ability
inside the 1814 band.
