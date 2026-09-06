/**
 * Read-only orientation helpers for /op:next-steps, /op:project, and
 * optional workflow-strictness guidance (POE-FUT-010/011/013).
 *
 * Pure functions: no pi imports, no ledger writes, no execution of stored
 * verification commands. index.ts reuses the existing argv builders and
 * parsers in core.ts; this file only ranks and formats already-read state.
 */

import {
	describeOrigin,
	truncate,
	type ClaimRow,
	type IdentityPolicy,
	type Report,
	type ReportLevel,
	type RoadmapIssue,
	type RoadmapPbc,
	type TaskOrigin,
	type TaskRow,
	type TaskShowSummary,
} from "../core.ts";

export const WORKFLOW_MODES = ["unset", "support", "engineering-light", "engineering-trust"] as const;
export type WorkflowMode = (typeof WORKFLOW_MODES)[number];

export const VERIFICATION_KINDS = ["approval", "advisory", "uid-isolated"] as const;
export type VerificationKind = (typeof VERIFICATION_KINDS)[number];

export const ORIENTATION_MESSAGE_TYPE = "operator-orientation";

const TERMINAL_STATUSES = new Set(["verified", "complete", "completed", "closed", "done"]);
const CLAIM_VERIFIED_RE = /^verified$/i;
const CLAIM_QUARANTINED_RE = /^quarantined$/i;
const CLAIMS_CELL_RE = /V:(\d+)\s*Q:(\d+)\s*O:(\d+)/i;
const HANDOFF_GO_RE = /\/(?:op:)?handoff(?:\s+go)?\b/i;
const CLAIM_ID_IN_TEXT_RE = /claim-[0-9]{4,}/g;

export interface NextStepsArgs {
	popup: boolean;
	mode: WorkflowMode;
	unknown: string[];
}

export function parseNextStepsArgs(args: string): NextStepsArgs {
	const tokens = args.trim().split(/\s+/).filter(Boolean);
	let popup = false;
	let mode: WorkflowMode = "unset";
	const unknown: string[] = [];
	for (const token of tokens) {
		const k = token.toLowerCase();
		if (k === "popup" || k === "choose" || k === "select") {
			popup = true;
			continue;
		}
		const fromFlag = /^mode=(.+)$/.exec(k);
		const rawMode = fromFlag ? fromFlag[1] : k;
		if (rawMode === "support" || rawMode === "deliverable" || rawMode === "support/deliverable") {
			mode = "support";
			continue;
		}
		if (rawMode === "engineering-light" || rawMode === "light") {
			mode = "engineering-light";
			continue;
		}
		if (rawMode === "engineering-trust" || rawMode === "trust") {
			mode = "engineering-trust";
			continue;
		}
		if (rawMode === "unset" || rawMode === "none") {
			mode = "unset";
			continue;
		}
		unknown.push(token);
	}
	return { popup, mode, unknown };
}

export interface ProjectArgs {
	prefix: string | null;
	error: string | null;
}

/**
 * Parse /op:project args or /op:roadmap --project args.
 *
 * Extra tokens are treated as ambiguous rather than silently using the first.
 * Flag-shaped values are refused so they cannot be mistaken for a prefix.
 */
export function parseProjectArgs(args: string): ProjectArgs {
	const tokens = args.trim().split(/\s+/).filter(Boolean);
	const filtered: string[] = [];
	for (let i = 0; i < tokens.length; i += 1) {
		const t = tokens[i];
		if (t === "--project" || t === "project") {
			if (i + 1 < tokens.length && !tokens[i + 1].startsWith("-") && tokens[i + 1] !== "project") {
				filtered.push(tokens[i + 1]);
				i += 1;
			}
			continue;
		}
		filtered.push(t);
	}
	if (filtered.length === 0) {
		return { prefix: null, error: "Project prefix required. Example: /op:project pi-operator-extension" };
	}
	if (filtered.length > 1) {
		return {
			prefix: null,
			error: `Ambiguous project prefix: extra tokens ${filtered
				.slice(1)
				.map((t) => `'${t}'`)
				.join(", ")}. Pass one prefix.`,
		};
	}
	const prefix = filtered[0];
	if (prefix.startsWith("-")) {
		return { prefix: null, error: `Refusing flag-shaped prefix '${prefix}'.` };
	}
	if (!/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(prefix)) {
		return { prefix: null, error: `Refusing project prefix '${prefix}': expected [A-Za-z0-9][A-Za-z0-9._-]*` };
	}
	return { prefix, error: null };
}

