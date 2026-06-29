# Owner's Manual for blue-az/operator-control-plane — Index

Source: blue-az/operator-control-plane:main@9b9e3e63a7f0f54ccde541c6c10570c8fdbe8f5b

> [!NOTE]
> **Post-scan verification (owner)**: Reflect's per-chapter boundaries below reflect its static scan. Since the scan, the owner exercised the runtime live — the worked example, doctor, and usage-import against the real session-log corpus — and fixed a codex-import bug surfaced in doing so. The runtime caveats describe the scan, not the current verified state.

## Contents

1. [What operator Is For](chapters/01-what-operator-is-for.md)
2. [How Work Moves Through the Ledger](chapters/02-how-work-moves-through-the-ledger.md)
3. [The Surfaces and Records You Actually Operate](chapters/03-the-surfaces-and-records-you-actually-operate.md)
4. [Trust, Identity, and Verification](chapters/04-trust-identity-and-verification.md)
5. [Sessions, Usage, and Accountability](chapters/05-sessions-usage-and-accountability.md)
6. [Running a Multi-Harness Workflow](chapters/06-running-a-multi-harness-workflow.md)

## Appendices

- [opr Governed LLM Client](chapters/appendix-opr-governed-llm-client.md) — draft migration
  target for the planned `opr` extraction.

## Attention Index

- critical: [This may be only the local tool, not the whole workflow](chapters/01-what-operator-is-for.md)
- high: [Init does not repair a broken ledger tree](chapters/01-what-operator-is-for.md)
- high: [Some writes depend on the current task already being set](chapters/01-what-operator-is-for.md)
- medium: [A claim is not trusted when it is created](chapters/01-what-operator-is-for.md)
- critical: [Claim status checks are not blanket checks](chapters/02-how-work-moves-through-the-ledger.md)
- high: [A late quarantine can overwrite terminal task state](chapters/02-how-work-moves-through-the-ledger.md)
- medium: [Usage import can match more than one shape of source](chapters/02-how-work-moves-through-the-ledger.md)
- medium: [Bootstrap is not a repair path](chapters/02-how-work-moves-through-the-ledger.md)
- medium: [Direct usage intake bypasses session provenance](chapters/02-how-work-moves-through-the-ledger.md)
- critical: [Status-bearing evidence can bypass the verifier gate when no claim is present](chapters/03-the-surfaces-and-records-you-actually-operate.md)
- high: [Quarantine can overwrite a task that was already terminal](chapters/03-the-surfaces-and-records-you-actually-operate.md)
- medium: [Usage import is more permissive than exact matching](chapters/03-the-surfaces-and-records-you-actually-operate.md)
- medium: [Direct usage intake bypasses the session-import trail](chapters/03-the-surfaces-and-records-you-actually-operate.md)
- critical: [Verifier gate is claim-bound](chapters/04-trust-identity-and-verification.md)
- critical: [Identity mode changes the guarantee](chapters/04-trust-identity-and-verification.md)
- high: [Evidence copy is best-effort](chapters/04-trust-identity-and-verification.md)
- high: [Quarantine can downgrade a finished task](chapters/04-trust-identity-and-verification.md)
- medium: [Bootstrap is not self-healing](chapters/04-trust-identity-and-verification.md)
- medium: [Usage import can merge instead of append](chapters/04-trust-identity-and-verification.md)
- medium: [Import matching can pull in more than one source](chapters/05-sessions-usage-and-accountability.md)
- high: [Manual usage entries do not carry the same source trail](chapters/05-sessions-usage-and-accountability.md)
- high: [Session closeout can change the final task state](chapters/05-sessions-usage-and-accountability.md)
- medium: [Import fidelity depends on external session logs](chapters/05-sessions-usage-and-accountability.md)
- critical: [A quarantine can still downgrade a finished task](chapters/06-running-a-multi-harness-workflow.md)
- high: [Session closeout can diverge from usage cleanup](chapters/06-running-a-multi-harness-workflow.md)
- high: [Verification is not a blanket rule on every evidence write](chapters/06-running-a-multi-harness-workflow.md)
- medium: [Usage import can match more broadly than an exact session ID](chapters/06-running-a-multi-harness-workflow.md)
- low: [The repository may not be the whole operating system](chapters/06-running-a-multi-harness-workflow.md)

