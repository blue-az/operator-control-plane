/**
 * Operator control plane - project-local pi extension.
 *
 * Steps 1, 2, 3 and 4 of the ladder in
 * owners-manual/pbc/appendix-pi-operator-extension.pbc.md: read-only
 * orientation, authoring writes that only happen after an explicit
 * confirmation, claim-scoped supervisor-review, and chooser-first delegate.
 *
 *   /op:doctor              run ./operator doctor and report pass/fail
 *   /op:status              current task orientation and recent ledger state
 *   /op:tasks               ./operator task-list
 *   /op:use                 select a task for this pi session; writing the ledger's
 *                           current_task requires a confirmation dialog
 *   /op:claim               register a claim with a session-derived --by (step 2)
 *   /op:evidence            attach an artifact and a rerunnable --verify-cmd (step 2)
 *   /op:handoff             record closeout from an editor-first draft (step 2)
 *   /op:supervisor-review   wrap ./operator review-delegate for one named claim (step 3)
 *   /op:delegate            send bounded implementation work to another agent (step 4)
 *   /op:roadmap             show ladder, recent dogfood issues, and future features
 *   /op:next-steps          summarize the active task's recommended next actions
 *
 * Deliberately absent at step 4: the /pbc:* commands. Also absent: any
 * model-callable tool. These commands are human ergonomics (POE-RUL-103);
 * the model still has bash and can run ./operator itself under its own
 * rules, and does not get a shortcut here for authoring claims about its
 * own work or marking them verified.
 *
 * Authority boundaries this file must keep:
 *   - argv is always built by core.ts from a fixed allowlist, never from user
 *     text, and never contains --status, --verified-by or --verdict
 *     (POE-RUL-104/113);
 *   - every invocation names its task explicitly instead of leaning on the
 *     ledger's current_task (POE-RUL-112);
 *   - --by is derived from the pi session id and is provenance only; no
 *     verifier identity, harness id or reviewer is ever derived from it
 *     (POE-RUL-102, review finding F5);
 *   - the session selection is display state; the ledger stays the source of
 *     truth and both values are always shown side by side (POE-RUL-101);
 *   - reports are terminal output, not evidence (POE-RUL-105);
 *   - every write is previewed as an exact ./operator invocation and confirmed
 *     before it runs, and a decline is reported as loudly as a write.
 */

import { existsSync, readdirSync } from "node:fs";

import type { ExtensionAPI, ExtensionCommandContext } from "@earendil-works/pi-coding-agent";
import { REPORT_ENTRY_TYPE } from "./core.ts";
import * as core from "./core.ts";

/** Session-scoped task selection. Never written to the ledger on its own. */
let sessionTask: string | null = null;

const SELECTION_ENTRY_TYPE = "operator-task-selection";

interface Runner {
	exec(command: string, args: string[], options?: { cwd?: string; timeout?: number }): Promise<{
		stdout: string;
		stderr: string;
		code: number;
	}>;
}

/** Run one allowlisted ./operator invocation. */
async function runOperator(pi: Runner, ledger: core.Ledger, argv: string[]): Promise<core.CommandResult> {
	core.assertSafeArgv(argv);
	const result = await pi.exec(ledger.operatorBin, argv, { cwd: ledger.root, timeout: 120_000 });
	return { stdout: result.stdout, stderr: result.stderr, code: result.code };
}

/**
 * Resolve the ledger or explain why we will not guess. Returns null after
 * notifying, so callers just bail.
 */
function requireLedger(ctx: ExtensionCommandContext): core.Ledger | null {
	const ledger = core.findLedger(ctx.cwd);
	if (!ledger) {
		ctx.ui.notify(
			`No Operator ledger above ${ctx.cwd}: need a directory holding both ${core.LEDGER_DIR}/ and an executable 'operator'.`,
			"error",
		);
		return null;
	}
	return ledger;
}

/** The task these commands act on, and where that choice came from. */
function resolveActiveTask(ledger: core.Ledger): { taskId: string | null; origin: core.TaskOrigin } {
	if (sessionTask) return { taskId: sessionTask, origin: "session" };
	const current = core.readLedgerCurrentTask(ledger);
	if (current) return { taskId: current, origin: "ledger" };
	return { taskId: null, origin: "none" };
}

/**
 * Everything an authoring write needs before it may ask the user anything:
 * a ledger, a UI, a task that exists on disk, and a session-derived --by.
 *
 * All four fail closed with an explanation rather than a default. In
 * particular there is no fallback author label: a write whose provenance
 * cannot be derived from the session is not written at all (POE-RUL-102).
 */
interface WriteContext {
	ledger: core.Ledger;
	taskId: string;
	origin: core.TaskOrigin;
	by: string;
}

function requireWriteContext(ctx: ExtensionCommandContext, command: string): WriteContext | null {
	const ledger = requireLedger(ctx);
	if (!ledger) return null;
	if (!ctx.hasUI) {
		ctx.ui.notify(
			`${command} is a guided flow and needs a UI. Run ./operator directly for a non-interactive write.`,
			"error",
		);
		return null;
	}
	const { taskId, origin } = resolveActiveTask(ledger);
	if (!taskId) {
		ctx.ui.notify(`${command} needs a task. Run /op:tasks then /op:use <task-id>.`, "error");
		return null;
	}
	if (!core.taskRecordExists(ledger, taskId)) {
		ctx.ui.notify(`No task record at ${core.LEDGER_DIR}/tasks/${taskId}.yaml. Refusing to write against it.`, "error");
		return null;
	}
	const by = core.deriveAuthorLabel(sessionId(ctx));
	if (!by) {
		ctx.ui.notify(
			`${command} could not derive a session-scoped --by label, so it will not write unattributed provenance.`,
			"error",
		);
		return null;
	}
	return { ledger, taskId, origin, by };
}

/** The pi session id, when the runtime exposes one. Never invented. */
function sessionId(ctx: ExtensionCommandContext): string | null {
	try {
		const id = ctx.sessionManager.getSessionId();
		return typeof id === "string" && id.length > 0 ? id : null;
	} catch {
		return null;
	}
}

/**
 * Ask an optional free-text question.
 *
 * Escape (undefined) cancels the whole flow; an empty submission means "none".
 * Returns null for cancel so callers can tell the two apart.
 */
async function askOptional(ctx: ExtensionCommandContext, title: string, placeholder?: string): Promise<string | null> {
	const answer = await ctx.ui.input(`${title} (empty = none, escape = cancel)`, placeholder);
	return answer === undefined ? null : answer.trim();
}