export function isClaimVerified(status: string): boolean {
	return CLAIM_VERIFIED_RE.test(status.trim());
}

export function isClaimQuarantined(status: string): boolean {
	return CLAIM_QUARANTINED_RE.test(status.trim());
}

export interface ClaimsCell {
	verified: number;
	quarantined: number;
	open: number;
	total: number;
	parsed: boolean;
}

export function parseClaimsCell(cell: string): ClaimsCell {
	const m = CLAIMS_CELL_RE.exec(cell.trim());
	if (!m) {
		return { verified: 0, quarantined: 0, open: 0, total: 0, parsed: false };
	}
	const verified = Number(m[1]);
	const quarantined = Number(m[2]);
	const open = Number(m[3]);
	return { verified, quarantined, open, total: verified + quarantined + open, parsed: true };
}

export function normalizeNextAction(raw: string | null | undefined): string | null {
	const v = (raw ?? "").trim();
	if (!v || v === "None" || v === "N/A" || v === "null" || v === "~") return null;
	return v;
}

export function isTerminalTaskStatus(status: string | null | undefined): boolean {
	return TERMINAL_STATUSES.has((status ?? "").trim().toLowerCase());
}

export interface StaleNextAction {
	stale: boolean;
	reasons: string[];
}

/**
 * Explicit stale-action detector. Conservative: only flags next_action text
 * that names work the current records already show as done. Owner decisions
 * to proceed to a later slice are not stale.
 */
export function detectStaleNextAction(input: {
	nextAction: string | null;
	status: string | null;
	claims: ClaimRow[];
	evidenceCount: number;
	handoffCount: number;
}): StaleNextAction {
	const next = normalizeNextAction(input.nextAction);
	if (!next) return { stale: false, reasons: [] };
	const reasons: string[] = [];
	const verifiedIds = new Set(input.claims.filter((c) => isClaimVerified(c.status)).map((c) => c.id));
	const mentioned = next.match(CLAIM_ID_IN_TEXT_RE) ?? [];
	if (mentioned.length > 0 && mentioned.every((id) => verifiedIds.has(id))) {
		const verifyish = /\bverif/i.test(next);
		if (verifyish) {
			reasons.push(`next_action names only already-VERIFIED claim(s) (${mentioned.join(", ")})`);
		}
	}
	if (HANDOFF_GO_RE.test(next) && input.handoffCount > 0) {
		reasons.push("next_action recommends /op:handoff go after a handoff is already recorded");
	}
	if (isTerminalTaskStatus(input.status)) {
		if (/\/op:claim\b/i.test(next) && input.claims.length > 0) {
			reasons.push("task is already in a terminal status and next_action still recommends /op:claim");
		}
		if (/\/op:evidence\b/i.test(next) && input.evidenceCount > 0) {
			reasons.push("task is already in a terminal status and next_action still recommends /op:evidence");
		}
	}
	return { stale: reasons.length > 0, reasons };
}

export interface PrioritizedAction {
	/** 1-based display order. Stable for a given input. */
	priority: number;
	kind:
		| "empty-ledger"
		| "no-task"
		| "next_action"
		| "unverified-claim"
		| "missing-gate"
		| "dogfood"
		| "future";
	text: string;
	stale: boolean;
	authority: VerificationKind | "none";
}

