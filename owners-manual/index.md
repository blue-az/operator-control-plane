# Owner's Manual for blue-az/operator-control-plane — Index

Source: blue-az/operator-control-plane:master@c5cd06fca49d13e59ffb989d928d7c8fe923819f

## Contents

1. [What the Operator Control Plane Is For](chapters/01-what-the-operator-control-plane-is-for.md)
2. [How Work Moves Through the Ledger](chapters/02-how-work-moves-through-the-ledger.md)
3. [How Verification Creates Trust](chapters/03-how-verification-creates-trust.md)
4. [How Harnesses Coordinate Work](chapters/04-how-harnesses-coordinate-work.md)
5. [How Usage Import Supports the Audit Trail](chapters/05-how-usage-import-supports-the-audit-trail.md)
6. [Operating Boundaries, Failure Modes, and Stewardship](chapters/06-operating-boundaries-failure-modes-and-stewardship.md)

## Attention Index

- critical: [Verification is only as strong as the identity boundary](chapters/01-what-the-operator-control-plane-is-for.md)
- high: [Imported usage is useful but not complete proof](chapters/01-what-the-operator-control-plane-is-for.md)
- medium: [Do not let the scope inflate](chapters/01-what-the-operator-control-plane-is-for.md)
- high: [Do not treat one status as the whole story](chapters/02-how-work-moves-through-the-ledger.md)
- high: [Session closure only returns to assigned under narrow conditions](chapters/02-how-work-moves-through-the-ledger.md)
- medium: [Current-task fallback is command-specific](chapters/02-how-work-moves-through-the-ledger.md)
- critical: [Self-verification can undermine the whole trust model](chapters/03-how-verification-creates-trust.md)
- high: [The tool is not the whole identity boundary](chapters/03-how-verification-creates-trust.md)
- medium: [Doctor warns, it does not replace judgment](chapters/03-how-verification-creates-trust.md)
- critical: [Do not turn coordination into runtime ownership](chapters/04-how-harnesses-coordinate-work.md)
- high: [Do not blur the builder/reviewer split](chapters/04-how-harnesses-coordinate-work.md)
- high: [Do not describe session close as automatic reassignment](chapters/04-how-harnesses-coordinate-work.md)
- medium: [Harness metadata is secondary to the ledger record](chapters/04-how-harnesses-coordinate-work.md)
- high: [Imported activity is context, not proof](chapters/05-how-usage-import-supports-the-audit-trail.md)
- high: [The accounting model is not uniform across harnesses](chapters/05-how-usage-import-supports-the-audit-trail.md)
- high: [Missing source logs only warn](chapters/05-how-usage-import-supports-the-audit-trail.md)
- critical: [Local files are not proven durable or tamper-proof](chapters/06-operating-boundaries-failure-modes-and-stewardship.md)
- high: [Identity checking still leans on the host boundary](chapters/06-operating-boundaries-failure-modes-and-stewardship.md)
- high: [Imported provenance can survive a missing source file](chapters/06-operating-boundaries-failure-modes-and-stewardship.md)
- medium: [Session closure is conditional, not automatic](chapters/06-operating-boundaries-failure-modes-and-stewardship.md)
- medium: [Owner intent is still missing](chapters/06-operating-boundaries-failure-modes-and-stewardship.md)

## Owner Decision Index

- open: [Should the manual keep the product framed as a local governance ledger, not a generic workflow platform?](chapters/01-what-the-operator-control-plane-is-for.md)
- open: [Should this chapter keep the product framed as a local ledger rather than a hosted workflow system?](chapters/02-how-work-moves-through-the-ledger.md)
- open: [Should the manual say session closure falls back to assigned only when the task is still running and no open sessions remain?](chapters/02-how-work-moves-through-the-ledger.md)
- open: [Should the manual list which commands use the current-task fallback and which commands check harness state?](chapters/02-how-work-moves-through-the-ledger.md)
- open: [Should this chapter keep evidence capture separate from later verification?](chapters/02-how-work-moves-through-the-ledger.md)
- open: [Should verified claim writes stay locked to the configured identity map, or do you want a stronger external isolation rule in the operating setup?](chapters/03-how-verification-creates-trust.md)
- open: [Should doctor warnings about self-verification or reviewer mismatch be treated as stop-the-line issues?](chapters/03-how-verification-creates-trust.md)
- open: [Should single-user mode remain only a warning, rather than being described as enforced identity separation?](chapters/03-how-verification-creates-trust.md)
- open: [Should the manual keep the assigned harness and review harness as a hard distinction?](chapters/04-how-harnesses-coordinate-work.md)
- open: [Should coordination be framed as controlled recordkeeping rather than orchestration?](chapters/04-how-harnesses-coordinate-work.md)
- open: [Should session close be documented as a conditional return to assigned?](chapters/04-how-harnesses-coordinate-work.md)
- open: [Should imported usage stay advisory when it conflicts with verified ledger records?](chapters/05-how-usage-import-supports-the-audit-trail.md)
- open: [Should the manual keep separate language for token-metered and activity-only harnesses?](chapters/05-how-usage-import-supports-the-audit-trail.md)
- open: [Should a missing source log stay a warning instead of a hard failure?](chapters/05-how-usage-import-supports-the-audit-trail.md)
- open: [Do you want the local ledger to be your operational source of truth, or do you need extra backup and retention controls around it?](chapters/06-operating-boundaries-failure-modes-and-stewardship.md)
- open: [Is CLI-level identity checking enough, or do you need real separation from the host OS or container?](chapters/06-operating-boundaries-failure-modes-and-stewardship.md)
- open: [Should missing source logs stay a warning, or should they trigger stricter handling?](chapters/06-operating-boundaries-failure-modes-and-stewardship.md)