export default async function operatorExtension(pi: ExtensionAPI) {
	// The renderer is the only thing that needs pi-tui. Keep its failure
	// non-fatal so the commands still work under a bare loader, but say so
	// once rather than leaving the user staring at an empty transcript.
	let rendererError: string | null = null;
	try {
		const render = await import("./render.ts");
		render.registerReportRenderer(pi);
	} catch (err) {
		rendererError = err instanceof Error ? err.message : String(err);
	}
	let rendererWarned = false;

	const emit = (ctx: ExtensionCommandContext, report: core.Report) => {
		pi.appendEntry(REPORT_ENTRY_TYPE, report);
		if (!ctx.hasUI) return;
		if (rendererError && !rendererWarned) {
			rendererWarned = true;
			ctx.ui.notify(`Operator reports will not render in the transcript: ${rendererError}`, "warning");
		}
		ctx.ui.notify(`${report.command} ${report.headline}`, report.level);
	};

	// Restore the session selection after /reload or a session restart.
	pi.on("session_start", async (_event, ctx) => {
		sessionTask = null;
		for (const entry of ctx.sessionManager.getEntries()) {
			if (entry.type === "custom" && entry.customType === SELECTION_ENTRY_TYPE) {
				const data = entry.data as { taskId?: string | null } | undefined;
				sessionTask = data?.taskId ?? null;
			}
		}
	});

	pi.registerCommand("op:doctor", {
		description: "Operator: run ./operator doctor (read-only consistency check)",
		handler: async (_args, ctx) => {
			const ledger = requireLedger(ctx);
			if (!ledger) return;
			const argv = core.doctorArgv();
			ctx.ui.setStatus("operator", "running ./operator doctor…");
			ctx.ui.notify("Running ./operator doctor; this ledger is large and may take a moment.", "info");
			try {
				const summary = core.summarizeDoctor(await runOperator(pi, ledger, argv));
				emit(ctx, core.buildDoctorReport(summary));
			} finally {
				ctx.ui.setStatus("operator", undefined);
			}
		},
	});

	pi.registerCommand("op:status", {
		description: "Operator: current task orientation and recent ledger state (read-only)",
		handler: async (_args, ctx) => {
			const ledger = requireLedger(ctx);
			if (!ledger) return;
			ctx.ui.setStatus("operator", "building /op:status…");
			ctx.ui.notify("Building Operator status; task summary and doctor can be slow on this ledger.", "info");
			try {
			const { taskId, origin } = resolveActiveTask(ledger);
			const invocations: string[] = [];
			const notes: string[] = [];

			let taskShow: core.TaskShowSummary | null = null;
			let claims: core.ClaimRow[] = [];
			let sessionCount: number | null = null;

			if (taskId) {
				if (!core.taskRecordExists(ledger, taskId)) {
					notes.push(`No record at ${core.LEDGER_DIR}/tasks/${taskId}.yaml; showing ledger-wide state only.`);
				} else {
					const showArgv = core.taskShowArgv(taskId);
					invocations.push(core.formatInvocation(showArgv));
					taskShow = core.parseTaskShow((await runOperator(pi, ledger, showArgv)).stdout);

					const claimArgv = core.claimListArgv(taskId);
					invocations.push(core.formatInvocation(claimArgv));
					claims = core.parseClaimList((await runOperator(pi, ledger, claimArgv)).stdout);

					const sessionArgv = core.sessionListArgv(taskId);
					invocations.push(core.formatInvocation(sessionArgv));
					sessionCount = core.countSessionRows((await runOperator(pi, ledger, sessionArgv)).stdout);
				}
			} else {
				notes.push("No task selected. Run /op:tasks then /op:use <task-id>.");
			}

			const listArgv = core.taskListArgv();
			invocations.push(core.formatInvocation(listArgv));
			const taskCount = core.parseTaskList((await runOperator(pi, ledger, listArgv)).stdout).length;

			const doctorArgv = core.doctorArgv();
			invocations.push(core.formatInvocation(doctorArgv));
			const doctor = core.summarizeDoctor(await runOperator(pi, ledger, doctorArgv));

			emit(
				ctx,
				core.buildStatusReport({
					ledgerRoot: ledger.root,
					sessionTask,
					ledgerCurrentTask: core.readLedgerCurrentTask(ledger),
					activeTask: taskId,
					activeOrigin: origin,
					taskShow,
					claims,
					sessionCount,
					doctor,
					taskCount,
					invocations,
					notes,
				}),
			);
			} finally {
				ctx.ui.setStatus("operator", undefined);
			}
		},
	});

	pi.registerCommand("op:next-steps", {
		description: "Operator: show prioritized next actions for the active task (read-only; add 'popup' for chooser)",
		handler: async (args, ctx) => {
			const ledger = requireLedger(ctx);
			if (!ledger) return;
			const { taskId, origin } = resolveActiveTask(ledger);
			const invocations: string[] = [];
			let taskShow: core.TaskShowSummary | null = null;
			let claims: core.ClaimRow[] = [];
			if (taskId && core.taskRecordExists(ledger, taskId)) {
				const showArgv = core.taskShowArgv(taskId);
				invocations.push(core.formatInvocation(showArgv));
				taskShow = core.parseTaskShow((await runOperator(pi, ledger, showArgv)).stdout);
				const claimArgv = core.claimListArgv(taskId);
				invocations.push(core.formatInvocation(claimArgv));
				claims = core.parseClaimList((await runOperator(pi, ledger, claimArgv)).stdout);
			}
			try {
				const report = core.buildNextStepsReport({
					roadmap: core.readPiOperatorRoadmap(ledger.root),
					activeTask: taskId,
					activeOrigin: origin,
					taskShow,
					claims,
					invocations,
				});
				const wantsPopup = ["popup", "choose", "select"].includes(args.trim().toLowerCase());
				if (wantsPopup && ctx.hasUI) {
					const choices = report.lines.filter((line) => /^\d+\.\s/.test(line));
					if (choices.length > 0) {
						const picked = await ctx.ui.select("Operator next steps", choices);
						if (picked) ctx.ui.notify(`Selected next step: ${picked}`, "info");
					}
				}
				emit(ctx, report);
			} catch (err) {
				refuse(ctx, "/op:next-steps", "Operator next steps", err);
			}
		},
	});

	pi.registerCommand("op:roadmap", {
		description: "Operator: show implementation ladder, current step, dogfood issues, and future features",
		handler: async (_args, ctx) => {
			const ledger = requireLedger(ctx);
			if (!ledger) return;
			const { taskId, origin } = resolveActiveTask(ledger);
			const invocations: string[] = [];
			let taskShow: core.TaskShowSummary | null = null;
			if (taskId && core.taskRecordExists(ledger, taskId)) {
				const argv = core.taskShowArgv(taskId);
				invocations.push(core.formatInvocation(argv));
				taskShow = core.parseTaskShow((await runOperator(pi, ledger, argv)).stdout);
			}
			try {
				emit(ctx, core.buildRoadmapReport({
					roadmap: core.readPiOperatorRoadmap(ledger.root),
					activeTask: taskId,
					activeOrigin: origin,
					taskShow,
					invocations,
				}));
			} catch (err) {
				refuse(ctx, "/op:roadmap", "Operator roadmap", err);
			}
		},
	});

	pi.registerCommand("op:tasks", {
		description: "Operator: list tasks (/op:tasks [--all] [filter])",
		handler: async (args, ctx) => {
			const ledger = requireLedger(ctx);
			if (!ledger) return;
			const tokens = args.trim().split(/\s+/).filter(Boolean);
			const all = tokens[0] === "--all" || tokens[0] === "all";
			const filter = (all ? tokens.slice(1) : tokens).join(" ");
			let argv: string[];
			try {
				argv = core.taskListArgv({ all, filter });
			} catch (err) {
				ctx.ui.notify(String(err instanceof Error ? err.message : err), "error");
				return;
			}
			const rows = core.parseTaskList((await runOperator(pi, ledger, argv)).stdout);
			const note = filter ? `filter: ${filter}${all ? " (including eval-* cells)" : ""}` : all ? "including eval-* cells" : null;
			emit(ctx, core.buildTasksReport(rows, core.formatInvocation(argv), note));
		},
	});

	pi.registerCommand("op:use", {
		description: "Operator: select a task for this pi session (/op:use [task-id])",
		getArgumentCompletions: (prefix) => {
			const ledger = core.findLedger(process.cwd());
			if (!ledger) return null;
			const ids = listTaskIds(ledger).filter((id) => id.startsWith(prefix));
			return ids.length > 0 ? ids.slice(0, 50).map((id) => ({ value: id, label: id })) : null;
		},
		handler: async (args, ctx) => {
			const ledger = requireLedger(ctx);
			if (!ledger) return;

			let taskId = args.trim();
			if (!taskId) {
				if (!ctx.hasUI) {
					ctx.ui.notify("/op:use needs a task id when there is no UI to choose from.", "error");
					return;
				}
				const listArgv = core.taskListArgv();
				const rows = core.parseTaskList((await runOperator(pi, ledger, listArgv)).stdout);
				if (rows.length === 0) {
					ctx.ui.notify("No tasks in the ledger.", "warning");
					return;
				}
				const labels = rows.map((r) => `${r.id}  [${r.status}]  assigned:${r.assigned}  ${r.claims}`);
				const picked = await ctx.ui.select("Select a task for this pi session", labels);
				if (!picked) return;
				taskId = picked.split(/\s+/)[0];
			}

			if (!core.isValidTaskId(taskId)) {
				ctx.ui.notify(`Refusing task id '${taskId}': expected a slug like pi-operator-extension-step1.`, "error");
				return;
			}
			if (!core.taskRecordExists(ledger, taskId)) {
				ctx.ui.notify(`No task record at ${core.LEDGER_DIR}/tasks/${taskId}.yaml. Not selecting it.`, "error");
				return;
			}

			sessionTask = taskId;
			pi.appendEntry(SELECTION_ENTRY_TYPE, { taskId });

			const ledgerCurrent = core.readLedgerCurrentTask(ledger);
			const lines = [
				`Session selection: ${taskId}`,
				`Ledger current_task: ${ledgerCurrent ?? "(none)"}`,
				"",
				"This selection is local to this pi session. Operator's own current_task is unchanged",
				"unless you confirm the write below.",
			];

			let wrote = false;
			if (ledgerCurrent !== taskId) {
				if (ctx.hasUI) {
					const ok = await ctx.ui.confirm(
						"Write Operator current_task?",
						`This runs ./operator task-use ${taskId} and changes the ledger's current_task ` +
							`from ${ledgerCurrent ?? "(none)"} to ${taskId}. The session selection above works without it.`,
					);
					if (ok) {
						const useArgv = core.taskUseArgv(taskId);
						const result = await runOperator(pi, ledger, useArgv);
						wrote = result.code === 0;
						lines.push(
							"",
							wrote
								? `Confirmed: ran ${core.formatInvocation(useArgv)} (current_task is now ${taskId}).`
								: `Confirmed, but ${core.formatInvocation(useArgv)} exited ${result.code}: ${core.truncate(result.stderr || result.stdout, 200)}`,
						);
					} else {
						lines.push("", "Declined: ledger current_task left as is.");
					}
				} else {
					lines.push("", "No UI available to confirm, so the ledger's current_task was left as is.");
				}
			} else {
				lines.push("", "Ledger current_task already matches; nothing to write.");
			}

			emit(ctx, {
				command: "/op:use",
				title: "Operator task selection",
				headline: wrote ? `${taskId} (session + ledger current_task)` : `${taskId} (this pi session only)`,
				level: "info",
				lines,
				invocations: wrote ? [core.formatInvocation(core.taskUseArgv(taskId))] : [],
			});
		},
	});

	// --- step 2: authoring writes -------------------------------------------
	// Each one is a guided flow ending in a confirmation dialog that shows the
	// exact ./operator invocation. Declining is recorded in the transcript.

	/** Show the planned invocation, confirm it, run it, and report the outcome. */
	const confirmAndRun = async (
		ctx: ExtensionCommandContext,
		wc: WriteContext,
		spec: {
			command: string;
			title: string;
			noun: "claim" | "evidence" | "handoff";
			argv: string[];
			plan: string[];
			detail?: (recordId: string | null) => string[];
			confirmedByArgument?: boolean;
		},
	): Promise<void> => {
		const invocation = core.formatInvocation(spec.argv);
		const ok = spec.confirmedByArgument
			? true
			: await ctx.ui.confirm(
				`Write this ${spec.noun} to the ledger?`,
				[...spec.plan, "", invocation].join("\n"),
			);
		if (!ok) {
			emit(ctx, core.buildDeclinedReport(spec.command, spec.title, "Declined at the confirmation dialog.", spec.argv));
			return;
		}
		const result = await runOperator(pi, wc.ledger, spec.argv);
		// Only a zero exit can have produced a record; an id quoted inside an
		// error message must never be read as a successful write.
		const recordId = result.code === 0 ? core.parseRecordId(result.stdout, spec.noun) : null;
		emit(
			ctx,
			core.buildWriteReport({
				command: spec.command,
				title: spec.title,
				noun: spec.noun,
				taskId: wc.taskId,
				by: wc.by,
				argv: spec.argv,
				result,
				recordId,
				detail: spec.detail ? spec.detail(recordId) : [],
			}),
		);
	};

	/** Turn a builder throw into a reported refusal instead of an unhandled rejection. */
	const refuse = (ctx: ExtensionCommandContext, command: string, title: string, err: unknown): void => {
		const message = err instanceof Error ? err.message : String(err);
		ctx.ui.notify(message, "error");
		emit(ctx, core.buildDeclinedReport(command, title, message, null));
	};

	pi.registerCommand("op:claim", {
		description: "Operator: register a claim on the selected task (/op:claim [claim text])",
		handler: async (args, ctx) => {
			const wc = requireWriteContext(ctx, "/op:claim");
			if (!wc) return;

			const type = await ctx.ui.select(`Claim type for ${wc.taskId}`, [...core.CLAIM_TYPES]);
			if (!type) {
				emit(ctx, core.buildDeclinedReport("/op:claim", "Operator claim", "No claim type chosen.", null));
				return;
			}

			const text = await ctx.ui.editor(`Claim text for ${wc.taskId} (--by=${wc.by})`, args.trim());
			if (text === undefined || !text.trim()) {
				emit(ctx, core.buildDeclinedReport("/op:claim", "Operator claim", "No claim text entered.", null));
				return;
			}

			const gate = await askOptional(ctx, "Required gate artifact path", "tests/test_operator.py");
			if (gate === null) {
				emit(ctx, core.buildDeclinedReport("/op:claim", "Operator claim", "Cancelled at the gate prompt.", null));
				return;
			}
			const verifyCmd = await askOptional(ctx, "Rerunnable verify command", "python3 -m pytest tests/ -q");
			if (verifyCmd === null) {
				emit(ctx, core.buildDeclinedReport("/op:claim", "Operator claim", "Cancelled at the verify-command prompt.", null));
				return;
			}

			let layer: string | undefined;
			if (type === "supervision_credit") {
				// FR-12: an unnamed layer is an ambiguous credit, so this one is required.
				const picked = await ctx.ui.select("Supervision layer (required for supervision_credit)", [...core.SUPERVISION_LAYERS]);
				if (!picked) {
					emit(
						ctx,
						core.buildDeclinedReport("/op:claim", "Operator claim", "A supervision_credit claim needs a --layer (FR-12).", null),
					);
					return;
				}
				layer = picked;
			}

			const opts: core.ClaimAddOptions = { taskId: wc.taskId, type, text, by: wc.by, gate, verifyCmd, layer };
			let argv: string[];
			try {
				argv = core.claimAddArgv(opts);
			} catch (err) {
				refuse(ctx, "/op:claim", "Operator claim", err);
				return;
			}

			await confirmAndRun(ctx, wc, {
				command: "/op:claim",
				title: "Operator claim",
				noun: "claim",
				argv,
				plan: core.describeClaimPlan(opts),
				detail: (recordId) =>
					recordId
						? [
								`The claim is unverified. Attach an artifact with /op:evidence, then have a distinct`,
								`identity verify it; ${recordId} stays unverified until someone else does.`,
							]
						: [],
			});
		},
	});

	pi.registerCommand("op:evidence", {
		description: "Operator: attach evidence to the selected task (/op:evidence [path-or-url])",
		handler: async (args, ctx) => {
			const wc = requireWriteContext(ctx, "/op:evidence");
			if (!wc) return;

			let raw = args.trim();
			if (!raw) {
				const answer = await ctx.ui.input("Evidence path or http(s) URL", ".operator/... or /tmp/run.log");
				if (answer === undefined || !answer.trim()) {
					emit(ctx, core.buildDeclinedReport("/op:evidence", "Operator evidence", "No evidence locator given.", null));
					return;
				}
				raw = answer.trim();
			}
			let locator: string;
			let remote: boolean;
			try {
				({ locator, remote } = core.resolveEvidenceLocator(wc.ledger, raw));
			} catch (err) {
				refuse(ctx, "/op:evidence", "Operator evidence", err);
				return;
			}

			// Claims of this task, so evidence can be bound to one rather than
			// floating at task level.
			const claimArgv = core.claimListArgv(wc.taskId);
			const claims = core.parseClaimList((await runOperator(pi, wc.ledger, claimArgv)).stdout);
			const NO_CLAIM = "(no claim - attach to the task only)";
			const claimOptions = [...claims.map((c) => `${c.id}  [${c.status}]  ${core.truncate(c.text, 90)}`), NO_CLAIM];
			const pickedClaim = await ctx.ui.select(`Attach to which claim on ${wc.taskId}?`, claimOptions);
			if (!pickedClaim) {
				emit(ctx, core.buildDeclinedReport("/op:evidence", "Operator evidence", "No claim selection made.", null));
				return;
			}
			const claimId = pickedClaim === NO_CLAIM ? undefined : pickedClaim.split(/\s+/)[0];

			const type = await ctx.ui.select("Evidence type", [...core.EVIDENCE_TYPES]);
			if (!type) {
				emit(ctx, core.buildDeclinedReport("/op:evidence", "Operator evidence", "No evidence type chosen.", null));
				return;
			}

			const verifyCmdRaw = await ctx.ui.input(
				"Rerunnable verify command for this evidence (required, escape = cancel)",
				"./operator doctor",
			);
			if (verifyCmdRaw === undefined) {
				emit(ctx, core.buildDeclinedReport("/op:evidence", "Operator evidence", "Cancelled at the verify-command prompt.", null));
				return;
			}
			const verifyCmd = verifyCmdRaw.trim();
			if (!verifyCmd) {
				refuse(ctx, "/op:evidence", "Operator evidence", "refusing evidence-attach without a rerunnable --verify-cmd");
				return;
			}
			const notes = await askOptional(ctx, "Notes about this artifact");
			if (notes === null) {
				emit(ctx, core.buildDeclinedReport("/op:evidence", "Operator evidence", "Cancelled at the notes prompt.", null));
				return;
			}
			// Only remote evidence needs an asserted digest: operator fingerprints
			// local bytes itself, and a mismatch there is already fatal.
			let hash: string | undefined;
			if (remote) {
				const answer = await askOptional(ctx, "Expected SHA-256 of the remote artifact");
				if (answer === null) {
					emit(ctx, core.buildDeclinedReport("/op:evidence", "Operator evidence", "Cancelled at the hash prompt.", null));
					return;
				}
				hash = answer || undefined;
			}

			const opts: core.EvidenceAttachOptions = { taskId: wc.taskId, locator, type, by: wc.by, claimId, verifyCmd, notes, hash };
			let argv: string[];
			try {
				argv = core.evidenceAttachArgv(opts);
			} catch (err) {
				refuse(ctx, "/op:evidence", "Operator evidence", err);
				return;
			}

			await confirmAndRun(ctx, wc, {
				command: "/op:evidence",
				title: "Operator evidence",
				noun: "evidence",
				argv,
				plan: core.describeEvidencePlan(opts, remote),
				detail: () =>
					claimId
						? [`${claimId} now has evidence attached. Its verification status is unchanged.`]
						: ["No claim was named, so no claim gained evidence from this attachment."],
			});
		},
	});

	pi.registerCommand("op:handoff", {
		description: "Operator: record a generated closeout handoff for the selected task (/op:handoff; /op:handoff edit for manual draft)",
		handler: async (args, ctx) => {
			const wc = requireWriteContext(ctx, "/op:handoff");
			if (!wc) return;

			let taskShow: core.TaskShowSummary | null = null;
			const show = await runOperator(pi, wc.ledger, core.taskShowArgv(wc.taskId));
			if (show.code === 0) taskShow = core.parseTaskShow(show.stdout);
			const generated = core.buildGeneratedHandoffDraft(wc.taskId, wc.by, taskShow);

			// Default is generated closeout. Earlier dogfood showed that asking the
			// user to type "go" made the literal word look like handoff prose.
			// Manual editing is still available as /op:handoff edit.
			const arg = args.trim().toLowerCase();
			let draft = generated;
			const generatedByDefault = arg === "" || arg === "go" || arg === "auto" || arg === "generated";
			const editMode = arg === "edit" || arg === "draft";
			if (!generatedByDefault && !editMode) {
				refuse(ctx, "/op:handoff", "Operator handoff", new Error("usage: /op:handoff for generated closeout, or /op:handoff edit for manual draft"));
				return;
			}
			if (editMode) {
				const edited = await ctx.ui.editor(`Handoff for ${wc.taskId}`, core.buildHandoffTemplate(wc.taskId, wc.by, generated));
				if (edited === undefined) {
					emit(ctx, core.buildDeclinedReport("/op:handoff", "Operator handoff", "Handoff draft cancelled.", null));
					return;
				}
				draft = edited.trim().toLowerCase() === "go" ? generated : core.parseHandoffDraft(edited);
			}
			let argv: string[];
			try {
				argv = core.handoffAddArgv({ taskId: wc.taskId, by: wc.by, draft });
			} catch (err) {
				refuse(ctx, "/op:handoff", "Operator handoff", err);
				return;
			}

			await confirmAndRun(ctx, wc, {
				command: "/op:handoff",
				title: "Operator handoff",
				noun: "handoff",
				argv,
				plan: core.describeHandoffPlan(wc.taskId, wc.by, draft),
				confirmedByArgument: generatedByDefault,
				detail: () =>
					draft["--next-action"]
						? ["The task's next_action was set from the 'Next action' section."]
						: ["No 'Next action' section, so the task's next_action is unchanged."],
			});
		},
	});

	// --- step 3: supervisor-review ------------------------------------------
	// Claim-scoped wrap of review-delegate. Writes a bundle, never verifies,
	// never attaches evidence, never emits lifecycle flags.

	pi.registerCommand("op:supervisor-review", {
		description: "Operator: request distinct-agent review of one named claim (/op:supervisor-review [claim-id])",
		getArgumentCompletions: (prefix) => {
			const ledger = core.findLedger(process.cwd());
			if (!ledger) return null;
			const ids = core.listClaimIds(ledger).filter((id) => id.startsWith(prefix));
			return ids.length > 0 ? ids.slice(0, 50).map((id) => ({ value: id, label: id })) : null;
		},
		handler: async (args, ctx) => {
			const ledger = requireLedger(ctx);
			if (!ledger) return;
			if (!ctx.hasUI) {
				ctx.ui.notify(
					"/op:supervisor-review is a guided flow and needs a UI. Run ./operator review-delegate directly for a non-interactive write.",
					"error",
				);
				return;
			}
			const { taskId } = resolveActiveTask(ledger);
			if (!taskId) {
				ctx.ui.notify("/op:supervisor-review needs a task. Run /op:tasks then /op:use <task-id>.", "error");
				return;
			}
			if (!core.taskRecordExists(ledger, taskId)) {
				ctx.ui.notify(
					`No task record at ${core.LEDGER_DIR}/tasks/${taskId}.yaml. Refusing to review against it.`,
					"error",
				);
				return;
			}
			const sessionAuthor = core.deriveAuthorLabel(sessionId(ctx));

			const claimArgv = core.claimListArgv(taskId);
			const claims = core.parseClaimList((await runOperator(pi, ledger, claimArgv)).stdout);
			if (claims.length === 0) {
				const message = `/op:supervisor-review needs one named claim on ${taskId}; this task has none.`;
				ctx.ui.notify(message, "error");
				emit(ctx, core.buildDeclinedReport("/op:supervisor-review", "Operator supervisor-review", message, null));
				return;
			}

			let claimId = args.trim();
			if (!claimId) {
				const unverified = claims.filter((c) => c.status.toUpperCase() !== "VERIFIED");
				if (unverified.length === 1) {
					claimId = unverified[0].id;
					ctx.ui.notify(`Defaulting supervisor-review to the only unverified claim on ${taskId}: ${claimId}.`, "info");
				} else if (claims.length === 1) {
					claimId = claims[0].id;
					ctx.ui.notify(`Defaulting supervisor-review to the only claim on ${taskId}: ${claimId}.`, "info");
				} else {
					const labels = claims.map((c) => `${c.id}  [${c.status}]  ${core.truncate(c.text, 90)}`);
					const picked = await ctx.ui.select(`Which claim on ${taskId} should be reviewed?`, labels);
					if (!picked) {
						emit(
							ctx,
							core.buildDeclinedReport(
								"/op:supervisor-review",
								"Operator supervisor-review",
								"No claim selected.",
								null,
							),
						);
						return;
					}
					claimId = picked.split(/\s+/)[0];
				}
			}
			if (!core.isValidClaimId(claimId)) {
				const message = `Refusing claim id '${claimId}': expected claim-NNNN.`;
				ctx.ui.notify(message, "error");
				emit(ctx, core.buildDeclinedReport("/op:supervisor-review", "Operator supervisor-review", message, null));
				return;
			}
			if (!claims.some((c) => c.id === claimId)) {
				const message = `Claim ${claimId} is not on task ${taskId}. Supervisor-review is claim-scoped to the selected task.`;
				ctx.ui.notify(message, "error");
				emit(ctx, core.buildDeclinedReport("/op:supervisor-review", "Operator supervisor-review", message, null));
				return;
			}

			const showArgv = core.claimShowArgv(claimId);
			const shown = core.parseClaimShow((await runOperator(pi, ledger, showArgv)).stdout);
			if (shown.taskId && shown.taskId !== taskId) {
				const message = `Claim ${claimId} belongs to task ${shown.taskId}, not ${taskId}.`;
				ctx.ui.notify(message, "error");
				emit(ctx, core.buildDeclinedReport("/op:supervisor-review", "Operator supervisor-review", message, null));
				return;
			}

			let verifyCmd = shown.verifyCmd ?? "";
			if (!verifyCmd) {
				verifyCmd = "./operator doctor";
				ctx.ui.notify(`Claim ${claimId} has no verify command; defaulting review command to ${verifyCmd}.`, "info");
			}
			if (!verifyCmd) {
				refuse(
					ctx,
					"/op:supervisor-review",
					"Operator supervisor-review",
					"refusing review-delegate without a verification command; provide --verify-cmd (required_gate is an artifact path, not a command)",
				);
				return;
			}

			const harnesses = core.listHarnessIds(ledger);
			if (harnesses.length === 0) {
				const message = "No harness records under .operator/harnesses/; --reviewer cannot be chosen.";
				ctx.ui.notify(message, "error");
				emit(ctx, core.buildDeclinedReport("/op:supervisor-review", "Operator supervisor-review", message, null));
				return;
			}
			const taskShow = core.parseTaskShow((await runOperator(pi, ledger, core.taskShowArgv(taskId))).stdout);
			const assignedHarness = taskShow.fields["Assigned Harness"] || null;
			const reviewHarness = taskShow.fields["Review Harness"] || null;
			let reviewer = "";
			if (reviewHarness && harnesses.includes(reviewHarness) && reviewHarness !== sessionAuthor && reviewHarness !== assignedHarness) {
				reviewer = reviewHarness;
				ctx.ui.notify(`Defaulting supervisor-review target to task review_harness model/persona: ${reviewer}.`, "info");
			} else {
				const reviewerLabels = harnesses.map((id) => {
					const notes: string[] = [];
					if (id === reviewHarness) notes.push("task review_harness model/persona hint");
					if (id === assignedHarness) notes.push("task assigned_harness implementer");
					if (sessionAuthor && id === sessionAuthor) notes.push("this session — not selectable");
					return notes.length > 0 ? `${id}  (${notes.join("; ")})` : id;
				});
				const pickedReviewer = await ctx.ui.select(
					`Review model/persona for ${claimId}${reviewHarness ? ` (task review_harness ${reviewHarness} was not safe to auto-use)` : ""}`,
					reviewerLabels,
				);
				if (!pickedReviewer) {
					emit(
						ctx,
						core.buildDeclinedReport(
							"/op:supervisor-review",
							"Operator supervisor-review",
							"No reviewer selected.",
							null,
						),
					);
					return;
				}
				reviewer = pickedReviewer.split(/\s+/)[0];
			}
			if (!core.harnessRecordExists(ledger, reviewer)) {
				const message = `Refusing reviewer '${reviewer}': no harness record at ${core.LEDGER_DIR}/harnesses/${reviewer}.yaml.`;
				ctx.ui.notify(message, "error");
				emit(ctx, core.buildDeclinedReport("/op:supervisor-review", "Operator supervisor-review", message, null));
				return;
			}
			try {
				core.refuseSelfReview(reviewer, sessionAuthor);
			} catch (err) {
				refuse(ctx, "/op:supervisor-review", "Operator supervisor-review", err);
				return;
			}

			const pickedMode = await ctx.ui.select("Review path", [...core.REVIEW_MODE_OPTIONS]);
			if (!pickedMode) {
				emit(
					ctx,
					core.buildDeclinedReport(
						"/op:supervisor-review",
						"Operator supervisor-review",
						"No review path selected.",
						null,
					),
				);
				return;
			}
			const mode = core.parseReviewModeChoice(pickedMode);
			if (!mode) {
				refuse(ctx, "/op:supervisor-review", "Operator supervisor-review", `unknown review path '${pickedMode}'`);
				return;
			}

			const identity = core.readIdentityPolicy(ledger);
			let reviewUser: string | undefined;
			if (mode === "uid-isolated") {
				const hint = core.describeVerifierAuthPrompt(identity, shown.authorUid).join(" ");
				ctx.ui.notify(hint, "info");
				const verifierUsers = identity
					? core.verifierIdentities(identity).filter((v) => shown.authorUid === null || v.uid !== shown.authorUid)
					: [];
				const preferredVerifier = verifierUsers.find((v) => v.name === "operator-verifier");
				if (preferredVerifier) {
					reviewUser = preferredVerifier.name;
					ctx.ui.notify(`Defaulting trusted verifier Unix user to ${reviewUser} (uid ${preferredVerifier.uid}).`, "info");
				} else if (verifierUsers.length === 1) {
					reviewUser = verifierUsers[0].name;
					ctx.ui.notify(`Defaulting trusted verifier Unix user to ${reviewUser} (uid ${verifierUsers[0].uid}).`, "info");
				} else if (verifierUsers.length > 1) {
					const pickedUser = await ctx.ui.select(
						"Trusted verifier Unix user (authority identity; not the model reviewer)",
						verifierUsers.map((v) => `${v.name}  (uid ${v.uid}; roles ${v.roles.join(",")})`),
					);
					if (!pickedUser) {
						emit(
							ctx,
							core.buildDeclinedReport(
								"/op:supervisor-review",
								"Operator supervisor-review",
								"No verifier Unix user selected.",
								null,
							),
						);
						return;
					}
					reviewUser = pickedUser.split(/\s+/)[0];
				} else {
					const answer = await ctx.ui.input(
						"Unix user for the trusted verifier UID run (no registered verifier default found; escape = cancel)",
						"operator-verifier",
					);
					if (answer === undefined) {
						emit(
							ctx,
							core.buildDeclinedReport(
								"/op:supervisor-review",
								"Operator supervisor-review",
								"Cancelled at the review-user prompt.",
								null,
							),
						);
						return;
					}
					reviewUser = answer.trim();
					if (!reviewUser) {
						refuse(
							ctx,
							"/op:supervisor-review",
							"Operator supervisor-review",
							"refusing uid-isolated review-delegate without --review-user; trusted verification needs a visible human-auth path, not a placeholder",
						);
						return;
					}
				}
			}

			const opts: core.ReviewDelegateOptions = {
				claimId,
				taskId,
				reviewer,
				mode,
				verifyCmd,
				reviewUser,
			};
			let argv: string[];
			try {
				argv = core.reviewDelegateArgv(opts);
			} catch (err) {
				refuse(ctx, "/op:supervisor-review", "Operator supervisor-review", err);
				return;
			}

			const plan = core.describeSupervisorReviewPlan({
				...opts,
				assignedHarness,
				reviewHarness,
				sessionAuthor,
				authorUid: shown.authorUid,
				identity,
			});
			const invocation = core.formatInvocation(argv);
			const ok = await ctx.ui.confirm("Write this review bundle to the ledger?", [...plan, "", invocation].join("\n"));
			if (!ok) {
				emit(
					ctx,
					core.buildDeclinedReport(
						"/op:supervisor-review",
						"Operator supervisor-review",
						"Declined at the confirmation dialog.",
						argv,
					),
				);
				return;
			}
			const result = await runOperator(pi, ledger, argv);
			emit(
				ctx,
				core.buildSupervisorReviewReport({
					taskId,
					opts,
					argv,
					result,
				}),
			);
		},
	});

	// --- step 4: delegate -----------------------------------------------------
	// Chooser-first. Routed implementer: session-start / brief on the parent.
	// Unrouted implementer: confirmed child task with explicit --assign.
	// Dual implementer+reviewer is refused. Adapter invoke is primary;
	// paste/export is a labeled fallback. Parent routing is never mutated.

	pi.registerCommand("op:delegate", {
		description: "Operator: send bounded implementation work to another agent (/op:delegate [task-id] [target-alias])",
		getArgumentCompletions: (prefix) => {
			const ledger = core.findLedger(process.cwd());
			if (!ledger) return null;
			const taskIds = listTaskIds(ledger);
			let aliases: string[] = [];
			try {
				aliases = core.loadDelegateTargets(ledger).map((t) => t.alias);
			} catch {
				aliases = core.DEFAULT_DELEGATE_TARGETS.map((t) => t.alias);
			}
			const values = [...taskIds, ...aliases].filter((id) => id.startsWith(prefix));
			const unique = [...new Set(values)];
			return unique.length > 0 ? unique.slice(0, 50).map((id) => ({ value: id, label: id })) : null;
		},
		handler: async (args, ctx) => {
			const ledger = requireLedger(ctx);
			if (!ledger) return;
			if (!ctx.hasUI) {
				ctx.ui.notify(
					"/op:delegate is a guided flow and needs a UI. Run ./operator task-create / session-start / export-brief directly for a non-interactive write.",
					"error",
				);
				return;
			}

			let targets: core.DelegateTarget[];
			try {
				targets = core.loadDelegateTargets(ledger);
			} catch (err) {
				refuse(ctx, "/op:delegate", "Operator delegate", err);
				return;
			}

			let parsed: core.DelegateArgs;
			try {
				parsed = core.parseDelegateArgs(args);
			} catch (err) {
				refuse(ctx, "/op:delegate", "Operator delegate", err);
				return;
			}

			const active = resolveActiveTask(ledger);
			let parentTaskId = parsed.taskId ?? null;
			let alias = parsed.alias ?? null;
			if (parsed.token) {
				try {
					const resolved = core.resolveDelegateToken(ledger, parsed.token, targets);
					parentTaskId = resolved.taskId ?? parentTaskId;
					alias = resolved.alias ?? alias;
				} catch (err) {
					refuse(ctx, "/op:delegate", "Operator delegate", err);
					return;
				}
			}
			if (!parentTaskId) parentTaskId = active.taskId;
			if (!parentTaskId) {
				ctx.ui.notify("/op:delegate needs a task. Run /op:tasks then /op:use <task-id>.", "error");
				return;
			}
			if (!core.isValidTaskId(parentTaskId) || !core.taskRecordExists(ledger, parentTaskId)) {
				const message = `No task record at ${core.LEDGER_DIR}/tasks/${parentTaskId}.yaml. Refusing to delegate against it.`;
				ctx.ui.notify(message, "error");
				emit(ctx, core.buildDeclinedReport("/op:delegate", "Operator delegate", message, null));
				return;
			}

			const sessionAuthor = core.deriveAuthorLabel(sessionId(ctx));
			const taskShow = core.parseTaskShow((await runOperator(pi, ledger, core.taskShowArgv(parentTaskId))).stdout);
			const assignedHarness = core.normalizeHarnessField(taskShow.fields["Assigned Harness"]);
			const reviewHarness = core.normalizeHarnessField(taskShow.fields["Review Harness"]);

			const resolvedTargets: core.ResolvedDelegateTarget[] = [];
			const skipped: string[] = [];
			for (const target of targets) {
				try {
					resolvedTargets.push(core.resolveDelegateTarget(ledger, target));
				} catch (err) {
					skipped.push(err instanceof Error ? err.message : String(err));
				}
			}
			if (resolvedTargets.length === 0) {
				const message =
					"/op:delegate has no usable targets: every configured alias failed to resolve to a harness record plus an adapter carrier.";
				ctx.ui.notify(message, "error");
				emit(
					ctx,
					core.buildDeclinedReport(
						"/op:delegate",
						"Operator delegate",
						[message, ...skipped].join("\n"),
						null,
					),
				);
				return;
			}

			if (!alias) {
				const labels = resolvedTargets.map((t) => {
					const route = core.classifyDelegateTarget({
						target: t,
						assignedHarness,
						reviewHarness,
						sessionAuthor,
					});
					return core.chooserLabelForTarget(t, route, assignedHarness, reviewHarness);
				});
				const picked = await ctx.ui.select(
					`Delegate implementer for ${parentTaskId} (ledger harness ≠ carrier ≠ model ≠ isolation ≠ brief format)`,
					labels,
				);
				if (!picked) {
					emit(ctx, core.buildDeclinedReport("/op:delegate", "Operator delegate", "No target selected.", null));
					return;
				}
				alias = picked.split(/\s+/)[0];
			}

			const target = resolvedTargets.find((t) => t.alias === alias);
			if (!target) {
				const message = `Refusing target alias '${alias}': not in the resolved chooser set.`;
				ctx.ui.notify(message, "error");
				emit(ctx, core.buildDeclinedReport("/op:delegate", "Operator delegate", message, null));
				return;
			}

			const route = core.classifyDelegateTarget({
				target,
				assignedHarness,
				reviewHarness,
				sessionAuthor,
			});
			if (route.action === "refuse") {
				ctx.ui.notify(route.reason, "error");
				emit(ctx, core.buildDeclinedReport("/op:delegate", "Operator delegate", route.reason, null));
				return;
			}

			let workTaskId = parentTaskId;
			let childObjective = "";
			if (route.action === "child-task") {
				const suggested = core.defaultChildTaskId(parentTaskId, target.alias);
				const idAnswer = await ctx.ui.input(
					`Child task id for --assign ${target.harnessId} (parent ${parentTaskId} routing will not change)`,
					suggested,
				);
				if (idAnswer === undefined) {
					emit(
						ctx,
						core.buildDeclinedReport("/op:delegate", "Operator delegate", "Cancelled at the child task id prompt.", null),
					);
					return;
				}
				workTaskId = idAnswer.trim() || suggested;
				if (!core.isValidTaskId(workTaskId)) {
					refuse(
						ctx,
						"/op:delegate",
						"Operator delegate",
						`refusing child task id '${workTaskId}': expected [A-Za-z0-9][A-Za-z0-9._-]*`,
					);
					return;
				}
				if (core.taskRecordExists(ledger, workTaskId)) {
					refuse(
						ctx,
						"/op:delegate",
						"Operator delegate",
						`refusing child task id '${workTaskId}': a task record already exists`,
					);
					return;
				}
				const parentObjective = taskShow.fields.Objective ?? parentTaskId;
				const objAnswer = await ctx.ui.editor(
					`Child task objective (scoped from ${parentTaskId}; --assign ${target.harnessId})`,
					`Bounded implementation delegated from ${parentTaskId} to ${target.harnessId} while the current Pi agent remains in the loop. Parent objective: ${parentObjective}`,
				);
				if (objAnswer === undefined || !objAnswer.trim()) {
					emit(
						ctx,
						core.buildDeclinedReport("/op:delegate", "Operator delegate", "Cancelled at the child objective prompt.", null),
					);
					return;
				}
				childObjective = objAnswer.trim();
			}

			const pickedDispatch = await ctx.ui.select("Dispatch path", [...core.DELEGATE_DISPATCH_OPTIONS]);
			if (!pickedDispatch) {
				emit(ctx, core.buildDeclinedReport("/op:delegate", "Operator delegate", "No dispatch path selected.", null));
				return;
			}
			const requestedDispatch = core.parseDispatchChoice(pickedDispatch);
			if (!requestedDispatch) {
				refuse(ctx, "/op:delegate", "Operator delegate", `unknown dispatch path '${pickedDispatch}'`);
				return;
			}

			const plan = core.describeDelegatePlan({
				parentTaskId,
				workTaskId,
				target,
				route,
				childObjective,
				sessionAuthor,
				assignedHarness,
				reviewHarness,
				dispatch: requestedDispatch,
				dispatchReason:
					requestedDispatch === "adapter"
						? "primary path if a brief is written and isolation is in-repo"
						: "user chose the labeled paste/export fallback",
			});
			const planned: string[] = [];
			let createArgv: string[] | null = null;
			if (route.action === "child-task") {
				try {
					createArgv = core.taskCreateArgv({
						taskId: workTaskId,
						objective: childObjective,
						assign: target.harnessId,
					});
				} catch (err) {
					refuse(ctx, "/op:delegate", "Operator delegate", err);
					return;
				}
				planned.push(core.formatInvocation(createArgv));
			}
			const startArgv = core.sessionStartArgv(workTaskId, target.harnessId);
			planned.push(core.formatInvocation(startArgv));
			if (target.briefFormat === "brief") {
				planned.push(core.formatInvocation(core.briefArgv(workTaskId, target.harnessId)));
			}
			const ok = await ctx.ui.confirm("Write these Operator records for the delegate?", [...plan, "", ...planned].join("\n"));
			if (!ok) {
				emit(
					ctx,
					core.buildDeclinedReport(
						"/op:delegate",
						"Operator delegate",
						"Declined at the confirmation dialog.",
						createArgv ?? startArgv,
					),
				);
				return;
			}

			const results: core.CommandResult[] = [];
			const invocations: string[] = [];
			let childCreated = false;
			if (createArgv) {
				invocations.push(core.formatInvocation(createArgv));
				const created = await runOperator(pi, ledger, createArgv);
				results.push(created);
				if (created.code !== 0 || !core.parseTaskCreate(created.stdout)) {
					emit(
						ctx,
						core.buildDelegateReport({
							parentTaskId,
							workTaskId,
							target,
							route,
							dispatch: "paste-fallback",
							dispatchReason: "task-create failed; parent routing was not changed",
							childCreated: false,
							parentAssignedHarness: assignedHarness,
							parentReviewHarness: reviewHarness,
							briefFile: null,
							usageId: null,
							adapterState: null,
							invocations,
							results,
						}),
					);
					return;
				}
				childCreated = true;
			}

			invocations.push(core.formatInvocation(startArgv));
			const started = await runOperator(pi, ledger, startArgv);
			results.push(started);
			let briefFile: string | null = null;
			let usageId: string | null = null;
			if (started.code === 0) {
				const parsedStart = core.parseSessionStart(started.stdout);
				briefFile = parsedStart.briefPath;
				usageId = parsedStart.usageId;
			} else if (core.classifySessionStartError(started.stderr, started.stdout) === "already_running") {
				const exportArgv = core.exportBriefArgv(workTaskId, target.harnessId);
				invocations.push(core.formatInvocation(exportArgv));
				const exported = await runOperator(pi, ledger, exportArgv);
				results.push(exported);
				if (exported.code === 0) briefFile = core.exportBriefPath(ledger, workTaskId, target.harnessId);
			} else if (core.classifySessionStartError(started.stderr, started.stdout) === "unrouted") {
				emit(
					ctx,
					core.buildDelegateReport({
						parentTaskId,
						workTaskId,
						target,
						route,
						dispatch: "paste-fallback",
						dispatchReason: "session-start failed because the harness is not implementer-routed; parent routing was not mutated",
						childCreated,
						parentAssignedHarness: assignedHarness,
						parentReviewHarness: reviewHarness,
						briefFile: null,
						usageId: null,
						adapterState: null,
						invocations,
						results,
					}),
				);
				return;
			}

			if (target.briefFormat === "brief") {
				const bArgv = core.briefArgv(workTaskId, target.harnessId);
				invocations.push(core.formatInvocation(bArgv));
				const briefed = await runOperator(pi, ledger, bArgv);
				results.push(briefed);
				if (briefed.code === 0) briefFile = core.briefPath(ledger, workTaskId, target.harnessId);
			} else if (!briefFile) {
				const expected = core.exportBriefPath(ledger, workTaskId, target.harnessId);
				if (existsSync(expected)) briefFile = expected;
			}

			let dispatch = core.decideDispatchPath({
				requested: requestedDispatch,
				isolation: target.isolation,
				briefExists: Boolean(briefFile),
			});
			let adapterState: string | null = null;
			let adapterArgv: string[] | null = null;
			if (dispatch.path === "adapter" && briefFile) {
				try {
					adapterArgv = core.adapterInvokeArgv({
						moduleRoot: core.adapterModuleRoot(ledger),
						carrierId: target.carrierId,
						model: target.model,
						briefPath: briefFile,
						workspace: ledger.root,
					});
					core.assertSafeAdapterArgv(adapterArgv);
					const adapterResult = await pi.exec(adapterArgv[0], adapterArgv.slice(1), {
						cwd: ledger.root,
						timeout: 1_800_000,
					});
					results.push(adapterResult);
					invocations.push(core.formatAdapterInvocation(adapterArgv));
					const parsedAdapter = core.parseAdapterInvoke(adapterResult);
					adapterState = parsedAdapter.exitState;
					if (adapterState !== "success") {
						dispatch = {
							path: "paste-fallback",
							reason: `adapter reported ${adapterState ?? `exit ${adapterResult.code}`}; falling back to labeled paste/export`,
						};
					}
				} catch (err) {
					dispatch = {
						path: "paste-fallback",
						reason: `adapter invoke could not start (${err instanceof Error ? err.message : String(err)}); labeled paste/export fallback`,
					};
				}
			}

			emit(
				ctx,
				core.buildDelegateReport({
					parentTaskId,
					workTaskId,
					target,
					route,
					dispatch: dispatch.path,
					dispatchReason: dispatch.reason,
					childCreated,
					parentAssignedHarness: assignedHarness,
					parentReviewHarness: reviewHarness,
					briefFile,
					usageId,
					adapterState,
					invocations,
					results,
				}),
			);
		},
	});
}

/** Task ids straight off disk, for autocomplete. Cheap and never executes anything. */
function listTaskIds(ledger: core.Ledger): string[] {
	try {
		return readdirSync(ledger.tasksDir)
			.filter((name) => name.endsWith(".yaml"))
			.map((name) => name.slice(0, -".yaml".length))
			.filter((id) => core.isValidTaskId(id))
			.sort();
	} catch {
		return [];
	}
}
