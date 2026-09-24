/** Human-only PBC and crystal workflows. No shell, downloads, model calls or verdicts. */
import { createHash, randomUUID } from "node:crypto";
import {
	existsSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, readdirSync,
	realpathSync, rmSync, writeFileSync, openSync, closeSync, fsyncSync, renameSync,
} from "node:fs";
import { homedir, tmpdir } from "node:os";
import { basename, delimiter, dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import type { ExtensionAPI, ExtensionCommandContext } from "@earendil-works/pi-coding-agent";
import * as core from "../core.ts";

export const CAPTURE_VERSION = "0.1.16";
const PACKAGE = "@stewie-sh/agent-crystallize";
const MAX_BYTES = 512_000;
export interface WorkflowHooks {
	ledger(ctx: ExtensionCommandContext): core.Ledger | null;
	writeContext(ctx: ExtensionCommandContext, command: string): {
		ledger: core.Ledger; taskId: string; by: string;
	} | null;
	emit(ctx: ExtensionCommandContext, report: core.Report): void;
}
export function digest(text: string): string {
	return createHash("sha256").update(text).digest("hex");
}
export function onePath(args: string): string {
	let value = args.trim();
	if (value.startsWith('"') && value.endsWith('"')) value = JSON.parse(value);
	else if (value.startsWith("'") && value.endsWith("'")) value = value.slice(1, -1);
	if (!value || /[\0\r\n]/.test(value) || /(^|\s)-/.test(value)) {
		throw new Error("Expected one path (quote paths with spaces), not CLI flags.");
	}
	return value;
}
function readBounded(path: string): string {
	const stat = lstatSync(path);
	if (!stat.isFile() || stat.size > MAX_BYTES) throw new Error("Expected a regular file under 512 KB.");
	return readFileSync(path, "utf8");
}
function refuseSymlink(path: string): void {
	try {
		if (lstatSync(path).isSymbolicLink()) throw new Error(`Symlink write destination refused: ${path}`);
	} catch (err) {
		if ((err as NodeJS.ErrnoException).code !== "ENOENT") throw err;
	}
}
/** Writes are workspace-local, never through symlinks or into ledger/config directories. */
export function draftPath(cwd: string, input: string): string {
	const root = realpathSync(cwd);
	if (input.split(/[\\/]/).includes("..")) throw new Error("Parent traversal is not accepted.");
	const path = resolve(root, input);
	const rel = relative(root, path);
	if (!rel || rel.startsWith(`..${sep}`) || isAbsolute(rel) || !path.endsWith(".pbc.md")) {
		throw new Error("Choose a workspace-local .pbc.md file.");
	}
	let cursor = root;
	for (const part of rel.split(sep)) {
		if ([".operator", ".git", ".pi"].includes(part)) throw new Error("Runtime/config directories are not draft destinations.");
		cursor = join(cursor, part);
		refuseSymlink(cursor);
	}
	return path;
}
export function validationArgs(ledger: core.Ledger, path: string): string[] {
	const script = join(ledger.root, "scripts", "pbc_validate_operator.py");
	if (!existsSync(script)) throw new Error(`PBC wrapper unavailable: ${script}`);
	return [script, "--format", "text", "--ledger", join(ledger.root, ".operator"), "--", path];
}
export function proposalText(kind: "define" | "feature", source: string, by: string): string {
	const data = JSON.parse(source);
	if (!data || typeof data !== "object" || Array.isArray(data)) throw new Error("Draft must be a JSON object.");
	const fields = kind === "define"
		? ["definition", "scope", "non_goals", "actors", "proposed_rules"]
		: ["name", "description", "source_links", "next_steps"];
	if (Object.keys(data).some((key) => !fields.includes(key))) throw new Error("Unknown draft fields; lifecycle/status fields are not authoring inputs.");
	for (const key of fields) {
		const array = ["scope", "non_goals", "actors", "proposed_rules", "source_links", "next_steps"].includes(key);
		if (array ? !Array.isArray(data[key]) || data[key].some((v: unknown) => typeof v !== "string") : typeof data[key] !== "string" || !data[key].trim()) {
			throw new Error(`Invalid or missing ${key}: expected ${array ? "an array of strings" : "non-empty text"}.`);
		}
	}
	// JSON is YAML-compatible. Escape backticks so authored text cannot terminate the fence.
	const block = JSON.stringify({ status: "draft", proposed_by: by,
		...(kind === "define" ? { product_shape: data } : { future_features: [data] }),
	}, null, 2).replace(/`/g, "\\u0060");
	return `\n## Proposed ${kind === "define" ? "Product Shape" : "Feature Candidate"}\n\nDraft proposal only; not ratified and not part of the current acceptance gate.\n\n\`\`\`pbc:grounding\n${block}\n\`\`\`\n`;
}
export function draftDocument(path: string, original: string | null, proposal: string): string {
	if (original !== null) {
		// Append only: existing rules/frontmatter remain byte-for-byte unchanged.
		if (!original.startsWith("---\n") && !original.startsWith("---\r\n")) throw new Error("Existing PBC requires frontmatter.");
		return original + "\n" + proposal;
	}
	const id = basename(path, ".pbc.md").replace(/[^a-zA-Z0-9_]/g, "_");
	return `---\nid: pbc_${id}\ntitle: ${JSON.stringify(basename(path, ".pbc.md"))}\nstatus: draft\nupdated: ${new Date().toISOString().slice(0, 10)}\n---\n${proposal}`;
}
/** Recheck after the UI/validator await; never silently overwrite a concurrent edit. */
export function saveDraft(cwd: string, path: string, original: string | null, content: string): void {
	draftPath(cwd, path);
	if (original === null) {
		mkdirSync(dirname(path), { recursive: true });
		writeFileSync(path, content, { encoding: "utf8", flag: "wx", mode: 0o600 });
		return;
	}
	if (readBounded(path) !== original) throw new Error("PBC changed since preview; rerun the command.");
	const temp = join(dirname(path), `.${basename(path)}.${randomUUID()}.tmp`);
	try {
		const fd = openSync(temp, "wx", lstatSync(path).mode & 0o777);
		try { writeFileSync(fd, content); fsyncSync(fd); } finally { closeSync(fd); }
		if (readBounded(path) !== original) throw new Error("PBC changed since preview; rerun the command.");
		renameSync(temp, path);
	} finally { rmSync(temp, { force: true }); }
}

/** Discover installed code only. No npx invocation, network fetch, setup or hook changes. */
export function capturePackage(cwd: string): string {
	const explicit = process.env.OPERATOR_CRYSTALLIZE_PACKAGE;
	if (explicit && !isAbsolute(explicit)) throw new Error("OPERATOR_CRYSTALLIZE_PACKAGE must be an absolute package directory.");
	const candidates = explicit ? [explicit] : [join(cwd, "node_modules", PACKAGE)];
	if (!explicit) {
		for (const dir of (process.env.PATH ?? "").split(delimiter)) {
			const bin = join(dir, "agent-crystallize");
			if (existsSync(bin)) candidates.push(resolve(dirname(realpathSync(bin)), ".."));
		}
		const cache = join(homedir(), ".npm", "_npx");
		if (existsSync(cache)) for (const entry of readdirSync(cache).sort()) candidates.push(join(cache, entry, "node_modules", PACKAGE));
	}
	for (const candidate of candidates) {
		try {
			const pkg = JSON.parse(readFileSync(join(candidate, "package.json"), "utf8"));
			const bin = join(candidate, "dist", "index.js");
			if (pkg.name === PACKAGE && pkg.version === CAPTURE_VERSION && pkg.bin?.["agent-crystallize"] === "dist/index.js" && existsSync(bin)) return realpathSync(bin);
		} catch { /* try next installed candidate */ }
	}
	throw new Error(`Capture needs installed ${PACKAGE}@${CAPTURE_VERSION}. Set OPERATOR_CRYSTALLIZE_PACKAGE to its package directory. No automatic download or version fallback.`);
}
export function captureArgs(bin: string, cwd: string, session: string, task: string, body: string, model?: { id: string; provider: string }): string[] {
	if (!session || !body.trim() || body.length > 32_000) throw new Error("Capture needs a live session and a non-empty summary under 32 KB.");
	const args = [bin, "now", "--repo", cwd, "--out-dir", ".agent-crystals/sessions",
		"--title", `Pi session ${session.slice(0, 12)} ${randomUUID()}`,
		"--surface", "cli", "--harness", "pi", "--session-id", session, "--task-id", task,
		"--body", body];
	if (model) args.push("--model", model.id, "--provenance", `provider=${model.provider}`);
	return args;
}
export function sessionSeed(ctx: ExtensionCommandContext): string {
	const entries = ctx.sessionManager.getBranch();
	const chunks: string[] = [];
	for (const entry of entries) {
		if (entry.type !== "message" || (entry.message.role !== "user" && entry.message.role !== "assistant")) continue;
		const content = entry.message.content;
		const text = typeof content === "string" ? content : content.filter((part) => part.type === "text").map((part) => (part as { text: string }).text).join("\n");
		if (text) chunks.push(`${entry.message.role}: ${text.slice(0, 2000)}`);
	}
	return `Session notes — review/redact before capture. Narration is not verification.\n\n${chunks.slice(-6).join("\n\n").slice(-10_000)}`;
}
function listCrystals(cwd: string): string[] {
	const dir = join(cwd, ".agent-crystals", "sessions");
	const found: string[] = [];
	const walk = (path: string, depth: number) => {
		if (depth > 3 || !existsSync(path) || lstatSync(path).isSymbolicLink()) return;
		for (const entry of readdirSync(path, { withFileTypes: true })) {
			const child = join(path, entry.name);
			if (entry.isDirectory()) walk(child, depth + 1);
			else if (entry.isFile() && entry.name.endsWith(".md")) found.push(child);
		}
	};
	walk(dir, 0);
	return found.sort().reverse();
}

export function createWorkflows(pi: ExtensionAPI, hooks: WorkflowHooks) {
	const report = (ctx: ExtensionCommandContext, command: string, headline: string, lines: string[] = [], invocations: string[] = [], error = false) => {
		hooks.emit(ctx, { command: `/${command}`, title: command, headline, lines, invocations, level: error ? "error" : "info" });
	};
	const invocation = (cmd: string, args: string[]) => [cmd, ...args].map((s) => JSON.stringify(s)).join(" ");
	const wrap = (command: string, fn: (args: string, ctx: ExtensionCommandContext) => Promise<void>) => async (args: string, ctx: ExtensionCommandContext) => {
		try { await fn(args, ctx); } catch (err) { report(ctx, command, "refused / failed", [String(err)], [], true); }
	};
	const validate = wrap("pbc:validate", async (args, ctx) => {
		const ledger = hooks.ledger(ctx); if (!ledger) return;
		const path = resolve(ctx.cwd, args.trim() ? onePath(args) : "owners-manual/pbc");
		if (!existsSync(path)) throw new Error(`PBC path does not exist: ${path}`);
		const argv = validationArgs(ledger, path);
		const result = await pi.exec("python3", argv, { cwd: ledger.root, timeout: 120_000 });
		report(ctx, "pbc:validate", result.code === 0 ? "compatibility check passed (not ratification)" : "validation failed",
			["Route C: upstream findings and local allowlists remain distinct.", result.stdout, result.stderr], [invocation("python3", argv)], result.code !== 0);
	});
	const author = (kind: "define" | "feature") => wrap(`pbc:${kind}`, async (args, ctx) => {
		const command = `pbc:${kind}`;
		const ledger = hooks.ledger(ctx); if (!ledger) return;
		if (!ctx.hasUI) throw new Error("Draft authoring needs a UI for editing and confirmation.");
		const by = core.deriveAuthorLabel(ctx.sessionManager.getSessionId());
		if (!by) throw new Error("No live session identity; refusing unattributed draft.");
		const input = args.trim() || await ctx.ui.input("PBC destination (.pbc.md; existing documents get an appended proposal)", "owners-manual/pbc/product.pbc.md");
		if (!input) { report(ctx, command, "cancelled; nothing written"); return; }
		const path = draftPath(ctx.cwd, onePath(input));
		const original = existsSync(path) ? readBounded(path) : null;
		const template = kind === "define"
			? { definition: "Describe the product and its purpose", scope: [], non_goals: [], actors: [], proposed_rules: [] }
			: { name: "Feature name", description: "Describe the candidate, not current acceptance scope", source_links: [], next_steps: [] };
		const edited = await ctx.ui.editor(`Draft ${kind}: edit JSON fields (no ratification)`, JSON.stringify(template, null, 2));
		if (edited === undefined) { report(ctx, command, "cancelled; nothing written"); return; }
		const proposal = proposalText(kind, edited, by);
		const content = draftDocument(path, original, proposal);
		if (content.length > MAX_BYTES) throw new Error("Draft exceeds 512 KB.");
		const temp = mkdtempSync(join(tmpdir(), "op-pbc-draft-"));
		try {
			const candidate = join(temp, basename(path));
			writeFileSync(candidate, content, { mode: 0o600 });
			const argv = validationArgs(ledger, candidate);
			const result = await pi.exec("python3", argv, { cwd: ledger.root, timeout: 120_000 });
			if (result.code !== 0) {
				report(ctx, command, "draft validation failed; destination unchanged", [result.stdout, result.stderr], [invocation("python3", argv)], true); return;
			}
			const preview = original === null ? content : proposal;
			if (!await ctx.ui.confirm(`Write draft to ${path}?`, `${original === null ? "CREATE" : "APPEND ONLY; existing content unchanged"}\nAuthor: ${by}\nNo rule ratification or ledger writes.\n\n${preview}\n\nValidation:\n${result.stdout}`)) {
				report(ctx, command, "declined; destination unchanged"); return;
			}
			saveDraft(ctx.cwd, path, original, content);
			report(ctx, command, "draft saved (not ratified)", [path, `sha256: ${digest(content)}`, "Existing rules are unchanged. Proposed rules are draft product-shape text, not canonical pbc:rules."], [invocation("python3", argv)]);
		} finally { rmSync(temp, { recursive: true, force: true }); }
	});
	const crystal = (kind: "attach" | "import") => wrap(`op:crystal-${kind}`, async (args, ctx) => {
		const command = `op:crystal-${kind}`;
		const wc = hooks.writeContext(ctx, `/${command}`); if (!wc) return;
		let input = args.trim();
		if (!input) {
			const choices = listCrystals(ctx.cwd);
			if (!choices.length) throw new Error("No session crystals found; use /op:crystal to capture or pass a path.");
			input = await ctx.ui.select("Select an existing crystal", choices) ?? "";
			if (!input) { report(ctx, command, "cancelled; nothing written"); return; }
		}
		const path = realpathSync(resolve(ctx.cwd, onePath(input)));
		const content = readBounded(path);
		const argv = core.crystalArgv({ kind, path, taskId: wc.taskId, by: wc.by, hash: digest(content), provider: ctx.model?.provider, model: ctx.model?.id });
		if (!await ctx.ui.confirm(`Confirm crystal ${kind}?`, `${invocation(wc.ledger.operatorBin, argv)}\n\nTask: ${wc.taskId}\nAuthor: ${wc.by}\nsha256: ${digest(content)}\n${kind === "import" ? "Attaches draft evidence and extracts draft claims; duplicate import is idempotent. No open-loop tasks." : "Attaches draft evidence only; does not verify."}\n\nUntrusted crystal preview:\n${content}`)) {
			report(ctx, command, "declined; nothing written"); return;
		}
		if (readBounded(path) !== content) throw new Error("Crystal changed since preview; rerun the command.");
		const result = await pi.exec(wc.ledger.operatorBin, argv, { cwd: wc.ledger.root, timeout: 120_000 });
		report(ctx, command, result.code === 0 ? "draft operation completed (not verification)" : "crystal operation failed", [result.stdout, result.stderr], [invocation(wc.ledger.operatorBin, argv)], result.code !== 0);
	});
	const capture = wrap("op:crystal", async (args, ctx) => {
		if (args.trim()) throw new Error("/op:crystal captures this session; use /op:crystal-attach <path> or /op:crystal-import <path> for existing artifacts.");
		const wc = hooks.writeContext(ctx, "/op:crystal"); if (!wc) return;
		const bin = capturePackage(ctx.cwd);
		const session = ctx.sessionManager.getSessionId();
		const body = await ctx.ui.editor("Capture current session — review/redact notes (no automatic attachment)", sessionSeed(ctx));
		if (body === undefined) { report(ctx, "op:crystal", "cancelled; nothing captured"); return; }
		const argv = captureArgs(bin, realpathSync(ctx.cwd), session, wc.taskId, body, ctx.model);
		if (!await ctx.ui.confirm("Capture session crystal?", `Installed ${PACKAGE}@${CAPTURE_VERSION}\nWrites only a local crystal; no ledger attachment, import, or verification.\n\n${invocation(process.execPath, argv)}`)) {
			report(ctx, "op:crystal", "declined; nothing captured"); return;
		}
		// Recheck after confirmation: the UI await must not leave a stale path check.
		for (const path of [join(ctx.cwd, ".agent-crystals"), join(ctx.cwd, ".agent-crystals", "sessions")]) refuseSymlink(path);
		const result = await pi.exec(process.execPath, argv, { cwd: ctx.cwd, timeout: 120_000 });
		report(ctx, "op:crystal", result.code === 0 ? "session captured; not attached" : "capture failed", [result.stdout, result.stderr, "Use /op:crystal-attach <path> or /op:crystal-import <path> separately."], [invocation(process.execPath, argv)], result.code !== 0);
	});
	return { validate, define: author("define"), feature: author("feature"), capture, attach: crystal("attach"), import: crystal("import") };
}