## Owner Decision Index

- open: [Should this manual treat operator as the whole operating environment, or as one local component inside a larger workflow?](chapters/01-what-operator-is-for.md)
- open: [Should task-bound writes rely on the current task by default, or should every write require an explicit task selection?](chapters/01-what-operator-is-for.md)
- open: [Should bootstrap stay a first-run setup step, or should it also repair an existing .operator/ tree?](chapters/01-what-operator-is-for.md)
- open: [Should the manual treat claim-backed evidence status as the only trusted status path?](chapters/02-how-work-moves-through-the-ledger.md)
- open: [Should a late quarantine be allowed to override a task that already looks complete or verified?](chapters/02-how-work-moves-through-the-ledger.md)
- open: [Should usage import stay permissive and able to hydrate an open placeholder?](chapters/02-how-work-moves-through-the-ledger.md)
- open: [Should direct usage intake remain separate from session import provenance?](chapters/02-how-work-moves-through-the-ledger.md)
- open: [Should task-bound writes keep the implicit current-task fallback, or should the owner require explicit task identifiers on every write?](chapters/03-the-surfaces-and-records-you-actually-operate.md)
- open: [Should any status-bearing evidence write require a claim, or should bare evidence status writes remain allowed?](chapters/03-the-surfaces-and-records-you-actually-operate.md)
- open: [Should quarantine be allowed to downgrade a task that is already verified or complete?](chapters/03-the-surfaces-and-records-you-actually-operate.md)
- open: [Should imported usage remain permissive and placeholder-hydrating, or should it be narrowed to stricter matching and append-only behavior?](chapters/03-the-surfaces-and-records-you-actually-operate.md)
- open: [Should evidence attaches with status be rejected when no claim is supplied?](chapters/04-trust-identity-and-verification.md)
- open: [Should single-user mode remain a warning-only trust mode, or should it fail closed when identity rules are configured?](chapters/04-trust-identity-and-verification.md)
- open: [Should a local evidence copy failure abort the write instead of letting verification continue?](chapters/04-trust-identity-and-verification.md)
- open: [Should quarantine be allowed to overwrite verified or complete task status?](chapters/04-trust-identity-and-verification.md)
- open: [Should usage import stay permissive on matching and placeholder hydration, or should it require an exact match and append-only writes?](chapters/04-trust-identity-and-verification.md)
- open: [Should manual usage entries stay as a separate direct-write path, or should every usage row be normalized around imported session records?](chapters/05-sessions-usage-and-accountability.md)
- open: [Should session import keep its permissive matching and fallback behavior, or should it require one exact source session?](chapters/05-sessions-usage-and-accountability.md)
- open: [Should closeout keep the automatic fallback to assigned when usage ends, or should every closeout require an explicit final state?](chapters/05-sessions-usage-and-accountability.md)
- open: [Should the generated brief remain the canonical handoff text for the next harness?](chapters/06-running-a-multi-harness-workflow.md)
- open: [Should task-bound writes keep the implicit current-task fallback, or should the manual require explicit task selection in high-risk work?](chapters/06-running-a-multi-harness-workflow.md)
- open: [Should session end be allowed to override the fallback assignment when usage closes, or should usage closeout and task status stay strictly coupled?](chapters/06-running-a-multi-harness-workflow.md)
- open: [Should usage import stay permissive about session matching and placeholder hydration, or should the owner require stricter selection rules?](chapters/06-running-a-multi-harness-workflow.md)
- open: [Should the manual keep describing this as a local ledger workflow unless broader system boundaries are confirmed?](chapters/06-running-a-multi-harness-workflow.md)
