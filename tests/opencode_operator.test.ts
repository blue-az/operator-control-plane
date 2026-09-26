import assert from "node:assert/strict";
import { test } from "node:test";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync, symlinkSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";
import plugin, { dialogs, pages } from "../adapters/opencode/index.ts";
import { COMMANDS, OperatorController, authorLabel, type Dialogs, type Context, type Command } from "../adapters/opencode/controller.ts";
import { createRunner } from "../adapters/opencode/runner.ts";
import * as core from "../.pi/extensions/operator/core.ts";

const root = fileURLToPath(new URL("../", import.meta.url));
const ok = { code: 0, stdout: "ok", stderr: "" };
function fixture(t: any) {
	const dir = mkdtempSync(join(tmpdir(), "operator-opencode-test-"));
	t.after(() => rmSync(dir, { recursive: true, force: true }));
	mkdirSync(join(dir, ".operator/tasks"), { recursive: true });
	mkdirSync(join(dir, ".operator/harnesses"), { recursive: true });
	writeFileSync(join(dir, ".operator/tasks/t1.yaml"), "task_id: t1\n");
	writeFileSync(join(dir, ".operator/harnesses/opencode-ses_fixture.yaml"), "id: opencode-ses_fixture\n");
	writeFileSync(join(dir, "operator"), "fixture");
	writeFileSync(join(dir, "evidence.log"), "fixture evidence\n");
	return dir;
}
function harness(t: any, answers: (string | undefined)[] = []) {
	const dir = fixture(t);
	let context: Context = { directory: dir, sessionID: "ses_0123456789abcdef" };
	const calls: { command: string; args: string[]; options: any }[] = [];
	const confirmations: string[] = [];
	const reports: string[] = [];
	const selections: string[] = [];
	let confirmed = true;
	let beforeConfirm = () => {};
	let result = ok;
	const signal = new AbortController();
	const ui: Dialogs = {
		async input() { return answers.shift(); },
		async select(_, choices) { return selections.shift() ?? choices[0]; },
		async confirm(_, text) { confirmations.push(text); beforeConfirm(); return confirmed; },
		async show(_, text) { reports.push(text); },
	};
	const controller = new OperatorController(() => context, ui, { async exec(command, args, options) {
		calls.push({ command, args, options }); return result;
	} }, signal.signal);
	return { dir, controller, calls, confirmations, reports, selections, signal,
		setContext(value: Context) { context = value; },
		decline() { confirmed = false; },
		beforeConfirm(fn: () => void) { beforeConfirm = fn; },
		result(value: typeof ok) { result = value; },
	};
}
const flows: [Command, (string | undefined)[]][] = [
	["op:use", ["t1"]],
	["op:brief", ["t1"]],
	["op:export-brief", ["t1"]],
	["op:session-start", ["t1"]],
	["op:session-end", ["usage-0001", "0.05"]],
	["op:claim", ["t1", "new claim", "", ""]],
	["op:evidence", ["t1", "evidence.log", "", "python3 check.py", ""]],
	["op:handoff", ["t1", "changed", "", "", "", "", "next action"]],
];
for (const [command, inputs] of flows) {
	test(`${command}: declined confirmation never invokes a write`, async (t) => {
		const h = harness(t, [...inputs]); h.decline();
		await h.controller.run(command);
		assert.equal(h.confirmations.length, 1);
		assert.equal(h.calls.length, 0);
	});
	test(`${command}: executes only the exact confirmed argv and cwd`, async (t) => {
		const h = harness(t, [...inputs]);
		await h.controller.run(command);
		assert.equal(h.confirmations.length, 1, h.reports.join("\n"));
		assert.equal(h.calls.length, 1, h.reports.join("\n"));
		const call = h.calls[0];
		assert.equal(call.command, join(h.dir, "operator"));
		assert.equal(call.options.cwd, h.dir);
		assert.ok(h.confirmations[0].includes(JSON.stringify(call.args)));
		core.assertSafeArgv(call.args);
		for (const flag of core.FORBIDDEN_FLAGS) assert.ok(!call.args.some(arg => arg === flag || arg.startsWith(`${flag}=`)));
	});
}

