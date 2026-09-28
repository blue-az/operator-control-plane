/**
 * /op:life-boat — minimal slice of owners-manual/pbc/appendix-op-life-boat.pbc.md.
 *
 * Implemented: human launch (LB-RUL-001), enforced edit freeze (LB-RUL-002),
 * agent-drafted attempt log (LB-RUL-003) reviewed in the editor before anything is
 * written (LB-RUL-004), saved as a crystal with git HEAD and diff stat and offered for
 * attachment, never committing source (LB-RUL-005), direction handed back with the
 * do-not-retry list (LB-RUL-008), and a second-launch warning (LB-RUL-010).
 *
 * Not implemented: launching the fresh supervisor (LB-RUL-006/007). The operator starts
 * it by hand from the saved crystal, pending the supervisor-role decision.
 */
import { realpathSync } from "node:fs";
import { join } from "node:path";
import type { ExtensionAPI, ExtensionCommandContext } from "@earendil-works/pi-coding-agent";
import { captureArgs, capturePackage, refuseSymlink, type WorkflowHooks } from "./commands.ts";

export const LIFEBOAT_ENTRY_TYPE = "operator-life-boat";

/** Tools the agent keeps while frozen. Anything else, including bash and unknown tools, is blocked. */
export const READ_ONLY_TOOLS: ReadonlySet<string> = new Set(["read", "grep", "find", "ls"]);

export const ATTEMPT_LOG_REQUEST = `The operator suspects a doom loop and has opened a life-boat. Editing is frozen: stop changing files.

Write an attempt log covering every distinct attempt in this session, oldest first. Group variations of the same idea under one attempt and list the variations. Use exactly this shape:

### Attempt 1: <short name>
- Tried: <what you did>
- Changed: <files or settings touched>
- Result: <what happened, with the actual error or output>
- Abandoned because: <why>

After the attempts, add:

### Current hypothesis
<what you now believe the problem is>

### Untested
<ideas you have not tried yet>

Do not soften failures or describe an attempt as closer to working than it was. The operator will review and correct this log before it is saved.`;

export interface LifeboatState {
	open: boolean;
	taskId: string | null;
	/** Launches per task in this session, for LB-RUL-010. */
	launches: Record<string, number>;
}

export function initialState(): LifeboatState {
	return { open: false, taskId: null, launches: {} };
}

/** Latest persisted state on the branch; entries are display-only and never reach the model. */
export function restoreState(entries: readonly { type: string; customType?: string; data?: unknown }[]): LifeboatState {
	let state = initialState();
	for (const entry of entries) {
		if (entry.type === "custom" && entry.customType === LIFEBOAT_ENTRY_TYPE && entry.data) {
			const data = entry.data as Partial<LifeboatState>;
			state = { open: data.open === true, taskId: data.taskId ?? null, launches: { ...(data.launches ?? {}) } };
		}
	}
	return state;
}

export function freezeDecision(state: LifeboatState, toolName: string): { block: true; reason: string } | undefined {
	if (!state.open || READ_ONLY_TOOLS.has(toolName)) return undefined;
	return {
		block: true,
		reason: `Life-boat open: ${toolName} is frozen until the operator closes it. Reply with text only.`,
	};
}

type BranchEntry = { type: string; message?: { role?: string; content?: unknown } };

/** Text of the newest assistant message, skipping thinking and tool parts. */
export function lastAssistantText(branch: readonly BranchEntry[]): string | null {
	for (let i = branch.length - 1; i >= 0; i--) {
		const message = branch[i].type === "message" ? branch[i].message : undefined;
		if (message?.role !== "assistant") continue;
		const content = message.content;
		const text = typeof content === "string"
			? content
			: Array.isArray(content)
				? content.filter((part) => part?.type === "text").map((part) => String(part.text ?? "")).join("\n")
				: "";
		if (text.trim()) return text.trim();
	}
	return null;
}