export interface NextStepsInput {
	roadmap: RoadmapPbc;
	activeTask: string | null;
	activeOrigin: TaskOrigin;
	taskShow: TaskShowSummary | null;
	claims: ClaimRow[];
	invocations: string[];
	identity?: IdentityPolicy | null;
	taskCount?: number | null;
	mode?: WorkflowMode;
}

function identityMode(identity: IdentityPolicy | null | undefined): string {
	return (identity?.mode ?? "").trim() || "unknown";
}

function enforced(identity: IdentityPolicy | null | undefined): boolean {
	return identityMode(identity) === "enforced";
}

/**
 * The three verification kinds this surface must keep distinct.
 * Workflow guidance may describe them; it may not collapse them.
 */
export function verificationKindNotes(identity: IdentityPolicy | null | undefined): string[] {
	const mode = identityMode(identity);
	return [
		"Verification kinds (not interchangeable):",
		"  1. Approval / user acceptance: a deliverable sign-off. Not verification and not a ledger status write.",
		"  2. Advisory review: same-UID or advisory-agent notes. Recorded as advisory; not trusted verification.",
		mode === "enforced"
			? "  3. UID-isolated verification: a registered verifier UID distinct from the claim author. Enforced identity policy is unchanged by this guidance."
			: "  3. UID-isolated verification: a registered verifier UID distinct from the claim author. This ledger is not in enforced mode, so recorded status is still advisory unless that distinct UID actually writes it.",
	];
}

export function workflowGuidanceLines(mode: WorkflowMode, identity: IdentityPolicy | null | undefined): string[] {
	if (mode === "unset") return [];
	const lines = ["", `Workflow guidance (${mode}) — recommendations only, not a gate and not authority.`];
	if (mode === "support") {
		lines.push(
			"support/deliverable: user acceptance may close the deliverable for the owner.",
			"User acceptance is not verification and does not mark a claim verified.",
			"This mode adds no mandatory ceremony and does not weaken enforced UID policy.",
		);
	} else if (mode === "engineering-light") {
		lines.push(
			"engineering-light: expect tests plus claim, evidence, and handoff.",
			"Advisory review notes are optional commentary, not trusted verification.",
			"This mode does not auto-close the task and does not emit lifecycle flags.",
		);
	} else if (mode === "engineering-trust") {
		lines.push(
			"engineering-trust: expect PBC/spec, distinct-agent review, evidence, and a distinct verifier UID.",
			"Same-UID advisory review cannot satisfy engineering-trust.",
			"User acceptance cannot substitute for UID-isolated verification.",
		);
	}
	if (enforced(identity)) {
		lines.push("Identity mode is enforced: workflow guidance cannot downgrade UID-isolated verification to advisory or approval.");
	}
	return lines;
}

function recommendedVerificationAuthority(
	identity: IdentityPolicy | null | undefined,
	mode: WorkflowMode,
): VerificationKind {
	if (mode === "support") return "approval";
	if (enforced(identity) || mode === "engineering-trust") return "uid-isolated";
	return "advisory";
}

function authorityLabel(kind: VerificationKind): string {
	switch (kind) {
		case "approval":
			return "approval/user-acceptance (not verification)";
		case "advisory":
			return "advisory review (not trusted verification)";
		case "uid-isolated":
			return "UID-isolated verification (distinct registered verifier UID)";
	}
}

