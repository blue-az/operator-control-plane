# Crystal ↔ Ledger Phase 3 — Session Bridge (mini-spec)

> **Status: implemented with Phases 1–2.** Builds on `CRYSTAL_LEDGER_INTEROP_SPEC.md`.
> Trust rules T1–T7 still bind. This document only defines the hook/session glue.

## 0. Why

Phases 1–2 make crystals *attachable* and *importable* as draft ledger evidence.
Phase 3 removes the manual step of remembering to open an Operator session when a
coding harness starts and to attach the rolled-up session crystal when the
session closes.

Crystallize still owns writing `.agent-crystals/`. Operator still owns `.operator/`.
The bridge only **invokes** existing Operator commands; it never writes crystals
and never auto-verifies claims.

## 1. Non-goals

- No Operator writes into `.agent-crystals/` (T1).
- No execution or model-feed of crystal body text (T3).
- No auto-verification / status laundering (T2).
- No auto-`crystal-import` at session end (claim extraction stays an explicit
  Phase 2 action — end-of-session only **attaches** the crystal).
- No harness trust/install automation (Codex/Claude `/hooks` remains human).
- No hard dependency on the `agent-crystallize` binary at Operator runtime
  (bridge reads files Operator already knows how to parse).

## 2. Surfaces

### 2.1 `operator crystal-bridge --event EVENT`

Hook-facing entry point. Intended to be chained **after** (or beside)
`agent-crystallize hook --event EVENT` in harness config.

| Event | Behavior |
|-------|----------|
| `SessionStart` | If a local ledger + resolvable task exist: run `session-start` for `--harness` (required). Soft-no-op if already running (unless `--force`). |
| `Stop` | Attach the latest **session** crystal under the task repo's `.agent-crystals/sessions/` (or `--crystal PATH`) as draft `session_crystal` evidence on the open session's task. Does **not** close the usage session. |
| other crystallize events | Soft no-op (exit 0). PreCompact/PostCompact remain crystallize-owned. |

**Soft-fail policy (hooks must not brick the harness):**

- No `.operator` ledger → print notice, exit 0.
- No current/resolvable task on SessionStart → notice, exit 0 (unless `--task` given and missing → exit 1).
- No session crystal found on Stop → notice, exit 0 (unless `--require-crystal` → exit 1).

### 2.2 `operator session-end … --attach-crystal [auto|PATH]`

When a human (or captain script) closes a usage session, optionally attach the
rolled-up session crystal **before** the usage record is closed:

- `auto` — newest `*.md` under `<task.repo>/.agent-crystals/sessions/` by mtime.
- `PATH` — explicit crystal file (must be a regular file).
- Attach uses the Phase 1 `crystal-attach` path (draft only, T6 validation).
- Fingerprint idempotency: if that crystal is already attached on the task, skip
  with a notice (same idea as Phase 2 import idempotency).
- Failure to attach with `--require-crystal` aborts session-end; without it,
  warn and still close the session.

### 2.3 Harness name mapping

Crystallize `--harness` values map to Operator registry IDs:

| crystallize / bridge input | Operator harness id |
|----------------------------|---------------------|
| `claude-code`, `claude` | `claude` |
| `codex` | `codex` |
| `gemini-agy` | `gemini-agy` |
| other | must match a registered harness id exactly |

## 3. State recorded

On successful SessionStart bridge, the new usage record may include:

```yaml
crystal_bridge:
  event: SessionStart
  harness: claude
  bridged_at: <ISO-8601>
```

On successful attach (Stop bridge or session-end flag), the usage record (when
known) and/or stdout note the evidence id. Attach itself is ordinary
`session_crystal` evidence (Phase 1 metadata fields).

## 4. Example harness wiring (Claude Code fragment)

Full file: `examples/crystal-bridge-claude-hooks.fragment.json`. Uses `npx -y
@stewie-sh/agent-crystallize` rather than a bare `agent-crystallize` binary
name — hook subprocesses do not necessarily inherit the interactive shell
PATH, so a bare binary name can silently fail with `command not found` while
the `;`-chained `operator crystal-bridge` call still runs (the Operator half
degrades gracefully either way; this only affects whether crystallize's own
half of the chain fires). If you have the binary installed globally or at a
known absolute path, replace the `npx -y …` prefix to skip resolve overhead.

```json
{
  "hooks": {
    "SessionStart": [{
      "matcher": "startup|resume|clear|compact",
      "hooks": [{
        "type": "command",
        "command": "npx -y @stewie-sh/agent-crystallize hook --harness claude-code --event SessionStart; operator crystal-bridge --event SessionStart --harness claude",
        "timeout": 45
      }]
    }],
    "Stop": [{
      "hooks": [{
        "type": "command",
        "command": "npx -y @stewie-sh/agent-crystallize hook --harness claude-code --event Stop; operator crystal-bridge --event Stop",
        "timeout": 45
      }]
    }]
  }
}
```

Captain still closes cost/outcome explicitly:

```bash
operator session-end usage-0001 --outcome useful --cost 0 --attach-crystal auto
```

## 5. Tests

1. `crystal-bridge --event SessionStart` opens a usage session on the current task.
2. Soft-no-op without `.operator` (exit 0).
3. `session-end --attach-crystal` with a sessions/ fixture attaches `session_crystal`.
4. Re-attach same crystal is idempotent (notice, no duplicate evidence).
5. Bridge never accepts verification status.
6. Existing suite remains green.

## 6. Relation to interop phases

| Phase | Command | Role |
|-------|---------|------|
| 1 | `crystal-attach` | Fingerprint + metadata, draft evidence |
| 2 | `crystal-import` | Extract draft claims from Tests bullets |
| 3 | `crystal-bridge` + `session-end --attach-crystal` | Lifecycle glue only |
