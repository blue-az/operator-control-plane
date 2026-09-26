/** Human-operated OpenCode core workflows. No model tools or provider calls. */
import * as core from "../../.pi/extensions/operator/core.ts";
import { OperatorClient, type ClientRunner } from "../../.pi/extensions/operator/client.ts";

export interface Dialogs {
	input(title: string, value?: string): Promise<string | undefined>;
	select(title: string, values: readonly string[]): Promise<string | undefined>;
	confirm(title: string, message: string): Promise<boolean>;
	show(title: string, message: string): Promise<void>;
}
export interface Context { directory: string; sessionID?: string }
export const COMMANDS = [
	["op", "Operator status / doctor"],
	["op:tasks", "List all tasks"],
	["op:task", "Inspect a task"],
	["op:claims", "Inspect task claims"],
	["op:sessions", "Inspect task sessions"],
	["op:use", "Set current ledger task (confirmed write)"],
	["op:brief", "Generate brief (confirmed write)"],
	["op:export-brief", "Generate export brief (confirmed write)"],
	["op:session-start", "Start ledger session (confirmed write)"],
	["op:session-end", "Close usage record (confirmed write)"],
	["op:claim", "Record unverified claim"],
	["op:evidence", "Attach draft evidence"],
	["op:handoff", "Record structured handoff"],
] as const;
export type Command = typeof COMMANDS[number][0];
const WRITES = new Set(["task-use", "brief", "export-brief", "session-start", "session-end", "claim-add", "evidence-attach", "handoff-add"]);
class Cancelled extends Error {}

/** Keep the entire OpenCode ID: its shared ses_ prefix is not a unique short ID. */
export function authorLabel(sessionID?: string): string {
	if (!sessionID || !/^[A-Za-z0-9][A-Za-z0-9_-]+$/.test(sessionID)) {
		throw new Error("Open an OpenCode session before recording authoring writes.");
	}
	return `opencode-${sessionID}`;
}

/** JSON strings preserve exact argv, including newlines/control characters, without terminal escapes. */
export function invocation(ledger: core.Ledger, argv: string[]): string {
	return `cwd: ${JSON.stringify(ledger.root)}\nexecutable: ${JSON.stringify(ledger.operatorBin)}\nargv: ${JSON.stringify(argv)}`;
}

export class OperatorController {
	private busy = false;
	private readonly selected = new Map<string, string>();
	private readonly context: () => Context;
	private readonly ui: Dialogs;
	private readonly runner: ClientRunner;
	private readonly signal?: AbortSignal;
	constructor(context: () => Context, ui: Dialogs, runner: ClientRunner, signal?: AbortSignal) {
		this.context = context;
		this.ui = ui;
		this.runner = runner;
		this.signal = signal;
	}

	async run(command: Command): Promise<void> {
		// Never interleave prompts from two commands or enqueue a stale write.
		if (this.busy || this.signal?.aborted) return;
		this.busy = true;
		try {
			if (!COMMANDS.some(([name]) => name === command)) throw new Error("Unknown Operator command");
			await this.dispatch(command);
		} catch (err) {
			if (!(err instanceof Cancelled) && !this.signal?.aborted) {
				await this.ui.show("Operator error", err instanceof Error ? err.message : String(err));
			}
		} finally { this.busy = false; }
	}

	private async input(title: string, value = ""): Promise<string> {
		const answer = await this.ui.input(title, value);
		if (answer === undefined || this.signal?.aborted) throw new Cancelled();
		return answer.trim();
	}
	private async select(title: string, values: readonly string[]): Promise<string> {
		if (!values.length) throw new Error(`${title}: no choices available. Configure the Operator registry first.`);
		const answer = await this.ui.select(title, values);
		if (answer === undefined || this.signal?.aborted) throw new Cancelled();
		if (!values.includes(answer)) throw new Error("Invalid selection");
		return answer;
	}
	private checkTask(ledger: core.Ledger, task: string): void {
		if (!core.isValidTaskId(task) || !core.taskRecordExists(ledger, task)) {
			throw new Error(`No valid task record for ${JSON.stringify(task)}`);
		}
	}
	private async result(ledger: core.Ledger, argv: string[], result: core.CommandResult): Promise<void> {
		await this.ui.show(`Operator: ${argv[0]} (exit ${result.code})`, [
			invocation(ledger, argv), result.stdout, result.stderr,
			result.code === 0 ? "CLI output is not independent verification." : "Command failed. Inspect the ledger: partial writes may have occurred; do not assume rollback.",
		].filter(Boolean).join("\n\n"));
	}

