import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import * as core from "../.pi/extensions/operator/core.ts";
import * as flow from "../.pi/extensions/operator/workflows/commands.ts";

const root = resolve(import.meta.dirname, "..");
const fixture = mkdtempSync(join(tmpdir(), "op-workflows-"));
const savedPackage = process.env.OPERATOR_CRYSTALLIZE_PACKAGE;
let checks = 0;
function check(name: string, fn: () => void) { fn(); checks++; console.log(`ok ${name}`); }
function cli(args: string[]) {
	return spawnSync(join(root, "operator"), args, { cwd: fixture, encoding: "utf8" });
}
try {
	assert.equal(cli(["init"]).status, 0);
	assert.equal(cli(["task-create", "--id", "workflow-task", "-o", "Workflow fixture"]).status, 0);
	symlinkSync(join(root, "operator"), join(fixture, "operator"));
	symlinkSync(join(root, "scripts"), join(fixture, "scripts"));
	const ledger = core.findLedger(fixture)!;
	const out = join(fixture, "draft.pbc.md");
	const definition = JSON.stringify({ definition: "Example product", scope: ["CLI"], non_goals: ["Authority"], actors: ["human"], proposed_rules: ["Keep drafts untrusted"] });
	const feature = JSON.stringify({ name: "Shortcut", description: "A draft only", source_links: ["issue:1"], next_steps: ["Review"] });
	check("path and lifecycle injection rejected", () => {
		for (const p of ["--profile operator", "x --out y", "../x.pbc.md", ".operator/x.pbc.md"]) assert.throws(() => flow.draftPath(fixture, flow.onePath(p)));
		assert.throws(() => flow.proposalText("define", JSON.stringify({ status: "agreed" }), "pi-session"));
		assert.throws(() => core.crystalArgv({ kind: "attach", path: "--status", taskId: "workflow-task", by: "pi-session" }));
		assert.throws(() => core.assertSafeArgv(["crystal-import", "--open-loops-as-tasks"]));
		assert.throws(() => core.assertSafeArgv(["crystal-attach", "--verdict", "pass"]));
	});
	check("symlinks and traversal refused", () => {
		symlinkSync(tmpdir(), join(fixture, "escape"));
		assert.throws(() => flow.draftPath(fixture, "escape/x.pbc.md"));
		symlinkSync(join(fixture, "absent"), join(fixture, "dangling.pbc.md"));
		assert.throws(() => flow.draftPath(fixture, "dangling.pbc.md"));
	});
	check("draft serialization cannot escape fences", () => {
		const text = flow.proposalText("feature", feature.replace("A draft only", "```pbc:rules"), "pi-session");
		assert.equal((text.match(/```/g) ?? []).length, 2);
		assert.ok(text.includes("\\u0060"));
	});
	check("save refuses stale or existing destinations", () => {
		flow.saveDraft(fixture, out, null, "old");
		assert.throws(() => flow.saveDraft(fixture, out, null, "new"));
		assert.throws(() => flow.saveDraft(fixture, out, "stale", "new"));
		assert.equal(readFileSync(out, "utf8"), "old");
		rmSync(out);
	});
	let reports: core.Report[] = [];
	let confirmed = false;
	let ui = true;
	let writeAllowed = true;
	let editor: string | undefined = definition;
	let selection: string | undefined;
	let calls: { command: string; args: string[] }[] = [];
	let validatorCode = 0;
	let useRealValidator = false;
	let captureStub = true;
	let duringConfirm: (() => void) | undefined;
	const ctx: any = {
		cwd: fixture, get hasUI() { return ui; },
		sessionManager: { getSessionId: () => "workflow-session-123", getBranch: () => [
			{ type: "message", message: { role: "user", content: "Capture this" } },
			{ type: "message", message: { role: "assistant", content: [{ type: "thinking", thinking: "DO NOT EXPORT" }, { type: "text", text: "Public summary" }] } },
			{ type: "message", message: { role: "toolResult", content: [{ type: "text", text: "PRIVATE TOOL" }] } },
		] },
		ui: { input: async () => undefined, editor: async () => editor, select: async () => selection,
			confirm: async () => { duringConfirm?.(); return confirmed; } },
	};
	const pi: any = { exec: async (command: string, args: string[]) => {
		calls.push({ command, args });
		if (command === "python3" && !useRealValidator) return { code: validatorCode, stdout: "validator result", stderr: validatorCode ? "malformed document" : "" };
		if (command === process.execPath && captureStub) return { code: 0, stdout: "capture stub", stderr: "" };
		const p = spawnSync(command, args, { cwd: fixture, encoding: "utf8", timeout: 120_000 });
		return { code: p.status ?? 1, stdout: p.stdout ?? "", stderr: p.stderr ?? "" };
	} };
	const commands = flow.createWorkflows(pi, {
		ledger: () => ledger,
		writeContext: () => writeAllowed && ui ? { ledger, taskId: "workflow-task", by: "pi-workflow-session" } : null,
		emit: (_ctx, report) => reports.push(report),
	});
	const last = () => reports.at(-1)!;
	await commands.validate("missing.pbc.md", ctx);
	check("missing validation path never executes", () => { assert.equal(calls.length, 0); assert.equal(last().level, "error"); });
	await commands.validate("--allow-unpinned", ctx);
	check("validation flags refused", () => assert.equal(calls.length, 0));
	mkdirSync(join(fixture, "pbc"));
	await commands.validate("pbc", ctx);
	check("validation uses fixed wrapper and no output writes", () => {
		assert.equal(calls.length, 1);
		assert.ok(calls[0].args.includes("--"));
		assert.ok(!calls[0].args.includes("--out"));
	});
	calls = [];
	await commands.define("draft.pbc.md", ctx);
	check("declined define leaves destination absent and temp removed", () => {
		assert.ok(!existsSync(out));
		assert.ok(!existsSync(calls[0].args.at(-1)!));
		assert.match(last().headline, /declined/);
	});
	ui = false; calls = [];
	await commands.define("draft.pbc.md", ctx);
	check("no UI refuses authoring before exec", () => assert.equal(calls.length, 0));
	ui = true; editor = undefined;
	await commands.define("draft.pbc.md", ctx);
	check("editor cancellation writes nothing", () => { assert.equal(calls.length, 0); assert.ok(!existsSync(out)); });
	editor = definition; validatorCode = 1; confirmed = true;
	await commands.define("draft.pbc.md", ctx);
	check("validator failure blocks saving", () => { assert.ok(!existsSync(out)); assert.equal(last().level, "error"); });
	validatorCode = 0;
	await commands.define("draft.pbc.md", ctx);
	const first = readFileSync(out, "utf8");
	check("define writes draft only", () => { assert.ok(first.includes("status: draft")); assert.ok(first.includes("product_shape")); assert.ok(!first.includes("```pbc:rules")); });
	editor = feature;
	await commands.feature("draft.pbc.md", ctx);
	check("feature preserves original document exactly", () => {
		const updated = readFileSync(out, "utf8"); assert.ok(updated.startsWith(first)); assert.ok(updated.includes("future_features"));
	});
	const beforeDecline = readFileSync(out, "utf8"); confirmed = false;
	await commands.feature("draft.pbc.md", ctx);
	check("declined feature leaves existing bytes unchanged", () => assert.equal(readFileSync(out, "utf8"), beforeDecline));
	confirmed = true;
	const consumer = join(fixture, "consumer"); mkdirSync(consumer); ctx.cwd = consumer;
	await commands.feature("consumer.pbc.md", ctx);
	check("external ledger authoring stays in consumer cwd", () => {
		assert.ok(existsSync(join(consumer, "consumer.pbc.md")));
		assert.ok(!existsSync(join(fixture, "consumer.pbc.md")));
		assert.ok(!existsSync(join(consumer, ".operator")));
		assert.equal(calls.at(-1)!.args[4], join(fixture, ".operator"));
	});
	ctx.cwd = fixture;
	duringConfirm = () => writeFileSync(out, first + "\nConcurrent edit\n");
	await commands.feature("draft.pbc.md", ctx);
	check("concurrent edit is not overwritten", () => { assert.equal(readFileSync(out, "utf8"), first + "\nConcurrent edit\n"); assert.equal(last().level, "error"); });
	duringConfirm = undefined;
	check("session seed omits thinking and tool results", () => {
		const seed = flow.sessionSeed(ctx); assert.ok(seed.includes("Public summary")); assert.ok(!seed.includes("DO NOT EXPORT")); assert.ok(!seed.includes("PRIVATE TOOL"));
	});
	// A structurally real crystal fixture, exercised through the real Operator CLI.
	const crystalDir = join(fixture, ".agent-crystals", "sessions"); mkdirSync(crystalDir, { recursive: true });
	const valid = join(root, "tests", "fixtures", "crystals", "valid-session.md");
	const crystalPath = join(crystalDir, "valid.md"); writeFileSync(crystalPath, readFileSync(valid));
	confirmed = false; calls = [];
	await commands.attach(crystalPath, ctx);
	check("declined attach executes nothing", () => assert.equal(calls.length, 0));
	confirmed = true;
	const originalCrystal = readFileSync(crystalPath, "utf8");
	duringConfirm = () => writeFileSync(crystalPath, originalCrystal + "\nchanged\n");
	await commands.attach(crystalPath, ctx);
	check("changed crystal is not attached", () => { assert.equal(calls.length, 0); assert.equal(last().level, "error"); });
	duringConfirm = undefined; writeFileSync(crystalPath, originalCrystal);
	const savedModel = process.env.PI_MODEL;
	try {
		process.env.PI_MODEL = "observed-model";
		ctx.model = { id: "different-model", provider: "test-provider" };
		await commands.attach(crystalPath, ctx);
		check("live model mismatch refuses attachment", () => { assert.equal(last().level, "error"); assert.match(last().lines.join("\n"), /provenance mismatch/); });
	} finally {
		if (savedModel === undefined) delete process.env.PI_MODEL; else process.env.PI_MODEL = savedModel;
		delete ctx.model;
	}
	await commands.attach(crystalPath, ctx);
	check("attach backend succeeds draft-only", () => { assert.equal(last().level, "info", JSON.stringify(last())); assert.ok(calls.at(-1)!.args.includes("--hash")); assert.ok(calls.at(-1)!.args.includes("--task")); });
	await commands.import(crystalPath, ctx);
	check("import backend succeeds", () => assert.equal(last().level, "info", JSON.stringify(last())));
	await commands.import(crystalPath, ctx);
	check("duplicate import is idempotent", () => assert.match(last().lines.join("\n"), /already imported|already attached/i));
	writeFileSync(join(crystalDir, "broken.md"), "not a crystal");
	await commands.attach(join(crystalDir, "broken.md"), ctx);
	check("invalid crystal refused by backend", () => assert.equal(last().level, "error"));
	selection = crystalPath; calls = [];
	await commands.attach("", ctx);
	check("no-argument attach chooses an existing crystal", () => assert.equal(calls.at(-1)!.args[1], crystalPath));
	selection = undefined; calls = [];
	await commands.import("", ctx);
	check("chooser cancellation executes nothing", () => assert.equal(calls.length, 0));
	writeAllowed = false;
	await commands.attach(crystalPath, ctx);
	check("missing task/identity blocks crystal writes", () => assert.equal(calls.length, 0));
	writeAllowed = true;
	const fakePackage = join(fixture, "fake-package"); mkdirSync(join(fakePackage, "dist"), { recursive: true });
	writeFileSync(join(fakePackage, "dist", "index.js"), "");
	writeFileSync(join(fakePackage, "package.json"), JSON.stringify({ name: "@stewie-sh/agent-crystallize", version: "99.0.0", bin: { "agent-crystallize": "dist/index.js" } }));
	process.env.OPERATOR_CRYSTALLIZE_PACKAGE = fakePackage;
	check("wrong capture version has no fallback", () => assert.throws(() => flow.capturePackage(fixture)));
	writeFileSync(join(fakePackage, "package.json"), JSON.stringify({ name: "@stewie-sh/agent-crystallize", version: flow.CAPTURE_VERSION, bin: { "agent-crystallize": "dist/index.js" } }));
	editor = "Reviewed capture"; confirmed = false;
	await commands.capture("", ctx);
	check("capture cancellation executes nothing without optional dependencies", () => assert.equal(calls.length, 0));
	confirmed = true; ui = false;
	await commands.capture("", ctx);
	check("capture without UI executes nothing", () => assert.equal(calls.length, 0));
	ui = true;
	process.env.OPERATOR_CRYSTALLIZE_PACKAGE = join(fixture, "missing-package");
	await commands.capture("", ctx);
	check("missing capture dependency fails closed without download", () => { assert.equal(calls.length, 0); assert.equal(last().level, "error"); });
	// Installed package is optional in CI, but runs a real capture/parse smoke when available.
	if (savedPackage === undefined) delete process.env.OPERATOR_CRYSTALLIZE_PACKAGE;
	else process.env.OPERATOR_CRYSTALLIZE_PACKAGE = savedPackage;
	let captureBin: string | undefined;
	try { captureBin = flow.capturePackage(fixture); } catch { console.log("SKIP optional installed crystallize capture smoke"); }
	if (captureBin) {
		editor = "Public session summary"; confirmed = false; calls = [];
		await commands.capture("", ctx);
		check("declined capture executes nothing", () => assert.equal(calls.length, 0));
		confirmed = true; captureStub = false;
		await commands.capture("", ctx);
		check("real installed capture succeeds", () => { assert.equal(last().level, "info", JSON.stringify(last())); assert.ok(calls.at(-1)!.args.includes("workflow-session-123")); });
		const result = JSON.parse(last().lines[0]);
		await commands.attach(result.path, ctx);
		check("captured schema accepted by Operator", () => assert.equal(last().level, "info", JSON.stringify(last())));
	}
	// Wrapper depends on a separately installed pinned pbc-spec; never download it.
	useRealValidator = true;
	await commands.validate(out, ctx);
	if (last().level === "info") {
		check("real pinned validator accepts generated drafts", () => assert.match(last().lines.join("\n"), /remaining CLI errors none/));
		editor = definition;
		await commands.define("real.pbc.md", ctx);
		check("real validated authoring saves", () => assert.ok(existsSync(join(fixture, "real.pbc.md")), JSON.stringify(last())));
		const brokenPbc = join(fixture, "broken.pbc.md");
		const brokenText = "---\nid: [invalid YAML\n---\n";
		writeFileSync(brokenPbc, brokenText);
		await commands.validate(brokenPbc, ctx);
		check("real validator rejects malformed PBC without modifying it", () => {
			assert.equal(last().level, "error"); assert.equal(readFileSync(brokenPbc, "utf8"), brokenText);
		});
		editor = feature;
		await commands.feature(brokenPbc, ctx);
		check("real draft validation blocks appending to malformed document", () => {
			assert.equal(last().level, "error"); assert.equal(readFileSync(brokenPbc, "utf8"), brokenText);
		});
	} else if (/path not found|not built/.test(last().lines.join("\n"))) console.log("SKIP optional pinned PBC validator smoke");
	else assert.fail(JSON.stringify(last()));
	console.log(`${checks} workflow checks passed`);
} finally {
	if (savedPackage === undefined) delete process.env.OPERATOR_CRYSTALLIZE_PACKAGE;
	else process.env.OPERATOR_CRYSTALLIZE_PACKAGE = savedPackage;
	rmSync(fixture, { recursive: true, force: true });
}
