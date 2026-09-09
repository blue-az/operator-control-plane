/**
 * Carrier-neutral Operator client.
 *
 * This module deliberately imports no Pi UI/runtime APIs. A carrier supplies
 * only an argv runner; Operator remains the authority and all argv is built by
 * the fixed builders in core.ts.
 */
import * as core from "./core.ts";

export interface ClientRunner {
	exec(command: string, args: string[], options?: { cwd?: string; timeout?: number }): Promise<core.CommandResult>;
}

export interface IdempotentResult extends core.CommandResult {
	/** True when the requested lifecycle state already existed. */
	idempotent: boolean;
}

export class OperatorClient {
	readonly ledger: core.Ledger;
	private readonly runner: ClientRunner;
	constructor(ledger: core.Ledger, runner: ClientRunner) {
		this.ledger = ledger;
		this.runner = runner;
	}

	private async invoke(argv: string[]): Promise<core.CommandResult> {
		core.assertSafeArgv(argv);
		return this.runner.exec(this.ledger.operatorBin, argv, { cwd: this.ledger.root, timeout: 120_000 });
	}

	private requireTask(taskId: string): void {
		if (!core.taskRecordExists(this.ledger, taskId)) {
			throw new Error(`refusing operation: no task record at ${core.LEDGER_DIR}/tasks/${taskId}.yaml`);
		}
	}

	async doctor(): Promise<core.CommandResult> { return this.invoke(core.doctorArgv()); }
	async tasks(opts: { all?: boolean; filter?: string } = {}): Promise<core.CommandResult> {
		return this.invoke(core.taskListArgv(opts));
	}
	async taskShow(taskId: string): Promise<core.CommandResult> {
		this.requireTask(taskId); return this.invoke(core.taskShowArgv(taskId));
	}
	async claims(taskId: string): Promise<core.CommandResult> {
		this.requireTask(taskId); return this.invoke(core.claimListArgv(taskId));
	}
	async sessions(taskId: string): Promise<core.CommandResult> {
		this.requireTask(taskId); return this.invoke(core.sessionListArgv(taskId));
	}
	async useTask(taskId: string): Promise<core.CommandResult> {
		this.requireTask(taskId); return this.invoke(core.taskUseArgv(taskId));
	}
	async startSession(taskId: string, harnessId: string): Promise<IdempotentResult> {
		this.requireTask(taskId);
		const result = await this.invoke(core.sessionStartArgv(taskId, harnessId));
		if (result.code !== 0 && core.classifySessionStartError(result.stderr, result.stdout) === "already_running") {
			return { ...result, code: 0, idempotent: true };
		}
		return { ...result, idempotent: false };
	}
	async endSession(usageId: string, outcome: string, cost: number): Promise<IdempotentResult> {
		const result = await this.invoke(core.sessionEndArgv(usageId, outcome, cost));
		if (result.code !== 0 && /already closed/i.test(`${result.stderr}\n${result.stdout}`)) {
			return { ...result, code: 0, idempotent: true };
		}
		return { ...result, idempotent: false };
	}
	async brief(taskId: string, harnessId: string): Promise<core.CommandResult> {
		this.requireTask(taskId); return this.invoke(core.briefArgv(taskId, harnessId));
	}
	async exportBrief(taskId: string, harnessId: string): Promise<core.CommandResult> {
		this.requireTask(taskId); return this.invoke(core.exportBriefArgv(taskId, harnessId));
	}
}

/** Stable name for carriers that do not need to know the Pi implementation. */
export { OperatorClient as CarrierNeutralOperatorClient };
