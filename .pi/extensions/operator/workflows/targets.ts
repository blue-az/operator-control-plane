/** Confirmed edits to the exact registry /op:delegate already reads. No launches or ledger writes. */
import { randomUUID } from "node:crypto";
import { closeSync, existsSync, fsyncSync, lstatSync, mkdirSync, openSync, readFileSync, realpathSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, relative, sep } from "node:path";
import type { ExtensionCommandContext } from "@earendil-works/pi-coding-agent";
import * as core from "../core.ts";
import type { WorkflowHooks } from "./commands.ts";

const LIMIT = 256_000;
export type TargetAction = "list" | "add" | "edit" | "remove";
export function parseTargetArgs(args: string): { action: TargetAction | null; alias?: string } {
	const parts = args.trim().split(/\s+/).filter(Boolean);
	if (!parts.length) return { action: null };
	if (!["list", "add", "edit", "remove"].includes(parts[0]) || parts.length > 2 ||
		(parts.length === 2 && (!["edit", "remove"].includes(parts[0]) || !core.isValidHarnessId(parts[1])))) {
		throw new Error("Usage: /op:targets [list|add|edit <alias>|remove <alias>]");
	}
	return { action: parts[0] as TargetAction, alias: parts[1] };
}
function wire(target: core.DelegateTarget): Record<string, unknown> {
	return { alias: target.alias, harness_id: target.harnessId, carrier_id: target.carrierId,
		model: target.model, isolation: target.isolation, brief_format: target.briefFormat, command_template: target.commandTemplate };
}
export function readRegistry(ledger: core.Ledger): string | null {
	const path = core.delegateTargetsPath(ledger);
	if (!existsSync(path)) return null;
	const stat = lstatSync(path);
	if (!stat.isFile() || stat.size > LIMIT) throw new Error("Registry must be a regular JSON file under 256 KB.");
	return readFileSync(path, "utf8");
}
function targets(original: string | null): core.DelegateTarget[] {
	return original === null ? core.DEFAULT_DELEGATE_TARGETS.map((t) => ({ ...t })) : core.parseDelegateTargetsJson(original);
}
/** Preserve top-level metadata and untouched rows; normalize only the changed row's known fields. */
export function patchRegistry(original: string | null, action: Exclude<TargetAction, "list">, alias: string | undefined, target?: core.DelegateTarget): string {
	const current = targets(original);
	const document = original === null ? { targets: current.map(wire) } : JSON.parse(original);
	const index = current.findIndex((t) => t.alias === alias);
	if (action !== "add" && index < 0) throw new Error(`Unknown target alias: ${alias}`);
	if (action === "remove") document.targets.splice(index, 1);
	else {
		if (!target) throw new Error("Missing target draft");
		const valid = core.validateDelegateTarget(target);
		if (current.some((t, i) => t.alias === valid.alias && (action === "add" || i !== index))) throw new Error(`Duplicate target alias: ${valid.alias}`);
		if (action === "add") document.targets.push(wire(valid));
		else {
			const row = { ...document.targets[index] };
			for (const key of ["harnessId", "carrierId", "briefFormat", "commandTemplate"]) delete row[key];
			document.targets[index] = { ...row, ...wire(valid) };
		}
	}
	const content = JSON.stringify(document, null, 2) + "\n";
	core.parseDelegateTargetsJson(content); // includes empty-list, duplicate and routing-field refusal
	if (Buffer.byteLength(content) > LIMIT) throw new Error("Registry exceeds 256 KB.");
	return content;
}
function safeRegistryPath(ledger: core.Ledger): string {
	const root = realpathSync(ledger.root);
	const path = join(root, ".pi", "extensions", "operator", "targets.json");
	let cursor = root;
	for (const part of relative(root, path).split(sep)) {
		cursor = join(cursor, part);
		try {
			if (lstatSync(cursor).isSymbolicLink()) throw new Error(`Refusing symlink registry path: ${cursor}`);
		} catch (err) { if ((err as NodeJS.ErrnoException).code !== "ENOENT") throw err; }
	}
	return path;
}
/** Lock cooperating writers, recheck the preview snapshot, then replace atomically. */
export function saveRegistry(ledger: core.Ledger, original: string | null, content: string): void {
	core.parseDelegateTargetsJson(content);
	const path = safeRegistryPath(ledger);
	mkdirSync(dirname(path), { recursive: true });
	const lock = join(dirname(path), ".targets.json.lock");
	const lockFd = openSync(lock, "wx", 0o600); // existing lock fails closed; never remove another writer's lock
	const temp = join(dirname(path), `.targets.${randomUUID()}.tmp`);
	try {
		if (readRegistry(ledger) !== original) throw new Error("Registry changed since preview; rerun /op:targets.");
		const fd = openSync(temp, "wx", original === null ? 0o600 : lstatSync(path).mode & 0o777);
		try { writeFileSync(fd, content); fsyncSync(fd); } finally { closeSync(fd); }
		safeRegistryPath(ledger);
		if (readRegistry(ledger) !== original) throw new Error("Registry changed since preview; rerun /op:targets.");
		renameSync(temp, path);
	} finally { closeSync(lockFd); rmSync(temp, { force: true }); rmSync(lock, { force: true }); }
}
function describe(ledger: core.Ledger, target: core.DelegateTarget): string {
	let model: string;
	try { model = core.resolveDelegateTarget(ledger, target).model; }
	catch (err) { model = `UNAVAILABLE (${String(err)})`; }
	return `${target.alias}: harness=${target.harnessId}; carrier=${target.carrierId}; model=${target.model ?? "(inherit)"} → ${model}; isolation=${target.isolation}; brief=${target.briefFormat}; display-only hint=${target.commandTemplate ?? "(none)"}`;
}
async function editTarget(ctx: ExtensionCommandContext, existing?: core.DelegateTarget): Promise<core.DelegateTarget | null> {
	const alias = await ctx.ui.input("Target alias", existing?.alias ?? "");
	if (alias === undefined) return null;
	const harnessId = await ctx.ui.input("Existing registered harness ID (not a role label)", existing?.harnessId ?? "");
	if (harnessId === undefined) return null;
	const carrierId = await ctx.ui.select(`Carrier / adapter (current: ${existing?.carrierId ?? "none"})`, [...core.ADAPTER_CARRIER_IDS]);
	if (carrierId === undefined) return null;
	const model = await ctx.ui.input("Model ID (empty = inherit registered harness model)", existing?.model ?? "");
	if (model === undefined) return null;
	const isolation = await ctx.ui.select(`Isolation (current: ${existing?.isolation ?? "none"})`, [...core.DELEGATE_ISOLATION_MODES]);
	if (isolation === undefined) return null;
	const briefFormat = await ctx.ui.select(`Brief format (current: ${existing?.briefFormat ?? "none"})`, [...core.DELEGATE_BRIEF_FORMATS]);
	if (briefFormat === undefined) return null;
	const commandTemplate = await ctx.ui.input("Display-only launch hint; never executed (empty = none)", existing?.commandTemplate ?? "");
	if (commandTemplate === undefined) return null;
	return core.validateDelegateTarget({ alias, harnessId, carrierId, model: model.trim() || null,
		isolation: isolation as core.DelegateIsolation, briefFormat: briefFormat as core.DelegateBriefFormat,
		commandTemplate: commandTemplate.trim() || null });
}
export function createTargetHandler(hooks: Pick<WorkflowHooks, "ledger" | "emit">) {
	return async (args: string, ctx: ExtensionCommandContext): Promise<void> => {
		const emit = (headline: string, lines: string[] = [], error = false) => hooks.emit(ctx, {
			command: "/op:targets", title: "Delegation target registry", headline,
			lines, invocations: [], level: error ? "error" : "info",
		});
		try {
			const parsed = parseTargetArgs(args);
			const ledger = hooks.ledger(ctx); if (!ledger) return;
			const original = readRegistry(ledger);
			const current = targets(original);
			let action = parsed.action;
			if (!action) {
				if (!ctx.hasUI) action = "list";
				else action = await ctx.ui.select("Target registry: configuration only; no task routing changes", ["list", "add", "edit", "remove"]) as TargetAction | undefined ?? null;
				if (!action) { emit("cancelled; nothing written"); return; }
			}
			if (action === "list") {
				emit(original === null ? "built-in defaults (no registry file)" : `${current.length} configured targets`,
					[core.delegateTargetsPath(ledger), ...current.map((t) => describe(ledger, t)), "This registry does not assign tasks, register harnesses or authorize reviews."]);
				return;
			}
			if (!ctx.hasUI) throw new Error("Registry changes need a UI and explicit confirmation.");
			const by = core.deriveAuthorLabel(ctx.sessionManager.getSessionId());
			if (!by) throw new Error("No live session identity; refusing unattributed configuration change.");
			let alias = parsed.alias;
			if (action !== "add" && !alias) {
				alias = await ctx.ui.select("Target alias", current.map((t) => t.alias));
				if (alias === undefined) { emit("cancelled; nothing written"); return; }
			}
			const before = current.find((t) => t.alias === alias);
			if (action !== "add" && !before) throw new Error(`Unknown target alias: ${alias}`);
			let draft: core.DelegateTarget | undefined;
			let resolutionSnapshot: string | undefined;
			if (action !== "remove") {
				const edited = await editTarget(ctx, before);
				if (!edited) { emit("cancelled; nothing written"); return; }
				// The registry editor cannot invent harness identities or accept an unresolved model.
				const resolved = core.resolveDelegateTarget(ledger, edited);
				if (resolved.harness.harnessId !== edited.harnessId) throw new Error("Harness record ID does not match its registry filename.");
				resolutionSnapshot = JSON.stringify(resolved);
				draft = edited;
			}
			const content = patchRegistry(original, action, alias, draft);
			safeRegistryPath(ledger);
			const summary = [
				`WRITE ${core.delegateTargetsPath(ledger)}`,
				`Control-plane registry shared by consumers of this ledger. Session: ${by}`,
				`Before: ${before ? describe(ledger, before) : "(new target)"}`,
				`After: ${draft ? describe(ledger, draft) : "(removed)"}`,
				"No task assignments, reviewer routing, harness records, identity policy or verification status are changed. No agent is launched.",
				"Exact proposed registry:", content,
			];
			if (!await ctx.ui.confirm(`Confirm target ${action}?`, summary.join("\n\n"))) { emit("declined; nothing written"); return; }
			if (draft) { // Recheck the harness after waiting for confirmation.
				const resolved = core.resolveDelegateTarget(ledger, draft);
				if (JSON.stringify(resolved) !== resolutionSnapshot) throw new Error("Harness/model changed during confirmation; rerun /op:targets.");
			}
			saveRegistry(ledger, original, content);
			emit("registry saved; task routing unchanged", summary);
		} catch (err) { emit("refused / failed", [String(err)], true); }
	};
}