export function prioritizeNextActions(input: NextStepsInput): PrioritizedAction[] {
	const mode = input.mode ?? "unset";
	const taskCount = input.taskCount ?? null;
	if (taskCount === 0) {
		return [
			{
				priority: 1,
				kind: "empty-ledger",
				text: "Empty ledger: no tasks. Create one with ./operator task-create (not through this read-only command).",
				stale: false,
				authority: "none",
			},
		];
	}
	if (!input.activeTask) {
		return [
			{
				priority: 1,
				kind: "no-task",
				text: "No active task. Run /op:tasks then /op:use <task-id>.",
				stale: false,
				authority: "none",
			},
		];
	}

	const f = input.taskShow?.fields ?? {};
	const next = normalizeNextAction(f["Next Action"]);
	const evidenceCount = input.taskShow?.evidence ?? 0;
	const handoffCount = input.taskShow?.handoffs ?? 0;
	const stale = detectStaleNextAction({
		nextAction: next,
		status: f.Status ?? null,
		claims: input.claims,
		evidenceCount,
		handoffCount,
	});
	const unverified = input.claims.filter((c) => !isClaimVerified(c.status) && !isClaimQuarantined(c.status));
	const quarantined = input.claims.filter((c) => isClaimQuarantined(c.status));
	const reviewHarness = (f["Review Harness"] ?? "").trim();
	const hasReviewHarness = Boolean(reviewHarness) && reviewHarness !== "None" && reviewHarness !== "N/A";
	const actions: PrioritizedAction[] = [];

	if (next) {
		actions.push({
			priority: 0,
			kind: "next_action",
			text: stale.stale
				? `STALE ledger next_action (do not follow blindly): ${truncate(next, 240)} — ${stale.reasons.join("; ")}`
				: `Current ledger next_action: ${truncate(next, 240)}`,
			stale: stale.stale,
			authority: "none",
		});
	} else {
		actions.push({
			priority: 0,
			kind: "next_action",
			text: "No ledger next_action is recorded for this task.",
			stale: false,
			authority: "none",
		});
	}

	if (unverified.length > 0) {
		const ids = unverified.map((c) => c.id).join(", ");
		const needed = recommendedVerificationAuthority(input.identity, mode);
		actions.push({
			priority: 0,
			kind: "unverified-claim",
			text:
				`Unverified claim(s): ${ids}. ` +
				`Needed for trusted closeout: ${authorityLabel(needed)}. ` +
				`Suggested review wrap: /op:supervisor-review ${unverified[unverified.length - 1]!.id} ` +
				`(writes a bundle; does not verify).`,
			stale: false,
			authority: needed,
		});
	} else if (input.claims.length > 0 && quarantined.length === 0) {
		actions.push({
			priority: 0,
			kind: "unverified-claim",
			text: "No unverified claims on this task. Remaining closeout is still not automatic: user acceptance is not verification.",
			stale: false,
			authority: "approval",
		});
	}

	if (unverified.length > 0 && evidenceCount === 0) {
		actions.push({
			priority: 0,
			kind: "missing-gate",
			text: "Missing evidence gate: unverified claims and no evidence records on this task. Attach a rerunnable artifact with /op:evidence (does not verify).",
			stale: false,
			authority: "none",
		});
	}
	if (unverified.length > 0 && !hasReviewHarness) {
		actions.push({
			priority: 0,
			kind: "missing-gate",
			text: "Missing review gate: unverified claims and no review_harness on this task. review_harness is routing only; trusted verification still needs a distinct verifier UID.",
			stale: false,
			authority: "uid-isolated",
		});
	}
	if (quarantined.length > 0) {
		actions.push({
			priority: 0,
			kind: "missing-gate",
			text: `Quarantined claim(s): ${quarantined.map((c) => c.id).join(", ")}. Quarantine is not verification and is not user acceptance.`,
			stale: false,
			authority: "none",
		});
	}

	const issues = [...input.roadmap.issues].sort((a, b) => a.id.localeCompare(b.id));
	for (const issue of issues.slice(-3)) {
		actions.push({
			priority: 0,
			kind: "dogfood",
			text: `Recent dogfood issue ${issue.id}: ${truncate(issue.nextStep, 200)}`,
			stale: false,
			authority: "none",
		});
	}

	const futures = [...input.roadmap.futureFeatures].sort((a, b) => a.id.localeCompare(b.id));
	if (futures.length > 0) {
		const shown = futures.slice(0, 5);
		actions.push({
			priority: 0,
			kind: "future",
			text: `Future slices in PBC id order (not current acceptance): ${shown
				.map((f) => (f.command ? `${f.id} ${f.command}` : f.id))
				.join(", ")}${futures.length > shown.length ? ` (+${futures.length - shown.length} more)` : ""}.`,
			stale: false,
			authority: "none",
		});
	}

	return actions.map((a, i) => ({ ...a, priority: i + 1 }));
}

