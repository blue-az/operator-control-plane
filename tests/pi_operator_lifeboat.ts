import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { CAPTURE_VERSION, captureArgs, capturePackage } from "../.pi/extensions/operator/workflows/commands.ts";
import * as lb from "../.pi/extensions/operator/workflows/lifeboat.ts";

const fixture = mkdtempSync(join(tmpdir(), "op-lifeboat-"));
const savedPackage = process.env.OPERATOR_CRYSTALLIZE_PACKAGE;
let checks = 0;
async function check(name: string, fn: () => unknown) { await fn(); checks++; console.log(`ok ${name}`); }
const TWO_ATTEMPTS = "### Attempt 1: bump timeout\n- Result: still hangs\n\n### Attempt 2: retry loop\n- Result: same hang";
const PRE_LAUNCH = "PRE-LAUNCH reply: let me bump the timeout again.";
try {
	const git = (...args: string[]) => spawnSync("git", args, { cwd: fixture, encoding: "utf8" });
	git("init", "-q"); git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "base");
	const head = git("rev-parse", "HEAD").stdout.trim();

	// Real crystallize, if installed, for the output-shape check at the end.
	let realCapture: string | null = null;
	try { realCapture = capturePackage(fixture); } catch { /* optional */ }

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
	await check("only a reply after the request counts as the log", () => {
		const user = (text: string) => ({ type: "message", message: { role: "user", content: text } });
		const assistant = (content: unknown) => ({ type: "message", message: { role: "assistant", content } });
		assert.equal(lb.attemptLogReply([assistant(PRE_LAUNCH)]), null);
		assert.equal(lb.attemptLogReply([assistant(PRE_LAUNCH), user(lb.ATTEMPT_LOG_REQUEST)]), null);
		assert.equal(lb.attemptLogReply([assistant(PRE_LAUNCH), user(lb.ATTEMPT_LOG_REQUEST),
			assistant([{ type: "thinking", thinking: "hidden" }, { type: "text", text: "the log" }]),
			{ type: "message", message: { role: "toolResult", content: [{ type: "text", text: "tool" }] } }]), "the log");
	});
	await check("crystal body has no heading crystallize would escape; attempts become findings", () => {
		const body = lb.crystalBody("## Rejected Attempts\n" + TWO_ATTEMPTS, head, "");
		assert.equal(/^ {0,3}#{1,2}\s/m.test(body), false, body);
		const argv = lb.lifeboatCaptureArgs(["bin", "now"], TWO_ATTEMPTS, head);
		assert.deepEqual(argv.filter((_, i) => argv[i - 1] === "--finding"), ["Rejected attempt: Attempt 1: bump timeout", "Rejected attempt: Attempt 2: retry loop"]);
		assert.ok(argv.includes(`git HEAD ${head}`));
	});

	// A fake pi that behaves like pi 0.87.1 where it matters: sendUserMessage returns
	// before the run starts, the reply arrives later, waitForIdle does not wait for a
	// run that has not started, and sending while streaming needs deliverAs.
	const handlers: Record<string, (event: any, ctx?: any) => any> = {};
	const entries: { type: string; customType: string; data: unknown }[] = [];
	const branch: any[] = [{ type: "message", message: { role: "assistant", content: PRE_LAUNCH } }];
	let command: (args: string, ctx: any) => Promise<void> = async () => {};
	let sent: { text: string; deliverAs?: string }[] = [], execs: string[][] = [], attached: string[] = [], reports: any[] = [], confirms: string[] = [];
	let confirmed = true, taskId: string | null = "stuck-task", agentReply: string | null = TWO_ATTEMPTS, idle = true;
	let editor: (prefill: string) => string | undefined = (prefill) => prefill;
	const pi: any = {
		on: (event: string, fn: any) => { handlers[event] = fn; },
		registerCommand: (_name: string, spec: any) => { command = spec.handler; },
		appendEntry: (customType: string, data: unknown) => entries.push({ type: "custom", customType, data: JSON.parse(JSON.stringify(data)) }),
		sendUserMessage: (text: string, options?: { deliverAs?: string }) => {
			if (!idle && !options?.deliverAs) throw new Error("Agent is streaming; specify deliverAs");
			sent.push({ text, deliverAs: options?.deliverAs });
			branch.push({ type: "message", message: { role: "user", content: text } });
			const reply = agentReply;
			setTimeout(() => {
				if (reply !== null) branch.push({ type: "message", message: { role: "assistant", content: reply } });
				handlers.agent_end?.({ type: "agent_end" });
			}, 20);
		},
		exec: async (cmd: string, args: string[], opts: any) => {
			if (cmd === "git") { const p = spawnSync(cmd, args, { cwd: opts.cwd, encoding: "utf8" }); return { code: p.status ?? 1, stdout: p.stdout, stderr: p.stderr }; }
			execs.push(args);
			return { code: 0, stdout: JSON.stringify({ path: join(fixture, ".agent-crystals/sessions/c.md") }), stderr: "" };
		},
	};
	const ctx: any = {
		cwd: fixture, hasUI: true, model: { id: "m", provider: "p" },
		isIdle: () => idle,
		waitForIdle: async () => {},
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
	const bodyOf = (args: string[]) => args[args.indexOf("--body") + 1];

	taskId = null;
	await command("", ctx);
	await check("no active task: nothing sent, nothing frozen", () => { assert.equal(sent.length, 0); assert.equal(handle.state.open, false); });
	taskId = "stuck-task"; confirmed = false;
	await command("", ctx);
	await check("declined launch changes nothing", () => { assert.equal(sent.length, 0); assert.equal(handle.state.open, false); });

	reset(); confirmed = true;
	let editorSaw: string | undefined;
	editor = (prefill) => (editorSaw = prefill);
	await command("", ctx);
	await check("idle launch waits for the late reply and never saves pre-launch text", () => {
		assert.deepEqual(sent.map((s) => s.text), [lb.ATTEMPT_LOG_REQUEST]);
		assert.equal(editorSaw, TWO_ATTEMPTS);
		assert.equal(execs.length, 1);
		const body = bodyOf(execs[0]);
		assert.ok(!body.includes(PRE_LAUNCH) && body.includes("### Attempt 2: retry loop") && body.includes(`Git HEAD: ${head}`), body);
		assert.equal(attached.length, 1);
		assert.ok(!confirms.at(-1)!.includes("WARNING"));
		assert.equal(handle.state.open, true);
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

	reset(); editor = () => "### Attempt 1: only one";
	await command("save", ctx);
	await check("single-attempt log warns before capture", () => { assert.ok(confirms.at(-1)!.includes("WARNING: 1 attempt")); assert.equal(execs.length, 1); });

	reset(); editor = () => undefined;
	await command("save", ctx);
	await check("cancelled review saves nothing and stays frozen", () => { assert.equal(execs.length, 0); assert.equal(handle.state.open, true); });

	reset(); idle = false; editor = () => "Try the lock order fix.\nDo not retry: Attempt 1, Attempt 2.";
	await command("close", ctx);
	await check("close while streaming delivers the direction as a follow-up, then unfreezes", async () => {
		assert.equal(sent.length, 1);
		assert.equal(sent[0].deliverAs, "followUp");
		assert.ok(sent[0].text.includes("Do not retry: Attempt 1") && sent[0].text.includes("without citing it"));
		assert.equal(handle.state.open, false); assert.equal(await blocked("bash"), false);
	});
	idle = true;

	reset(); editor = (prefill) => prefill;
	await command("", ctx);
	await check("relaunch on the same task warns about repeated life-boats", () => assert.ok(confirms[0].includes("already had 1 life-boat")));
	const realSend = pi.sendUserMessage;
	pi.sendUserMessage = () => { throw new Error("delivery refused"); };
	reset(); editor = () => "Some direction";
	await command("close", ctx);
	await check("a direction that cannot be delivered leaves the life-boat frozen", () => {
		assert.equal(handle.state.open, true); assert.equal(reports.at(-1).level, "error");
	});
	pi.sendUserMessage = realSend;
	reset();
	await command("cancel", ctx);
	await check("cancel unfreezes without sending anything", () => { assert.equal(sent.length, 0); assert.equal(handle.state.open, false); });

	reset(); idle = false; agentReply = TWO_ATTEMPTS;
	await command("", ctx);
	await check("busy launch steers the request", () => { assert.equal(sent[0].deliverAs, "steer"); assert.equal(handle.state.open, true); });
	idle = true;
	await command("cancel", ctx);

	reset();
	await command("bogus", ctx);
	await check("unknown argument is refused", () => assert.equal(reports.at(-1).level, "error"));

	if (realCapture) {
		const log = "## Rejected Attempts\n" + TWO_ATTEMPTS;
		const argv = lb.lifeboatCaptureArgs(captureArgs(realCapture, fixture, "lifeboat-session-1", "stuck-task", lb.crystalBody(log, head, ""), undefined), log, head);
		const run = spawnSync(process.execPath, argv, { cwd: fixture, encoding: "utf8" });
		await check("real crystallize keeps attempts as headings and findings, no escaped headings", () => {
			assert.equal(run.status, 0, run.stderr);
			const text = readFileSync(JSON.parse(run.stdout).path, "utf8");
			assert.ok(!/^\\#/m.test(text), text);
			assert.ok(text.includes("### Attempt 1: bump timeout"), text);
			assert.match(text, /## Findings[\s\S]*- Rejected attempt: Attempt 2: retry loop/);
		});
	} else console.log("SKIP optional real crystallize output check");
	console.log(`${checks} life-boat checks passed`);
} finally {
	if (savedPackage === undefined) delete process.env.OPERATOR_CRYSTALLIZE_PACKAGE;
	else process.env.OPERATOR_CRYSTALLIZE_PACKAGE = savedPackage;
	rmSync(fixture, { recursive: true, force: true });
}