	private async dispatch(command: Command): Promise<void> {
		const context = { ...this.context() };
		if (!context.directory) throw new Error("OpenCode paths are not ready; try again.");
		const ledger = core.findLedger(context.directory);
		if (!ledger) throw new Error("No Operator ledger found. See adapters/opencode/README.md for the cross-project ledger contract.");
		const client = new OperatorClient(ledger, this.runner);
		const key = JSON.stringify([ledger.root, context.sessionID ?? null]);
		const fresh = () => {
			const now = this.context();
			if (this.signal?.aborted || now.sessionID !== context.sessionID || now.directory !== context.directory || core.findLedger(now.directory)?.root !== ledger.root) {
				throw new Error("OpenCode session, workspace, or ledger changed. Run the command again.");
			}
		};
		const write = async (argv: string[], note: string, check = () => {}) => {
			core.assertSafeArgv(argv);
			if (!WRITES.has(argv[0])) throw new Error("Not a core authoring command");
			fresh(); check();
			if (!await this.ui.confirm("Confirm Operator write", `${note}\n\n${invocation(ledger, argv)}\n\nRun this exact command? No verification status is set by this adapter.`)) throw new Cancelled();
			fresh(); check();
			const result = await this.runner.exec(ledger.operatorBin, argv, { cwd: ledger.root, timeout: 120_000 });
			await this.result(ledger, argv, result);
			return result;
		};
		if (command === "op") {
			await this.result(ledger, core.doctorArgv(), await client.doctor()); return;
		}
		if (command === "op:tasks") {
			await this.result(ledger, core.taskListArgv({ all: true }), await client.tasks({ all: true })); return;
		}
		if (command === "op:session-end") {
			// Explicit usage ID, not guessed from a global task or the latest session.
			const usage = await this.input("Usage ID to close (inspect /op:sessions first)");
			const outcome = await this.select("Session outcome (not verification)", core.SESSION_OUTCOMES);
			const cost = await this.input("Cost estimate in USD (required; 0 is allowed)");
			if (!cost) throw new Error("A cost estimate is required");
			await write(core.sessionEndArgv(usage, outcome, Number(cost)), "Closes the named usage record only; does not complete or verify its task. Confirm you chose the intended usage ID."); return;
		}
		const task = await this.input("Task ID", this.selected.get(key) ?? core.readLedgerCurrentTask(ledger) ?? "");
		this.checkTask(ledger, task);
		const checkTask = () => this.checkTask(ledger, task);
		if (command === "op:task") { await this.result(ledger, core.taskShowArgv(task), await client.taskShow(task)); return; }
		if (command === "op:claims") { await this.result(ledger, core.claimListArgv(task), await client.claims(task)); return; }
		if (command === "op:sessions") { await this.result(ledger, core.sessionListArgv(task), await client.sessions(task)); return; }
		if (command === "op:use") {
			const result = await write(core.taskUseArgv(task), "Updates the ledger's shared current-task pointer. Other sessions may see this change.", checkTask);
			if (result.code === 0) this.selected.set(key, task);
			return;
		}
		if (command === "op:brief" || command === "op:export-brief" || command === "op:session-start") {
			const harness = await this.select("Registered harness (routing identity, not verifier authority)", core.listHarnessIds(ledger));
			const argv = command === "op:brief" ? core.briefArgv(task, harness) : command === "op:export-brief" ? core.exportBriefArgv(task, harness) : core.sessionStartArgv(task, harness);
			await write(argv, command === "op:session-start"
				? "Starts ledger usage, writes an export brief, and marks the task running. If unassigned, Operator assigns this harness. Does not launch an agent. Use a registered session-derived harness ID."
				: "Writes a brief file and records its issuance. It is not a read-only preview or a model call.", () => {
				checkTask();
				if (!core.harnessRecordExists(ledger, harness)) throw new Error("Selected harness no longer exists");
			}); return;
		}
		const by = authorLabel(context.sessionID);
		if (command === "op:claim") {
			const type = await this.select("Claim type", core.CLAIM_TYPES);
			const text = await this.input("Claim text (unverified)");
			const gate = await this.input("Required gate (optional)");
			const verifyCmd = await this.input("Re-runnable verification command (optional; stored, not executed)");
			const layer = type === "supervision_credit" ? await this.select("Supervision layer", core.SUPERVISION_LAYERS) : undefined;
			await write(core.claimAddArgv({ taskId: task, type, text, gate, verifyCmd, layer, by }), `Records an unverified claim. Author: ${by}.`, checkTask); return;
		}
		if (command === "op:evidence") {
			const raw = await this.input("Evidence path (relative to ledger root) or HTTPS URL");
			const { locator, remote } = core.resolveEvidenceLocator(ledger, raw);
			const type = await this.select("Evidence type", core.EVIDENCE_TYPES);
			const claimId = await this.input("Claim ID (optional; empty means task-level evidence)");
			if (claimId) {
				const argv = core.claimShowArgv(claimId);
				const result = await this.runner.exec(ledger.operatorBin, argv, { cwd: ledger.root, timeout: 120_000 });
				if (result.code !== 0 || core.parseClaimShow(result.stdout).taskId !== task) throw new Error("Claim does not belong to the selected task");
			}
			const verifyCmd = await this.input("Re-runnable verification command (required; stored, not executed)");
			const notes = await this.input("Evidence notes (optional)");
			await write(core.evidenceAttachArgv({ taskId: task, locator, type, claimId: claimId || undefined, verifyCmd, notes, by }),
				`Attaches draft evidence; never verifies. Author: ${by}.${remote ? " Remote evidence is not locally snapshotted; doctor may report it uncheckable." : ""}`, () => {
					checkTask(); core.resolveEvidenceLocator(ledger, locator);
				}); return;
		}
		if (command === "op:handoff") {
			const draft: core.HandoffDraft = {};
			for (const section of core.HANDOFF_SECTIONS) draft[section.flag] = await this.input(`${section.heading} (optional)`);
			await write(core.handoffAddArgv({ taskId: task, by, draft }), `Records continuity prose, not verification. A next action updates the task's next_action. Author: ${by}.`, checkTask);
		}
	}
}