test("author identity uses the entire session ID, not the shared prefix", () => {
	assert.equal(authorLabel("ses_0123456789abc"), "opencode-ses_0123456789abc");
	assert.notEqual(authorLabel("ses_0123456789abc"), authorLabel("ses_0123456789xyz"));
	assert.throws(() => authorLabel(undefined));
	assert.throws(() => authorLabel("../../spoof"));
});
test("free text stays a single inline value, not authority flags or shell syntax", async (t) => {
	const text = "--status=verified $(touch marker)\n'quoted'";
	const h = harness(t, ["t1", text, "", ""]);
	await h.controller.run("op:claim");
	assert.ok(h.calls[0].args.includes(`--text=${text}`));
	assert.ok(h.calls[0].args.includes("--by=opencode-ses_0123456789abcdef"));
	assert.ok(h.confirmations[0].includes("\\n'quoted'"));
});
test("a dismissed field or missing session never writes", async (t) => {
	const h = harness(t, ["t1", undefined]);
	await h.controller.run("op:claim");
	assert.equal(h.calls.length, 0);
	const other = harness(t, ["t1", "claim", "", ""]);
	other.setContext({ directory: other.dir });
	await other.controller.run("op:claim");
	assert.equal(other.calls.length, 0);
	assert.match(other.reports[0], /Open an OpenCode session/);
});
test("session change while confirming fails closed", async (t) => {
	const h = harness(t, ["t1"]);
	h.beforeConfirm(() => h.setContext({ directory: h.dir, sessionID: "ses_other" }));
	await h.controller.run("op:use");
	assert.equal(h.calls.length, 0);
	assert.match(h.reports[0], /changed/);
});
test("ledger contract change while confirming fails closed", async (t) => {
	const h = harness(t, ["t1"]);
	const other = fixture(t);
	h.beforeConfirm(() => {
		mkdirSync(join(h.dir, ".pi"));
		writeFileSync(join(h.dir, core.LEDGER_CONTRACT_RELATIVE), JSON.stringify({ schema: core.LEDGER_CONTRACT_SCHEMA, ledger_root: other }));
	});
	await h.controller.run("op:use");
	assert.equal(h.calls.length, 0);
	assert.match(h.reports[0], /ambiguous/);
});
test("task deletion while confirming fails closed", async (t) => {
	const h = harness(t, ["t1"]);
	h.beforeConfirm(() => rmSync(join(h.dir, ".operator/tasks/t1.yaml")));
	await h.controller.run("op:use");
	assert.equal(h.calls.length, 0);
});
test("disposal while confirming fails closed", async (t) => {
	const h = harness(t, ["t1"]); h.beforeConfirm(() => h.signal.abort());
	await h.controller.run("op:use");
	assert.equal(h.calls.length, 0);
});
test("backend failure is reported without claiming rollback or treating already-running as success", async (t) => {
	const h = harness(t, ["t1"]); h.result({ code: 1, stdout: "", stderr: "Task is already running" });
	await h.controller.run("op:session-start");
	assert.match(h.reports[0], /already running/);
	assert.match(h.reports[0], /partial writes may have occurred/);
});
test("read-only commands need neither a session nor confirmation", async (t) => {
	for (const command of ["op", "op:tasks", "op:task", "op:claims", "op:sessions"] as const) {
		const h = harness(t, ["t1"]); h.setContext({ directory: h.dir });
		await h.controller.run(command);
		assert.equal(h.calls.length, 1);
		assert.ok(core.isReadOnly(h.calls[0].args));
		assert.equal(h.confirmations.length, 0);
	}
});
test("cross-project contract resolves backend; malformed and ambiguous contracts fail closed", async (t) => {
	const h = harness(t);
	const consumer = mkdtempSync(join(tmpdir(), "operator-opencode-consumer-"));
	t.after(() => rmSync(consumer, { recursive: true, force: true }));
	mkdirSync(join(consumer, ".pi"));
	const contract = join(consumer, core.LEDGER_CONTRACT_RELATIVE);
	writeFileSync(contract, JSON.stringify({ schema: core.LEDGER_CONTRACT_SCHEMA, ledger_root: h.dir }));
	h.setContext({ directory: consumer });
	await h.controller.run("op:tasks");
	assert.equal(h.calls[0].options.cwd, h.dir);
	writeFileSync(contract, "{broken");
	await h.controller.run("op:tasks");
	assert.equal(h.calls.length, 1);
	assert.match(h.reports.at(-1)!, /malformed/);
	writeFileSync(contract, JSON.stringify({ schema: core.LEDGER_CONTRACT_SCHEMA, ledger_root: h.dir }));
	mkdirSync(join(consumer, ".operator")); writeFileSync(join(consumer, "operator"), "fixture");
	await h.controller.run("op:tasks");
	assert.equal(h.calls.length, 1);
	assert.match(h.reports.at(-1)!, /ambiguous/);
});
test("wrong-task evidence claim is refused before confirmation", async (t) => {
	const h = harness(t, ["t1", "evidence.log", "claim-0001", "check", ""]);
	h.result({ code: 0, stdout: "Claim ID: claim-0001\nTask ID: t2\n", stderr: "" });
	await h.controller.run("op:evidence");
	assert.equal(h.calls.length, 1); assert.equal(h.calls[0].args[0], "claim-show");
	assert.equal(h.confirmations.length, 0);
	assert.match(h.reports[0], /does not belong/);
});
test("invalid IDs and blank costs cannot reach execution", async (t) => {
	const h = harness(t, ["../t1"]); await h.controller.run("op:use"); assert.equal(h.calls.length, 0);
	const end = harness(t, ["usage-0001", ""]); await end.controller.run("op:session-end"); assert.equal(end.calls.length, 0);
});
test("unknown optional commands cannot reach execution", async (t) => {
	const h = harness(t); await h.controller.run("op:verify-run" as Command); assert.equal(h.calls.length, 0);
});
function assertPaletteLayer(layer: any): void {
	assert.equal("mode" in layer, false, "mode-gated layers hide Operator commands in OpenCode 1.18.22");
	for (const command of layer.commands) {
		assert.equal(command.namespace, "palette");
		assert.equal(command.category, "Operator");
		assert.equal(typeof command.slashName, "string");
		assert.ok(command.slashName.length > 0);
	}
}
test("registration mock rejects the live-failing mode gate and missing palette metadata", () => {
	const command = { namespace: "palette", category: "Operator", slashName: "op" };
	assert.throws(() => assertPaletteLayer({ mode: "base", commands: [command] }), /mode-gated layers/);
	assert.throws(() => assertPaletteLayer({ mode: undefined, commands: [command] }), /mode-gated layers/);
	for (const key of ["namespace", "category", "slashName"]) {
		assert.throws(() => assertPaletteLayer({ commands: [{ ...command, [key]: undefined }] }));
	}
	assert.throws(() => assertPaletteLayer({ commands: [{ ...command, slashName: "" }] }));
});
test("TUI module registers exactly the core command set, without accessing model/server APIs", async () => {
	let layer: any;
	const api: any = {
		keymap: { registerLayer(value: any) { assertPaletteLayer(value); layer = value; } },
		ui: { DialogConfirm() {}, dialog: {} },
		lifecycle: { signal: new AbortController().signal },
		get client() { throw new Error("must not access model/server client"); },
	};
	await plugin.tui(api, undefined, {} as any);
	assert.equal("mode" in layer, false);
	assert.deepEqual(layer.commands.map((item: any) => item.slashName), COMMANDS.map(([name]) => name));
	assert.equal(layer.commands.length, 13);
	assert.deepEqual(Object.keys(plugin).sort(), ["id", "tui"]);
});
test("paged dialog text is never truncated and escapes terminal control characters", () => {
	const text = "a".repeat(15000);
	assert.equal(pages(text).join("").replaceAll("\n", ""), text);
	assert.ok(!pages("\x1b[31m\u202e")[0].includes("\x1b"));
	assert.match(pages("\x1b[31m\u202e")[0], /\\u001b/);
});
function fakeTui(decisions: (boolean | "escape")[]) {
	let close: (() => void) | undefined;
	const rendered: any[] = [];
	const signal = new AbortController();
	const api: any = {
		renderer: { width: 80, height: 30 }, lifecycle: { signal: signal.signal },
		ui: {
			dialog: {
				replace(render: () => unknown, onClose: () => void) { close = onClose; render(); },
				clear() { const old = close; close = undefined; old?.(); }, setSize() {},
			},
			DialogConfirm(props: any) { rendered.push(props); queueMicrotask(() => {
				const decision = decisions.shift();
				if (decision === "escape") api.ui.dialog.clear(); else if (decision) props.onConfirm(); else props.onCancel();
			}); },
			DialogPrompt(props: any) { queueMicrotask(() => props.onConfirm("answer")); },
			DialogSelect(props: any) { queueMicrotask(() => props.onSelect(props.options[0])); },
			toast() {},
		},
	};
	return { api, rendered, signal };
}
test("Escape on any confirmation page cancels; only accepting every page authorizes", async () => {
	const h = fakeTui([true, "escape"]);
	assert.equal(await dialogs(h.api).confirm("write", "x".repeat(2000)), false);
	assert.equal(h.rendered.length, 2);
	const yes = fakeTui(Array(30).fill(true));
	assert.equal(await dialogs(yes.api).confirm("write", "x".repeat(2000)), true);
	assert.match(yes.rendered.at(-1).title, /execute/);
});
test("prompt and select bridge host callbacks, disposal cancels pending dialogs", async () => {
	const h = fakeTui([]);
	assert.equal(await dialogs(h.api).input("test"), "answer");
	assert.equal(await dialogs(h.api).select("test", ["first", "second"]), "first");
	h.api.ui.DialogConfirm = () => { queueMicrotask(() => h.signal.abort()); };
	assert.equal(await dialogs(h.api).confirm("write", "test"), false);
});
test("too-small terminal refuses write confirmation", async () => {
	const h = fakeTui([true]); h.api.renderer.width = 20;
	assert.equal(await dialogs(h.api).confirm("write", "test"), false);
	assert.equal(h.rendered.length, 0);
});
test("terminal resizing during confirmation cancels the write", async () => {
	const h = fakeTui([]);
	h.api.ui.DialogConfirm = (props: any) => queueMicrotask(() => { h.api.renderer.width = 100; props.onConfirm(); });
	assert.equal(await dialogs(h.api).confirm("write", "exact argv"), false);
});
test("concurrent command invocation does not interleave or queue dialogs", async (t) => {
	const dir = fixture(t);
	let finish!: (value: string) => void;
	let prompts = 0;
	const controller = new OperatorController(() => ({ directory: dir }), {
		input() { prompts++; return new Promise(resolve => { finish = resolve; }); },
		async select() { return undefined; }, async confirm() { return false; }, async show() {},
	}, { async exec() { throw new Error("must not execute"); } });
	const first = controller.run("op:use");
	await controller.run("op:use");
	assert.equal(prompts, 1);
	finish("t1"); await first;
});
test("argv runner does not invoke a shell and returns nonzero exit faithfully", async (t) => {
	const dir = fixture(t);
	const marker = join(dir, "must-not-exist");
	const input = `$(touch ${marker})`;
	const runner = createRunner();
	const result = await runner.exec(process.execPath, ["-e", "process.stdout.write(process.argv[1]);process.exit(7)", input], { cwd: dir });
	assert.equal(result.code, 7); assert.equal(result.stdout, input); assert.equal(existsSync(marker), false);
});
test("real Operator disposable-ledger authoring and lifecycle round trip", async (t) => {
	const dir = mkdtempSync(join(tmpdir(), "operator-opencode-real-"));
	t.after(() => rmSync(dir, { recursive: true, force: true }));
	const operator = resolve(root, "operator");
	const op = (args: string[]) => execFileSync(operator, args, { cwd: dir, encoding: "utf8", timeout: 30_000 });
	op(["init"]); symlinkSync(operator, join(dir, "operator"));
	const id = "opencode-ses_integration";
	writeFileSync(join(dir, ".operator/harnesses", `${id}.yaml`), `id: ${id}\ndisplay_name: Disposable OpenCode session\nmodel: test-only\n`);
	op(["task-create", "--id", "t1", "--objective", "Disposable adapter integration", "--assign", id]);
	const answers: string[] = []; const selections: string[] = []; const output: string[] = [];
	const calls: { args: string[]; code: number }[] = [];
	const runner = createRunner();
	const ui: Dialogs = {
		async input() { assert.ok(answers.length, "unexpected input"); return answers.shift(); },
		async select(_, values) { const pick = selections.shift() ?? values[0]; assert.ok(values.includes(pick)); return pick; },
		async confirm(_, message) { assert.ok(message.includes(dir)); return true; },
		async show(_, message) { output.push(message); },
	};
	const controller = new OperatorController(() => ({ directory: dir, sessionID: "ses_integration" }), ui, {
		async exec(command, args, options) { const result = await runner.exec(command, args, options); calls.push({ args, code: result.code }); return result; },
	});
	answers.push("t1"); await controller.run("op:use");
	answers.push("t1", "A disposable file exists", "", ""); await controller.run("op:claim");
	writeFileSync(join(dir, "evidence.txt"), "test evidence\n");
	answers.push("t1", "evidence.txt", "claim-0001", "test -f evidence.txt", "draft evidence"); await controller.run("op:evidence");
	answers.push("t1", "Core adapter exercised", "", "", "Live TUI not tested", "", "Review adapter"); await controller.run("op:handoff");
	answers.push("t1"); selections.push(id); await controller.run("op:brief");
	answers.push("t1"); selections.push(id); await controller.run("op:export-brief");
	answers.push("t1"); selections.push(id); await controller.run("op:session-start");
	answers.push("usage-0001", "0"); selections.push("partial"); await controller.run("op:session-end");
	assert.equal(calls.length, 9, output.join("\n"));
	assert.ok(calls.every(call => call.code === 0), output.join("\n"));
	assert.equal(core.readLedgerCurrentTask(core.findLedger(dir)!), "t1");
	const claim = op(["claim-show", "--id", "claim-0001"]);
	assert.match(claim, /opencode-ses_integration/);
	assert.ok(!/^Verification status: verified$/m.test(claim));
	assert.match(op(["task-show", "--id", "t1"]), /Review adapter/);
});