export function countAttempts(log: string): number {
	return (log.match(/^###\s+Attempt\b/gim) ?? []).length;
}

export function crystalBody(log: string, head: string, diffStat: string): string {
	return [
		"# Life-boat attempt log",
		"",
		"Reviewed by the operator before capture. Narration is not verification.",
		"",
		`Git HEAD: ${head}`,
		"",
		"Working tree diff stat (uncommitted source was not committed, stashed or reverted):",
		"```",
		diffStat || "(clean)",
		"```",
		"",
		"## Rejected Attempts",
		"",
		log.trim(),
		"",
	].join("\n");
}

export function directionMessage(direction: string): string {
	return [
		"The life-boat is closed and editing is unfrozen. Direction from review:",
		"",
		direction.trim(),
		"",
		"Before proposing anything the do-not-retry list names, say which entry it matches and what is different this time. Proposing a rejected attempt again without citing it is the loop resuming.",
	].join("\n");
}

export interface LifeboatHooks extends WorkflowHooks {
	/** The existing /op:crystal-attach flow; it confirms before writing. */
	attach(args: string, ctx: ExtensionCommandContext): Promise<void>;
}

export function registerLifeboat(pi: ExtensionAPI, hooks: LifeboatHooks) {
	let state = initialState();
	const persist = () => pi.appendEntry(LIFEBOAT_ENTRY_TYPE, state);
	const report = (ctx: ExtensionCommandContext, headline: string, lines: string[] = [], invocations: string[] = [], error = false) =>
		hooks.emit(ctx, { command: "/op:life-boat", title: "op:life-boat", headline, lines, invocations, level: error ? "error" : "info" });
	const invocation = (cmd: string, args: string[]) => [cmd, ...args].map((s) => JSON.stringify(s)).join(" ");

	pi.on("session_start", async (_event, ctx) => {
		state = restoreState(ctx.sessionManager.getEntries());
	});
	pi.on("tool_call", async (event) => freezeDecision(state, event.toolName));

	const git = async (ctx: ExtensionCommandContext, args: string[]) => {
		const result = await pi.exec("git", args, { cwd: ctx.cwd, timeout: 30_000 });
		return result.code === 0 ? result.stdout.trim() : `(unavailable: ${result.stderr.trim() || `git exit ${result.code}`})`;
	};

	/** Review, capture and offer to attach. The freeze stays on either way. */
	const save = async (ctx: ExtensionCommandContext, wc: { taskId: string }) => {
		const draft = lastAssistantText(ctx.sessionManager.getBranch());
		if (!draft) {
			report(ctx, "no attempt log yet; still frozen", ["Wait for the agent's reply, then run /op:life-boat save."]);
			return;
		}
		const log = await ctx.ui.editor("Life-boat attempt log — correct it, add missing attempts (saved as a crystal)", draft);
		if (log === undefined || !log.trim()) {
			report(ctx, "log not saved; still frozen", ["Run /op:life-boat save to try again, or /op:life-boat cancel."]);
			return;
		}
		const attempts = countAttempts(log);
		const bin = capturePackage(ctx.cwd);
		const body = crystalBody(log, await git(ctx, ["rev-parse", "HEAD"]), await git(ctx, ["diff", "--stat", "HEAD"]));
		const argv = captureArgs(bin, realpathSync(ctx.cwd), ctx.sessionManager.getSessionId(), wc.taskId, body, ctx.model);
		const warning = attempts < 2 ? `\nWARNING: ${attempts} attempt(s) found. This may not be a loop.\n` : "";
		if (!await ctx.ui.confirm("Save life-boat crystal?", `${warning}Writes only a local crystal; no source commit, stash or revert.\n\n${invocation(process.execPath, argv)}`)) {
			report(ctx, "declined; nothing saved, still frozen", ["Run /op:life-boat save to try again, or /op:life-boat cancel."]);
			return;
		}
		for (const path of [join(ctx.cwd, ".agent-crystals"), join(ctx.cwd, ".agent-crystals", "sessions")]) refuseSymlink(path);
		const result = await pi.exec(process.execPath, argv, { cwd: ctx.cwd, timeout: 120_000 });
		if (result.code !== 0) {
			report(ctx, "crystal capture failed; still frozen", [result.stdout, result.stderr], [invocation(process.execPath, argv)], true);
			return;
		}
		let path: string | null = null;
		try { path = String(JSON.parse(result.stdout).path ?? "") || null; } catch { /* reported below */ }
		report(ctx, "attempt log saved; still frozen", [
			path ? `Crystal: ${path}` : result.stdout,
			"Next: start a fresh supervisor (new session, never this one) with that crystal, the task and the repo.",
			"Ask it for a diagnosis, one next attempt, and a do-not-retry list. Its answer is direction, not evidence.",
			"Then run /op:life-boat close and paste the direction.",
		], [invocation(process.execPath, argv)]);
		if (path) await hooks.attach(path, ctx);
		else report(ctx, "could not read the crystal path; attach it with /op:crystal-attach", [], [], true);
	};

	const launch = async (ctx: ExtensionCommandContext) => {
		const wc = hooks.writeContext(ctx, "/op:life-boat"); if (!wc) return;
		if (state.open) {
			report(ctx, "already open", ["/op:life-boat save | close | cancel"], [], true);
			return;
		}
		const prior = state.launches[wc.taskId] ?? 0;
		const escalation = prior > 0
			? `\nThis task already had ${prior} life-boat(s) this session. Repeated life-boats are themselves a loop: compare the earlier crystal and direction before sending another supervisor.\n`
			: "";
		if (!await ctx.ui.confirm("Open a life-boat?", `Task: ${wc.taskId}\n${escalation}\nFreezes every tool except ${[...READ_ONLY_TOOLS].join(", ")} until you close or cancel.\nAsks the agent for an attempt log, which you review before it is saved.`)) {
			report(ctx, "declined; nothing changed");
			return;
		}
		state = { open: true, taskId: wc.taskId, launches: { ...state.launches, [wc.taskId]: prior + 1 } };
		persist();
		if (ctx.isIdle()) pi.sendUserMessage(ATTEMPT_LOG_REQUEST);
		else pi.sendUserMessage(ATTEMPT_LOG_REQUEST, { deliverAs: "steer" });
		await ctx.waitForIdle();
		await save(ctx, wc);
	};

	const close = async (ctx: ExtensionCommandContext, cancel: boolean) => {
		if (!state.open) { report(ctx, "no life-boat is open"); return; }
		const direction = cancel ? "" : await ctx.ui.editor("Supervisor direction and do-not-retry list (empty = unfreeze without direction)", "") ?? null;
		if (direction === null) { report(ctx, "close cancelled; still frozen"); return; }
		state = { ...state, open: false };
		persist();
		if (direction.trim()) pi.sendUserMessage(directionMessage(direction));
		report(ctx, cancel ? "cancelled; editing unfrozen" : "closed; editing unfrozen", cancel ? [] : ["Record the closeout with /op:handoff: crystal, direction taken, who implements next."]);
	};

	pi.registerCommand("op:life-boat", {
		description: "[experimental] Operator: doom-loop escape; freeze edits, review an attempt log, save it as a crystal (/op:life-boat [save|close|cancel])",
		handler: async (args, ctx) => {
			try {
				const verb = args.trim();
				if (verb === "") await launch(ctx);
				else if (verb === "save") {
					if (!state.open) { report(ctx, "no life-boat is open"); return; }
					const wc = hooks.writeContext(ctx, "/op:life-boat save"); if (!wc) return;
					await save(ctx, wc);
				} else if (verb === "close") await close(ctx, false);
				else if (verb === "cancel") await close(ctx, true);
				else report(ctx, "unknown argument", ["usage: /op:life-boat [save|close|cancel]"], [], true);
			} catch (err) {
				report(ctx, "refused / failed", [String(err)], [], true);
			}
		},
	});

	return { get state() { return state; } };
}