export function buildNextStepsReport(input: NextStepsInput): Report {
	const mode = input.mode ?? "unset";
	const actions = prioritizeNextActions(input);
	const lines: string[] = [];
	const f = input.taskShow?.fields ?? {};
	lines.push(`Showing task: ${input.activeTask ?? "(none)"} - from ${describeOrigin(input.activeOrigin)}`);
	if (input.taskCount !== null && input.taskCount !== undefined) {
		lines.push(`Tasks in ledger: ${input.taskCount} (excluding eval-* cells)`);
	}
	if (f.Status) lines.push(`Task status: ${f.Status}`);
	if (mode !== "unset") lines.push(`Workflow mode: ${mode} (guidance only)`);
	lines.push("", "Recommended next steps");
	for (const action of actions) {
		const staleMark = action.stale ? " [stale warning]" : "";
		lines.push(`${action.priority}. ${action.text}${staleMark}`);
	}
	lines.push("", ...verificationKindNotes(input.identity ?? null));
	lines.push(...workflowGuidanceLines(mode, input.identity ?? null));
	lines.push(
		"",
		"This is guidance only. It does not execute stored verification commands, write the ledger, or change identity policy.",
	);
	const staleCount = actions.filter((a) => a.stale).length;
	const headline = !input.activeTask
		? taskCountHeadline(input.taskCount)
		: staleCount > 0
			? `next steps for ${input.activeTask} (${staleCount} stale warning${staleCount === 1 ? "" : "s"})`
			: `next steps for ${input.activeTask}`;
	const level: ReportLevel = actions.some((a) => a.kind === "empty-ledger" || a.kind === "no-task")
		? "warning"
		: staleCount > 0
			? "warning"
			: "info";
	return {
		command: "/op:next-steps",
		title: "Operator next steps",
		headline,
		level,
		lines,
		invocations: input.invocations,
	};
}

function taskCountHeadline(taskCount: number | null | undefined): string {
	if (taskCount === 0) return "empty ledger";
	return "no active task selected";
}

export function numberedActionLines(report: Report): string[] {
	return report.lines.filter((line) => /^\d+\.\s/.test(line));
}

export function orientationAgentContent(report: Report): string {
	return [`${report.title}: ${report.headline}`, ...report.lines].join("\n");
}

/**
 * Custom message payload for pi.sendMessage. Pi docs: custom messages
 * participate in LLM context; appendEntry custom entries do not.
 * deliverAs nextTurn queues the text for the next prompt without
 * triggering a turn.
 */
export function orientationSendMessage(report: Report): {
	message: {
		customType: string;
		content: string;
		display: boolean;
		details: { command: string; headline: string; level: ReportLevel };
	};
	options: { deliverAs: "nextTurn" };
} {
	return {
		message: {
			customType: ORIENTATION_MESSAGE_TYPE,
			content: orientationAgentContent(report),
			display: false,
			details: { command: report.command, headline: report.headline, level: report.level },
		},
		options: { deliverAs: "nextTurn" },
	};
}

export interface PrefixMatch {
	matches: TaskRow[];
	families: string[];
	incompleteBoundary: boolean;
	ambiguousFamilies: boolean;
	warnings: string[];
}

