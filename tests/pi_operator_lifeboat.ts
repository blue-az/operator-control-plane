import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { CAPTURE_VERSION } from "../.pi/extensions/operator/workflows/commands.ts";
import * as lb from "../.pi/extensions/operator/workflows/lifeboat.ts";

const fixture = mkdtempSync(join(tmpdir(), "op-lifeboat-"));
const savedPackage = process.env.OPERATOR_CRYSTALLIZE_PACKAGE;
let checks = 0;
async function check(name: string, fn: () => unknown) { await fn(); checks++; console.log(`ok ${name}`); }
const TWO_ATTEMPTS = "### Attempt 1: bump timeout\n- Result: still hangs\n\n### Attempt 2: retry loop\n- Result: same hang";
try {
	const git = (...args: string[]) => spawnSync("git", args, { cwd: fixture, encoding: "utf8" });
	git("init", "-q"); git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "base");
	const head = git("rev-parse", "HEAD").stdout.trim();
	const fakePackage = join(fixture, "fake-package"); mkdirSync(join(fakePackage, "dist"), { recursive: true });
	writeFileSync(join(fakePackage, "dist", "index.js"), "");
	writeFileSync(join(fakePackage, "package.json"), JSON.stringify({ name: "@stewie-sh/agent-crystallize", version: CAPTURE_VERSION, bin: { "agent-crystallize": "dist/index.js" } }));
	process.env.OPERATOR_CRYSTALLIZE_PACKAGE = fakePackage;

	await check("freeze allows only read-only tools, and nothing when closed", () => {
		const open = { ...lb.initialState(), open: true };
		assert.equal(lb.freezeDecision(lb.initialState(), "bash"), undefined);
		for (const tool of lb.READ_ONLY_TOOLS) assert.equal(lb.freezeDecision(open, tool), undefined);
		for (const tool of ["bash", "edit", "write", "mcp_unknown"]) assert.equal(lb.freezeDecision(open, tool)?.block, true);
	});
	await check("assistant text skips thinking and tool results", () => {
		assert.equal(lb.lastAssistantText([
			{ type: "message", message: { role: "assistant", content: [{ type: "thinking", thinking: "hidden" }, { type: "text", text: "log" }] } },
			{ type: "message", message: { role: "toolResult", content: [{ type: "text", text: "tool" }] } },
		]), "log");
		assert.equal(lb.lastAssistantText([]), null);
	});

	const handlers: Record<string, (event: any, ctx?: any) => any> = {};
	const entries: { type: string; customType: string; data: unknown }[] = [];
	const branch: any[] = [];
	let command: (args: string, ctx: any) => Promise<void> = async () => {};
	let sent: string[] = [], execs: string[][] = [], attached: string[] = [], reports: any[] = [], confirms: string[] = [];
	let confirmed = true, taskId: string | null = "stuck-task", agentReply = TWO_ATTEMPTS;
	let editor: (prefill: string) => string | undefined = (prefill) => prefill;
	const pi: any = {
		on: (event: string, fn: any) => { handlers[event] = fn; },
		registerCommand: (_name: string, spec: any) => { command = spec.handler; },
		appendEntry: (customType: string, data: unknown) => entries.push({ type: "custom", customType, data: JSON.parse(JSON.stringify(data)) }),
		sendUserMessage: (text: string) => { sent.push(text); },
		exec: async (cmd: string, args: string[], opts: any) => {
			if (cmd === "git") { const p = spawnSync(cmd, args, { cwd: opts.cwd, encoding: "utf8" }); return { code: p.status ?? 1, stdout: p.stdout, stderr: p.stderr }; }
			execs.push(args);
			return { code: 0, stdout: JSON.stringify({ path: join(fixture, ".agent-crystals/sessions/c.md") }), stderr: "" };
		},
	};
	const ctx: any = {
		cwd: fixture, hasUI: true, model: { id: "m", provider: "p" },
		isIdle: () => true,
		waitForIdle: async () => { branch.push({ type: "message", message: { role: "assistant", content: agentReply } }); },
		sessionManager: { getSessionId: () => "lifeboat-session-1", getBranch: () => branch, getEntries: () => entries },
		ui: { editor: async (_title: string, prefill: string) => editor(prefill), confirm: async (_t: string, body: string) => { confirms.push(body); return confirmed; } },
	};
	const hooks = {
		ledger: () => null,
		writeContext: () => (taskId ? { ledger: {} as any, taskId, by: "pi-lifeboat" } : null),
		emit: (_ctx: any, report: any) => reports.push(report),
		attach: async (path: string) => { attached.push(path); },
	};
	const handle = lb.registerLifeboat(pi, hooks);
	const blocked = async (tool: string) => (await handlers.tool_call({ toolName: tool }))?.block === true;
	const reset = () => { sent = []; execs = []; attached = []; reports = []; confirms = []; };

	taskId = null;
	await command("", ctx);
	await check("no active task: nothing sent, nothing frozen", async () => {
		assert.equal(sent.length, 0); assert.equal(handle.state.open, false);
	});
	taskId = "stuck-task"; confirmed = false;
	await command("", ctx);
	await check("declined launch changes nothing", () => { assert.equal(sent.length, 0); assert.equal(handle.state.open, false); });

	reset(); confirmed = true;
	await command("", ctx);
	await check("launch asks for the log, freezes, saves crystal, offers attach", async () => {
		assert.deepEqual(sent, [lb.ATTEMPT_LOG_REQUEST]);
		assert.equal(handle.state.open, true);
		assert.equal(execs.length, 1);
		const body = execs[0][execs[0].indexOf("--body") + 1];
		assert.ok(body.includes("## Rejected Attempts") && body.includes(TWO_ATTEMPTS) && body.includes(`Git HEAD: ${head}`), body);
		assert.equal(attached.length, 1);
		assert.ok(!confirms.at(-1)!.includes("WARNING"));
	});
	await check("bash and edit blocked while open, read allowed", async () => {
		assert.equal(await blocked("bash"), true); assert.equal(await blocked("edit"), true); assert.equal(await blocked("read"), false);
	});
	await check("state survives a session restart", () => {
		handlers.session_start({}, ctx); assert.equal(handle.state.open, true); assert.equal(handle.state.launches["stuck-task"], 1);
	});

	reset();
	await command("", ctx);
	await check("second launch while open is refused", () => { assert.equal(sent.length, 0); assert.equal(reports.at(-1).level, "error"); });

	reset(); agentReply = "### Attempt 1: only one"; editor = () => "### Attempt 1: only one";
	await command("save", ctx);
	await check("single-attempt log warns before capture", () => { assert.ok(confirms.at(-1)!.includes("WARNING: 1 attempt")); assert.equal(execs.length, 1); });

	reset(); editor = () => undefined;
	await command("save", ctx);
	await check("cancelled review saves nothing and stays frozen", () => { assert.equal(execs.length, 0); assert.equal(handle.state.open, true); });

	reset(); editor = () => "Try the lock order fix.\nDo not retry: Attempt 1, Attempt 2.";
	await command("close", ctx);
	await check("close hands direction back with the do-not-retry rule and unfreezes", async () => {
		assert.equal(sent.length, 1);
		assert.ok(sent[0].includes("Do not retry: Attempt 1") && sent[0].includes("without citing it"));
		assert.equal(handle.state.open, false); assert.equal(await blocked("bash"), false);
	});

	reset(); agentReply = TWO_ATTEMPTS; editor = (prefill) => prefill;
	await command("", ctx);
	await check("relaunch on the same task warns about repeated life-boats", () => assert.ok(confirms[0].includes("already had 1 life-boat")));
	reset();
	await command("cancel", ctx);
	await check("cancel unfreezes without sending anything", () => { assert.equal(sent.length, 0); assert.equal(handle.state.open, false); });

	reset();
	await command("bogus", ctx);
	await check("unknown argument is refused", () => assert.equal(reports.at(-1).level, "error"));
	console.log(`${checks} life-boat checks passed`);
} finally {
	if (savedPackage === undefined) delete process.env.OPERATOR_CRYSTALLIZE_PACKAGE;
	else process.env.OPERATOR_CRYSTALLIZE_PACKAGE = savedPackage;
	rmSync(fixture, { recursive: true, force: true });
}
