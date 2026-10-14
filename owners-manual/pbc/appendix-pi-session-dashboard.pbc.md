---
id: pbc-pi-session-dashboard
title: "Pi Session Dashboard — Behavior Contract Draft"
context: pi-session-dashboard
status: draft
updated: 2026-10-12
tags:
  - pbc
  - operator
  - pi
  - extension
  - dashboard
  - read-only
---

# Pi Session Dashboard

## Purpose

Give the operator a small, local, read-only Pi TUI view of the sessions reported by
pi-intercom. Version 1 is a local, per-process, read-only Pi session roster. From an
interactive Pi process that loaded the extension, `/dashboard` presents the session roster
and metadata; `r` refreshes it and `q` closes it. No JIG-specific feature, code, or API is used.

## Current prototype and contract status

A personal extension exists at `~/.pi/agent/extensions/agent-dashboard.ts`, outside this
repository. Source review and a local screenshot confirm that `/dashboard` rendered a roster;
Erik reports that `r` and `q` work. The source's provenance and canonical distribution location
are not established. Disconnect/error handling, stale-boundary behavior, privacy, and Escape
have not been systematically verified.

Extension availability is process-local: a Pi process that did not load the extension does not
have `/dashboard`. The screenshot showed the dashboard in a separate Pi process launched from the
`extensions` directory; the already-running Project Phoenix process did not gain the command.
Reload/hot-load behavior has not been verified.

This is a **draft contract**, not approval or ratification of the existing prototype. It does not
authorize implementation changes or claim that the displayed session reports are independently
verified.

## Scope

- The personal Pi extension that registers `/dashboard`.
- The pi-intercom extension channel used to obtain a session roster.
- Read-only display of session name, client-reported status, cwd, model, last-activity age,
  optional context percentage, and optional Herdr location.
- Explicit manual refresh and close behavior.
- Process-local extension availability and the operator path when an existing Pi process has not loaded it.
- Honest treatment of missing channel, unavailable UI, missing optional fields, and refresh errors.

The source/install path is currently local-only. Choosing a canonical, version-controlled source
or distribution mechanism is an open decision, not implied by this contract.

## Non-goals

- Any JIG-specific feature, code, API, data import, or runtime integration. No JIG-specific
  feature, code, or API is used.
- Host process discovery, session-file/log/transcript inspection, benchmark/run state, or claims
  that a reported session is alive, healthy, or actually executing.
- Starting, stopping, killing, messaging, or otherwise controlling sessions.
- Persistent history, caches, telemetry, or network access beyond the declared pi-intercom
  session-list channel.
- A Project Phoenix/Magic dashboard card, a public web surface, a shared dashboard window visible in every Pi session, or a general agent-management UI.
- Model-callable tools or automatic use of the roster to route work.

## Future design candidate — agent-centric view (not v1 scope)

**Follow-on design candidate (separate from v1):** the expected TennisAgent Mac agent, with
an explicit mapping from expected agent identity to reported session(s), could be considered
separately. Registry/session identity mapping remains unresolved. This is a design candidate
only; there is no implementation authorization.

The current `listSessions()` roster alone cannot establish which agents are expected or map a
session reliably to an agent; that requires an explicit, trustworthy agent registry/identity
mapping. The authoritative source and mapping remain undecided.

Andrii Shylenko's Grok Bot post and `~/Pictures/LinkedIn/GrokFlow.jpeg` are design inspiration:
the screenshot shows a mobile chat list with distinct project/role names and recent message
snippets. It does not establish Grok Bot's internals or prove autonomous execution. This is a
future-scope candidate, not a commitment to clone Grok Bot or expand the current v1 PBC.

## Actors

```pbc:actors
- id: operator
  name: Human operator
  type: human
  description: Opens the dashboard and interprets its client-reported session information.
- id: pi_runtime
  name: Pi runtime
  type: external
  description: Loads the extension and supplies interactive TUI and extension APIs.
- id: pi_intercom
  name: pi-intercom channel
  type: external
  description: Supplies the session roster through the declared listSessions interface.
- id: session_dashboard
  name: Session dashboard extension
  type: system
  description: Registers /dashboard and renders a read-only roster; it is not an authority for session liveness or health.
```

## Proposed rules