export function matchTasksByPrefix(rows: TaskRow[], prefix: string): PrefixMatch {
	const sorted = [...rows].sort((a, b) => a.id.localeCompare(b.id));
	const loose = sorted.filter((r) => r.id === prefix || r.id.startsWith(prefix));
	const bounded = sorted.filter((r) => r.id === prefix || r.id.startsWith(`${prefix}-`) || r.id.startsWith(`${prefix}.`));
	const incompleteBoundary = loose.length > 0 && bounded.length === 0;
	const matches = incompleteBoundary ? loose : bounded;
	const families = [...new Set(matches.map((r) => twoSegmentFamily(r.id)))].sort();
	const prefixTokens = prefix.split(/[-.]/).filter(Boolean).length;
	const ambiguousFamilies = prefixTokens < 2 && families.length > 1;
	const warnings: string[] = [];
	if (incompleteBoundary) {
		warnings.push(
			`Prefix '${prefix}' is not a complete task-id token boundary; listing startswith matches lexicographically (not a project phase order).`,
		);
	}
	if (ambiguousFamilies) {
		warnings.push(
			`Prefix '${prefix}' spans multiple task-id families (${families.join(", ")}). Listed lexicographically; this is not a project phase order.`,
		);
	}
	return { matches, families, incompleteBoundary, ambiguousFamilies, warnings };
}

function twoSegmentFamily(id: string): string {
	const parts = id.split("-");
	if (parts.length < 2) return id;
	return `${parts[0]}-${parts[1]}`;
}

export interface ProjectTaskSnapshot {
	row: TaskRow;
	taskShow: TaskShowSummary | null;
	claims: ClaimRow[];
}

export interface ProjectDashboardInput {
	prefix: string;
	match: PrefixMatch;
	snapshots: ProjectTaskSnapshot[];
	roadmap: RoadmapPbc;
	activeTask: string | null;
	invocations: string[];
	identity?: IdentityPolicy | null;
}

export function latestVerifiedClaim(claims: ClaimRow[]): ClaimRow | null {
	const verified = claims.filter((c) => isClaimVerified(c.status)).sort((a, b) => a.id.localeCompare(b.id));
	return verified[verified.length - 1] ?? null;
}

export function issuesForPrefix(issues: RoadmapIssue[], prefix: string, taskIds: string[]): RoadmapIssue[] {
	const ids = new Set(taskIds);
	return [...issues]
		.filter((issue) => {
			const blob = `${issue.id} ${issue.summary} ${issue.nextStep}`;
			if (blob.includes(prefix)) return true;
			for (const id of ids) {
				if (blob.includes(id)) return true;
			}
			return false;
		})
		.sort((a, b) => a.id.localeCompare(b.id));
}

