---
id: pbc_pi_yank_extension
title: "Pi-Yank Extension — Behavior Contract Draft"
context: pi-yank-extension
status: draft
tags:
  - pbc
  - operator
  - pi
  - extension
  - clipboard
updated: 2026-09-09
---

# Pi-Yank Extension — Behavior Contract Draft

> Draft PBC for a small personal pi extension that yanks a slice of a session
> message to the clipboard. Motivated by the removal of pi-vim-flash (0.1.5),
> which hard-froze the pi 0.85.1 TUI (upstream issue
> https://github.com/kungfusaini/pi-vim-flash/issues/2) and took the
> "select a range in the transcript, copy it out" workflow away with it.
>
> This is a design guardrail before implementation: it names the command
> surface, the fail-closed behavior of ambiguous slices, and the hard
> boundary (no TUI/editor internals) that made pi-vim-flash unsafe.

## Purpose

Give the operator user a keyboard-only, vi-flavored way to extract
mid-message text from pi's session without terminal selection, rendered
artifacts, or any state that can wedge the TUI. The workflow replaces the
pi-vim-flash loop `Esc → s → v → y` with a single slash command:
name two anchors (or one), get the slice on the clipboard, paste with
pi's normal `Ctrl+V`.

## Scope

Covers a single-file personal extension at
`~/.pi/agent/extensions/pi-yank.ts`, exposing one registered pi command,
`/yank`, that reads the active session's stored message text and writes
one string to the clipboard via pi's clipboard path (the same mechanism
pi-copy-message uses, including its OSC 52 fallback).

It governs:

- the `/yank` argument surface and its parse order,
- which message is in scope by default and how a specific message is
  addressed,
- how anchors (start/end) resolve into a deterministic slice,
- the fail-closed behavior for unresolvable slices,
- the hard API boundary (session data + clipboard only).

## Non-Goals

- No modal editor, no key remapping, no transcript overlay, no scrollback
  rendering, no CustomEditor. Anything in the pi-vim-flash failure class is
  out of scope by design.
- No persistent marks or state; anchors are given on the command line every
  time. Stateful `/mark` is a possible later slice and is out of scope until
  asked for explicitly.
- No role-scoped index in v1 (`~a2` = 2nd newest assistant message). Owner
  asked for it as a **future improvement**, not this draft's command surface.
  See Future Improvements.
- No cross-session or cross-project copying; only the active session.
- No writes to the session file, compaction, or any other side effect
  beyond one clipboard write per successful invocation.
- No interaction with or replacement of pi-copy-message or pi's native
  `Ctrl+X`; /yank is the surgical complement to those, not a superset.
- No packaging, publishing, or third-party surface. This is a local
  personal extension.

## Actors

```pbc:actors
- id: operator_user
  name: Operator user
  type: human
  description: Types /yank in interactive pi and decides what is acceptable.
- id: pi_harness
  name: Pi harness
  type: external
  description: TUI harness that loads the extension and provides the command, session, and clipboard APIs.
- id: pi_agent
  name: Pi agent
  type: system
  description: Model-driven assistant; not a required user of /yank (human ergonomics first).
- id: pi_yank
  name: Pi-Yank extension
  type: system
  description: The extension under contract. Registered command handler plus pure slice logic.
- id: pi_copy_message
  name: pi-copy-message extension
  type: external
  description: Installed reference implementation for message enumeration ordering and the clipboard path.
```

## Rules

v1 is implemented. Owner tracking / ratification surface is the Magic
dashboard Fronts card **YNK** (`magic_bridge/dashboard_fronts.yaml`).
That link is how this draft is tracked; it is not uid-isolated verification.
Rules below stay `proposed-rules` (no `pbc:rules` block) until a later
conversion. `~aN` is Future Improvements, not v1.