```pbc:proposed-rules
- id: PSD-RUL-101
  name: Read only the declared roster
  rule: >
    The extension obtains roster data only through the registered pi-intercom
    listSessions() channel. It MUST NOT scan host processes, session files,
    logs, transcripts, or unrelated APIs to supplement or validate the roster.
  trust: proposed
- id: PSD-RUL-102
  name: Preserve reported provenance
  rule: >
    Status and metadata are client-reported. The UI MUST label status as
    reported, or unknown when absent, and MUST NOT infer that a session is
    alive, dead, healthy, active, or available from a missing or stale report.
  trust: proposed
- id: PSD-RUL-103
  name: Restrict displayed fields
  rule: >
    The v1 display is limited to session name, reported-or-unknown status,
    cwd, model, last-activity age, optional context percentage, and optional
    Herdr location. It MUST NOT display message contents, prompts, tool
    arguments, environment variables, secrets, or arbitrary channel payloads.
  trust: proposed
- id: PSD-RUL-104
  name: Make staleness a narrow timestamp label
  rule: >
    A stale marker refers only to the age of the reported lastActivity
    timestamp; it is not a liveness or health verdict. The prototype uses a
    threshold greater than 120 seconds. The owner must confirm this threshold
    before ratification, and the UI MUST expose the age that explains the marker.
  trust: proposed
- id: PSD-RUL-105
  name: Refresh only on operator request
  rule: >
    The roster is fetched when /dashboard opens and refreshed only when the
    operator presses r. The extension MUST prevent overlapping refreshes and
    MUST show refresh failures in the dashboard without hiding the existing
    roster or throwing an unhandled UI error.
  trust: proposed
- id: PSD-RUL-106
  name: Close without side effects
  rule: >
    q closes the dashboard. Escape SHOULD close it if supported by the stable
    Pi component API. Closing MUST NOT modify or message any listed session.
  trust: proposed
- id: PSD-RUL-107
  name: Fail explicitly at the UI boundary
  rule: >
    If interactive UI is unavailable, the command MUST report that the
    dashboard requires interactive mode. If the intercom channel is not
    ready, it MUST report that it is not connected; an empty roster MUST be
    presented distinctly from a failed or unavailable channel.
  trust: proposed
- id: PSD-RUL-108
  name: Keep roster data local and ephemeral
  rule: >
    The extension MUST NOT persist roster data, send it outside the declared
    local pi-intercom channel, or expose it as a model-callable tool. Cwd,
    model, context percentage, and Herdr location are sensitive local
    metadata and are displayed only in the operator's interactive TUI.
  trust: proposed
- id: PSD-RUL-109
  name: Render untrusted fields as safe text
  rule: >
    Session-provided strings MUST be bounded to the display width and rendered
    as text. Terminal control sequences or other content that could alter the
    TUI MUST be escaped or removed before rendering.
  trust: proposed
- id: PSD-RUL-110
  name: No JIG-specific functionality
  rule: >
    The extension MUST NOT use JIG-specific features, code, or APIs. Names,
    documentation, and UI text MUST NOT imply JIG integration.
  trust: proposed
- id: PSD-RUL-111
  name: Dashboard availability is process-local
  rule: >
    The dashboard UI appears only in the Pi process that loaded the extension.
    It is not broadcast into the sessions listed in the roster. An existing
    Pi process that did not load the extension cannot invoke /dashboard;
    installation or activation instructions MUST state the supported way to
    make the command available there. Whether hot loading is required remains
    an owner decision.
  trust: proposed
```

## Proposed acceptance outcomes

```pbc:proposed-outcomes
- id: PSD-OUT-101
  name: Interactive roster render
  outcome: >
    In a fresh interactive Pi session with the extension loaded and the
    channel ready, /dashboard renders the listSessions() roster and only the
    fields permitted by PSD-RUL-103.
  trust: proposed
- id: PSD-OUT-102
  name: Refresh and close
  outcome: >
    Pressing r fetches an updated roster once; pressing q closes the view.
    Escape closes it if the supported Pi component API provides that behavior.
  trust: proposed
- id: PSD-OUT-103
  name: Honest unavailable and error states
  outcome: >
    No-UI, channel-not-ready, empty-roster, and refresh-failure cases are
    distinguishable and explained to the operator; refresh failure does not
    crash or silently discard the displayed roster.
  trust: proposed
- id: PSD-OUT-104
  name: Stale label has bounded meaning
  outcome: >
    Tests at the threshold boundary show that the stale marker reflects only
    lastActivity age and never asserts session liveness or health.
  trust: proposed
- id: PSD-OUT-105
  name: Privacy and safe rendering
  outcome: >
    A field/provenance review confirms that only the allowlisted local
    metadata is shown, no roster data is persisted or sent elsewhere, and
    untrusted session strings cannot inject terminal control sequences.
  trust: proposed
- id: PSD-OUT-106
  name: No session control or JIG coupling
  outcome: >
    Source inspection and tests show no session start/stop/message controls,
    model-callable tool, JIG-specific feature, code, or API.
  trust: proposed
- id: PSD-OUT-107
  name: Process-local availability is explicit
  outcome: >
    A fresh or restarted Pi process loads the extension and can invoke the
    dashboard. The supported behavior for a pre-existing process is explicit;
    no other Pi session is implied to share the dashboard UI.
  trust: proposed
```

## Acceptance evidence expected before ratification

- Automated component/formatting tests using a stub `listSessions()` channel for populated,
  empty, optional-field, malformed-string, and refresh-error cases.
- A fresh interactive Pi smoke test for command load, roster display, `r`, `q`, and Escape if
  adopted; the current screenshot plus Erik's `r`/`q` report are preliminary evidence only.
- A disconnect/channel-not-ready check and a stale-threshold boundary test.
- A privacy/provenance review of the channel payload and displayed fields.
- A decision on canonical source/distribution location and on the 120-second stale threshold.

## Proof boundary

Passing these checks would show that a local Pi extension displays a bounded, client-reported
session roster and handles the specified UI states. It would **not** prove that a reported
session is alive or executing, validate the accuracy of every peer's metadata, establish any JIG integration, or provide a host/process monitor.

## Open owner decisions

1. Confirm the 120-second stale threshold and its exact presentation.
2. Confirm that cwd, model, context percentage, and Herdr location are acceptable fields to show
   in the local TUI.
3. Choose the canonical source and distribution location for this personal extension.
4. Decide whether Escape is a supported close binding or only `q` is guaranteed.
5. Decide whether requiring a fresh/restarted Pi process is acceptable, or whether an existing session must be able to activate the dashboard without restart.
6. For the follow-on agent view, decide the authoritative expected-agent registry, identity mapping, and its separate contract/scope before implementation.

Until those decisions and the acceptance evidence are complete, this file remains `draft`; the
existing local extension is a prototype and is not ratified by its presence or by the screenshot.