export function buildProjectDashboardReport(input: ProjectDashboardInput): Report {
	const lines: string[] = [];
	lines.push(`Project prefix: ${input.prefix}`);
	lines.push("Grouping: lexicographic task-id prefix match. Not a project phase order (no phase metadata on these tasks).");
	for (const warning of input.match.warnings) lines.push(`Warning: ${warning}`);

	if (input.match.matches.length === 0) {
		lines.push("", `No tasks match prefix '${input.prefix}'.`);
		lines.push("Empty prefix matches are not inferred from the active task.");
		return {
			command: "/op:project",
			title: "Operator project dashboard",
			headline: `no tasks match prefix '${input.prefix}'`,
			level: "warning",
			lines,
			invocations: input.invocations,
		};
	}

	lines.push(`Matches: ${input.match.matches.length} task(s)`);
	if (input.match.families.length > 0) {
		lines.push(`Task-id families (inferred from ids, not phases): ${input.match.families.join(", ")}`);
	}
	lines.push("");
	lines.push(
		["TASK ID", "STATUS", "CLAIMS V/T", "EVID", "HAND", "LATEST VERIFIED", "OPEN", "NEXT"].map((h, i) =>
			h.padEnd([36, 12, 12, 5, 5, 16, 5, 24][i] ?? 8),
		).join(" ").trimEnd(),
	);

	let staleTasks = 0;
	const snapshotById = new Map(input.snapshots.map((s) => [s.row.id, s]));
	for (const row of input.match.matches) {
		const snap = snapshotById.get(row.id);
		const claims = snap?.claims ?? [];
		const cell = parseClaimsCell(row.claims);
		const verified = cell.parsed ? cell.verified : claims.filter((c) => isClaimVerified(c.status)).length;
		const total = cell.parsed ? cell.total : claims.length;
		const evidence = snap?.taskShow?.evidence ?? 0;
		const handoffs = snap?.taskShow?.handoffs ?? 0;
		const latest = latestVerifiedClaim(claims);
		const assumptions = snap?.taskShow?.assumptions ?? 0;
		const next = normalizeNextAction(row.nextAction) ?? normalizeNextAction(snap?.taskShow?.fields["Next Action"] ?? null);
		const stale = detectStaleNextAction({
			nextAction: next,
			status: row.status,
			claims,
			evidenceCount: evidence,
			handoffCount: handoffs,
		});
		if (stale.stale) staleTasks += 1;
		const nextCell = stale.stale ? `STALE: ${truncate(next ?? "", 40)}` : truncate(next ?? "(none)", 40);
		lines.push(
			[
				row.id.padEnd(36),
				row.status.padEnd(12),
				`${verified}/${total}`.padEnd(12),
				String(evidence).padEnd(5),
				String(handoffs).padEnd(5),
				(latest?.id ?? "(none)").padEnd(16),
				String(assumptions).padEnd(5),
				nextCell,
			].join(" "),
		);
		if (stale.stale) {
			for (const reason of stale.reasons) lines.push(`    stale: ${reason}`);
		}
	}

	const issueHits = issuesForPrefix(
		input.roadmap.issues,
		input.prefix,
		input.match.matches.map((r) => r.id),
	);
	lines.push("", "Open issues");
	if (issueHits.length === 0) {
		lines.push("  (none from the PBC dogfood backlog matching this prefix)");
	} else {
		for (const issue of issueHits) {
			lines.push(`  - ${issue.id}: ${truncate(issue.summary, 160)}`);
		}
	}

	const focusId =
		input.activeTask && input.match.matches.some((r) => r.id === input.activeTask)
			? input.activeTask
			: input.match.matches[0]!.id;
	const focusSnap = snapshotById.get(focusId);
	if (focusSnap) {
		const focusActions = prioritizeNextActions({
			roadmap: input.roadmap,
			activeTask: focusId,
			activeOrigin: input.activeTask === focusId ? "session" : "none",
			taskShow: focusSnap.taskShow,
			claims: focusSnap.claims,
			invocations: [],
			identity: input.identity ?? null,
			taskCount: input.match.matches.length,
			mode: "unset",
		}).filter((a) => a.kind !== "dogfood" && a.kind !== "future" && a.kind !== "empty-ledger");
		lines.push("", `Recommended next (task ${focusId}; ${input.activeTask === focusId ? "active task" : "lexicographic first match, not a phase"})`);
		for (const action of focusActions.slice(0, 4)) {
			lines.push(`  ${action.priority}. ${action.text}`);
		}
	}

	lines.push("", ...verificationKindNotes(input.identity ?? null));
	lines.push("", "Read-only dashboard. Task status was not mutated.");
	const headline = `${input.match.matches.length} task(s) for prefix '${input.prefix}'${staleTasks > 0 ? `; ${staleTasks} stale next_action` : ""}`;
	return {
		command: "/op:project",
		title: "Operator project dashboard",
		headline,
		level: staleTasks > 0 || input.match.ambiguousFamilies || input.match.incompleteBoundary ? "warning" : "info",
		lines,
		invocations: input.invocations,
	};
}

export function buildPrefixRequiredReport(error: string): Report {
	return {
		command: "/op:project",
		title: "Operator project dashboard",
		headline: "prefix required",
		level: "warning",
		lines: [
			error,
			"Grouping is a lexicographic task-id prefix match. This command does not invent a project or a phase order.",
			"Example: /op:project pi-operator-extension   or   /op:roadmap --project pi-operator-extension",
		],
		invocations: [],
	};
}
