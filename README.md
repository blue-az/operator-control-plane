# Operator Control Plane

A small, local, file-backed **governance ledger for multi-agent software work.** It enforces a
**narration-vs-execution partition**: an agent's *claim* ("I did X, it passes") is only as good as the
*evidence* attached to it and the *verification* by a different identity. The `operator` CLI records
tasks → claims → evidence → verifications as append-only YAML under `.operator/`, binds each write to
the executing OS identity, guards against self-verification, and ships a `doctor` consistency checker.

Built as the "engine room / logbook" enforcement substrate for [Bulkhead τ](https://bulkheadtau.com),
but it stands alone. **Contributions welcome** — especially on the open problems below.

## Quickstart

```bash
pip install -r requirements.txt        # just PyYAML
./operator --help
./operator doctor                      # consistency check over the local .operator/ ledger
pytest tests/                          # subprocess-driven tests + synthetic session fixtures
```

The ledger (`.operator/`) is gitignored — it's your work history, not the tool.

## Design specs

- [`EXECUTOR_IDENTITY_SPEC.md`](EXECUTOR_IDENTITY_SPEC.md) — process-level identity binding via `os.getuid()`.
- [`VERIFIED_BY_GUARD_SPEC.md`](VERIFIED_BY_GUARD_SPEC.md) — fail-closed on self-verification (a builder can't sign off its own claim).
- [`USAGE_AUTOIMPORT_SPEC.md`](USAGE_AUTOIMPORT_SPEC.md) — ingest per-session token/usage from Claude/Codex/Gemini harness logs without unit conflation.

## Known limitations — help wanted

These are real and known (named honestly rather than hidden — the whole point of the tool is that
unverified claims are worthless):

- **Honor-system `verified_by` in `single_user` mode.** When every agent runs under one OS user,
  identity enforcement is advisory — the builder can assert the reviewer's name. Real enforcement needs
  distinct OS users / containers, or a write-isolated reviewer. *Hard problem; ideas welcome.*
- **The ledger is local-only and unbacked.** `.operator/` is gitignored; a disk wipe loses the audit
  trail. Evidence written to `/tmp` has been lost this way. Wants a durable, tamper-evident store.
- **The policy gate is self-amendable.** Any agent with write access to the config can weaken the gate
  it's supposed to be bound by. Wants out-of-band / immutable policy.
- **Evidence binding.** Prefer binding a *re-runnable structural test* over a captured blob or a
  byte-hash of a living document (living docs drift and train reviewers to rubber-stamp).

## License

MIT.