```pbc:proposed-rules
- id: PYY-RUL-101
  name: Command Surface Is A Single Stateless Verb
  rule: >
    The extension registers exactly one command, /yank, with the surface
    /yank [~N] [start] [end]. No second command, no aliases, no persisted
    state. An invocation with no arguments yanks the entire message
    selected by the default rule (PYY-RUL-102) and is the
    Ctrl+X-equivalent floor.
  trust: proposed
- id: PYY-RUL-102
  name: Default Message Is The Latest Assistant Message
  rule: >
    When no ~N is given, /yank targets the latest assistant message of the
    active session, matching pi's native Ctrl+X and /copy default. ~N is
    a 1-based newest-first index over messages shown in the
    pi-copy-message chat ordering, and an out-of-range N fails closed
    (PYY-RUL-105).
  trust: proposed
- id: PYY-RUL-103
  name: Anchors Are Plain Substrings, Resolution Is Deterministic
  rule: >
    start and end are literal, quoted substrings, not regexes. The slice
    begins at the first occurrence of start (message start if start is
    omitted) and ends just before the first occurrence of end strictly
    after the start point (message end if end is omitted). The first
    match, not "closest" or all matches, is used. No case folding, no
    whitespace folding: anchors either match exactly or they do not.
  trust: proposed
- id: PYY-RUL-104
  name: Slices Copy The Raw Stored Message Text
  rule: >
    The yanked content is the stored message text sliced as in
    PYY-RUL-103, not rendered TUI text: no terminal wrapping, no color or
    markdown rendering artifacts injected, no truncation of long lines.
    This is the property pi-copy-message advertises and this extension
    inherits by construction, since it never touches the renderer.
  trust: proposed
- id: PYY-RUL-105
  name: Unresolvable Slices Fail Closed With A Named Error
  rule: >
    The extension refuses, with a message that names the failing anchor
    verbatim, when: start is absent from the message; end occurs before
    or at the start position; the slice would be empty; the target
    message does not exist or holds no text content. On refusal the
    clipboard is untouched. There is no silent fallback to the whole
    message.
  trust: proposed
- id: PYY-RUL-106
  name: Only Public Session And Clipboard APIs Are Touched
  rule: >
    The extension reads only through pi's session/entry APIs (the same
    surface pi-copy-message uses) and writes only through pi's clipboard
    path. It does not register a CustomEditor, does not read or render the
    transcript or scrollback, does not install key handlers, and does not
    use internal/unstable pi TUI APIs. This is the explicit anti-freeze
    boundary drawn from the pi-vim-flash failure on pi 0.85.1.
  trust: proposed
- id: PYY-RUL-107
  name: One Success Notification, No Silent No-Ops
  rule: >
    On success the extension reports the yanked length and a trimmed
    preview (first and last ~20 visible characters) so the copy is
    confirmable at a glance. On failure it reports the PYY-RUL-105 error.
    An invocation that neither copies nor explains itself is a defect.
  trust: proposed
```

## Acceptance Outcomes

```pbc:proposed-outcomes
- id: PYY-OUT-101
  name: Whole-Message Floor
  outcome: >
    /yank with no arguments leaves the full text of the latest assistant
    message on the clipboard; Ctrl+V pastes it into the prompt intact.
  trust: proposed
- id: PYY-OUT-102
  name: Two-Anchor Slice
  outcome: >
    /yank "start" "end" leaves exactly the text between the first start
    and the first end after it, with raw stored text per PYY-RUL-104.
  trust: proposed
- id: PYY-OUT-103
  name: Explicit Message
  outcome: >
    /yank ~N targets the N-th newest message in the established ordering
    and fails closed with a named error when N is out of range.
  trust: proposed
- id: PYY-OUT-104
  name: Refusal Does Not Write
  outcome: >
    Every PYY-RUL-105 failure leaves the clipboard unchanged and prints
    the failing anchor or condition.
  trust: proposed
```

## Proof Boundary

Shows: a scoped, fail-closed, API-boundary-pinned shape for a personal
pi extension that restores the pi-vim-flash "copy a slice of a message"
workflow without any of its TUI-internal surface.

Does not show: that the command is complete, that the anchor grammar is
final, or that stateful marks are not wanted (explicitly deferred).
Owner tracks v1 on Magic dashboard Fronts **YNK**. `~aN` remains future.

## Resolved Scope Decisions

Locked by the owner at scope time (2026-09-09):

1. `~N` indexes **all** messages in the active session, using the same
   newest-first ordering pi-copy-message exposes. It does not filter to
   assistant-only. This keeps the number predictable against the
   reference the owner already uses. (PYY-RUL-102.)
2. Anchor grammar is closed at the drafted surface: `start`/`end` are
   literal substrings, and **omitting `end` is the "to end of message"
   affordance.** No explicit rest-of-message token (e.g. `$`) is added.
   (PYY-RUL-103.)
3. A `/paste` companion command is **out of scope.** The clipboard is the
   boundary; pasting is pi's native `Ctrl+V` (PYY-RUL-101).

## Future Improvements

Not in v1. Do not implement until a later draft amends PYY-RUL-102 and
adds an outcome. Recorded 2026-09-09 at owner request:

- **`~aN` assistant-only index.** Same newest-first counting as `~N`, but
  only assistant messages. `/yank` with no number stays latest assistant
  (already true). `/yank ~2` stays all-roles (a user turn often sits at
  `~2`). `/yank ~a2` would be the previous **reply**. Out-of-range still
  fails closed. No other role letters in this item (`~uN` etc. not asked).
- Stateful `/mark` and a `/paste` companion remain unasked; still non-goals.

## Open Questions

None for v1. `~aN` is parked under Future Improvements, not an open
design debate.
