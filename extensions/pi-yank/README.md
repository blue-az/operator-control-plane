# pi-yank

Canonical source for the personal Pi `/yank` command. Contract:
`owners-manual/pbc/appendix-pi-yank-extension.pbc.md`.

Pinned harness: **@earendil-works/pi-coding-agent 0.85.1** (session + clipboard
APIs only; no CustomEditor / TUI internals).

This is not an Operator runtime dependency. Operator does not import it.

## Layout

| Path | Role |
|---|---|
| `core.ts` | parse, slice, message-text extraction (no pi import) |
| `index.ts` | Pi extension entry (`/yank`) |
| `selftest.ts` | fail-closed unit checks against `core.ts` |

## Install / sync to the live Pi path

Pi loads global extensions from `~/.pi/agent/extensions/*.ts` and
`~/.pi/agent/extensions/*/index.ts`.

From this checkout:

```bash
# Prefer a directory link (loads index.ts).
rm -f ~/.pi/agent/extensions/pi-yank.ts
ln -sfn "$PWD/extensions/pi-yank" ~/.pi/agent/extensions/pi-yank
```

Restart Pi. `/yank` should be available in every project.

The old single-file install (`~/.pi/agent/extensions/pi-yank.ts`) is a
**deployed copy**, not the source of truth. Replace it with the link above
so edits in git are what Pi loads.

Uninstall: `rm ~/.pi/agent/extensions/pi-yank` (or the old `.ts` file). Does
not touch this repository.

## Verify

```bash
node --experimental-strip-types extensions/pi-yank/selftest.ts
python3 -m pytest tests/test_pi_yank.py -q
```

Requires Node ≥ 22.6 (`--experimental-strip-types`). Does not run Pi, does
not write the clipboard, does not touch `~/.pi/agent/settings.json`.
