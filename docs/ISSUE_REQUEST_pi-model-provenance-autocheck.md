# Feature/bug request: model provenance check at documentation boundaries

**Status:** requested; not implemented  
**Repository:** `operator-control-plane`  
**Reported:** 2026-09-11

## Problem

Pi remains the harness while the active model/provider can change during a session. A
session was documented as Grok even though the live environment reported:

```text
PI_PROVIDER=openai-codex
PI_MODEL=gpt-5.6-luna
```

The provenance was assumed rather than checked. This is a narration-surface bug: the
artifact can be internally coherent while naming the wrong model.

## Requested behavior

Whenever a user asks Operator/Pi to document, crystallize, hand off, or otherwise
freeze session findings, capture the live harness identity rather than relying on
conversation memory or a hardcoded label:

- `PI_PROVIDER`
- `PI_MODEL`
- `PI_SESSION_ID` (or safe harness equivalent)
- harness and harness version
- timestamp

If the requested/documented identity differs from the live identity, emit a visible
warning and preserve both values as `claimed` and `observed`; do not silently rewrite
or silently accept the mismatch.

## Trust boundary

Environment fields are provenance metadata, not evidence that a model produced every
historical turn. The check must not claim that a mid-session model switch retroactively
changes earlier turns. It should label the artifact with the observed identity at
capture time and, where available, record the switch boundary.

No API keys, bearer tokens, cookies, or broad environment dumps may enter the crystal,
ledger, or evidence artifact.

## Acceptance criteria

1. A documentation/crystallization invocation records the live provider and model.
2. A deliberate provider/model mismatch produces a warning or fail-closed result,
   according to the caller's mode; it never silently reports the requested label.
3. A missing identity is explicit (`unknown`), not inferred from directory or prose.
4. Existing crystals remain readable; this is additive metadata, not a migration that
   rewrites historical provenance.
5. Tests cover model switch, missing variables, and secret redaction.
6. A smoke run proves the resulting artifact contains observed identity and contains no
   token/key material.

## Evidence from report

- Pi environment at capture: `PI_PROVIDER=openai-codex`, `PI_MODEL=gpt-5.6-luna`.
- Incorrect earlier narration called the supervisor seat Grok.
- Corrected crystal: `.agent-crystals/sessions/20260910T231132Z-dual-seat-ppr-factory-overnight-juice-vs-deepseek-vs-codex-luna.md`.
