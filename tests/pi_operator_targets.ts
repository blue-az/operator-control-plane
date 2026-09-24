import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync, existsSync, readdirSync, rmSync, symlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import * as core from "../.pi/extensions/operator/core.ts";
import { createTargetHandler, parseTargetArgs, patchRegistry, saveRegistry } from "../.pi/extensions/operator/workflows/targets.ts";

const root = mkdtempSync(join(tmpdir(), "op-targets-"));
let checks = 0;
const check = (name: string, fn: () => void) => { fn(); checks++; console.log(`ok ${name}`); };
try {
	mkdirSync(join(root, ".operator", "harnesses"), { recursive: true });
	mkdirSync(join(root, ".operator", "tasks"));
	writeFileSync(join(root, "operator"), "");
	writeFileSync(join(root, ".operator", "operator.yaml"), "current_task: test-task\n");
	const task = join(root, ".operator", "tasks", "test-task.yaml");
	const routing = "task_id: test-task\nassigned_harness: builder\nreview_harness: reviewer\n";
	writeFileSync(task, routing);
	const harnessPath = join(root, ".operator", "harnesses", "builder.yaml");
	const harness = "harness_id: builder\nmodel: test-model\nkind: cli\ncommand: pi\n";
	writeFileSync(harnessPath, harness);
	const ledger = core.findLedger(root)!;
	const path = core.delegateTargetsPath(ledger);
	mkdirSync(join(root, ".pi", "extensions", "operator"), { recursive: true });
	const target: core.DelegateTarget = { alias: "worker", harnessId: "builder", carrierId: "pi", model: null, isolation: "in-repo", briefFormat: "export", commandTemplate: null };
	// Resolve supported carrier from the fixed adapter list rather than assuming Pi is a profile.
	target.carrierId = core.ADAPTER_CARRIER_IDS[0];
	const initial = JSON.stringify({ note: "keep metadata", targets: [
		{ alias: "worker", harness_id: "builder", carrier_id: target.carrierId, model: null, isolation: "in-repo", brief_format: "export", note: "keep row metadata" },
		{ alias: "unavailable", harness_id: "absent", carrier_id: target.carrierId, model: null },
	] }, null, 2) + "\n";
	writeFileSync(path, initial);
	check("strict action syntax", () => {
		assert.deepEqual(parseTargetArgs(""), { action: null });
		assert.deepEqual(parseTargetArgs("edit worker"), { action: "edit", alias: "worker" });
		for (const value of ["raw", "list extra", "add extra", "edit --status", "edit worker extra"]) assert.throws(() => parseTargetArgs(value));
	});
	check("patch preserves metadata and untouched rows", () => {
		const patched = JSON.parse(patchRegistry(initial, "edit", "worker", { ...target, alias: "renamed" }));
		assert.equal(patched.note, "keep metadata"); assert.equal(patched.targets[0].note, "keep row metadata");
		assert.deepEqual(patched.targets[1], JSON.parse(initial).targets[1]);
	});
	check("duplicates, invented routing and empty registries refused", () => {
		assert.throws(() => patchRegistry(initial, "add", undefined, target));
		assert.throws(() => patchRegistry(initial, "edit", "worker", { ...target, alias: "unavailable" }));
		assert.throws(() => patchRegistry(initial, "edit", "absent", target));
		assert.throws(() => patchRegistry('{"targets":[],"assigned_harness":"x"}', "add", undefined, target));
		const one = JSON.stringify({ targets: [JSON.parse(initial).targets[0]] });
		assert.throws(() => patchRegistry(one, "remove", "worker"));
	});
	let reports: core.Report[] = [];
	let confirm = false;
	let hasUI = true;
	let id = "12345678-session";
	let inputs: (string | undefined)[] = [];
	let selections: (string | undefined)[] = [];
	let confirmation = "";
	let onConfirm: (() => void) | undefined;
	const consumer = join(root, "consumer"); mkdirSync(consumer);
	const ctx: any = { cwd: consumer, get hasUI() { return hasUI; }, sessionManager: { getSessionId: () => id }, ui: {
		input: async () => inputs.shift(), select: async () => selections.shift(),
		confirm: async (_title: string, text: string) => { confirmation = text; onConfirm?.(); return confirm; },
	} };
	const handler = createTargetHandler({ ledger: () => ledger, emit: (_ctx, report) => reports.push(report) });
	const last = () => reports.at(-1)!;
	const form = (alias = "new-worker", harnessId = "builder", model = "") => {
		inputs = [alias, harnessId, model, "never executed hint"];
		selections = [target.carrierId, "in-repo", "export"];
	};
	await handler("list", ctx);
	check("list reports unresolved targets without failing", () => {
		assert.equal(last().level, "info"); assert.match(last().lines.join("\n"), /UNAVAILABLE/); assert.equal(readFileSync(path, "utf8"), initial);
	});
	hasUI = false;
	await handler("", ctx);
	check("no-UI default is read-only list", () => assert.equal(last().level, "info"));
	await handler("add", ctx);
	check("no-UI mutations refused", () => { assert.equal(last().level, "error"); assert.equal(readFileSync(path, "utf8"), initial); });
	hasUI = true; id = "";
	await handler("add", ctx);
	check("missing session identity refuses changes", () => assert.equal(last().level, "error"));
	id = "12345678-session";
	inputs = [undefined]; await handler("add", ctx);
	check("cancelled form leaves bytes unchanged", () => assert.equal(readFileSync(path, "utf8"), initial));
	form(); await handler("add", ctx);
	check("declined add previews exact control-plane path and changes nothing", () => {
		assert.match(last().headline, /declined/); assert.ok(confirmation.includes(path)); assert.ok(confirmation.includes("Exact proposed registry"));
		assert.equal(readFileSync(path, "utf8"), initial);
	});
	confirm = true; form("new-worker", "invented"); await handler("add", ctx);
	check("unregistered harness refused", () => { assert.equal(last().level, "error"); assert.equal(readFileSync(path, "utf8"), initial); });
	form("new-worker", "builder", "--verdict"); await handler("add", ctx);
	check("flag-shaped model refused", () => assert.equal(last().level, "error"));
	form(); selections[1] = "arbitrary-isolation"; await handler("add", ctx);
	check("invalid isolation refused", () => assert.equal(last().level, "error"));
	form(); selections[0] = "arbitrary-carrier"; await handler("add", ctx);
	check("invalid carrier refused", () => assert.equal(last().level, "error"));
	form(); await handler("add", ctx);
	check("confirmed add writes only control-plane registry", () => {
		assert.equal(last().level, "info", JSON.stringify(last()));
		assert.ok(core.loadDelegateTargets(ledger).some((t) => t.alias === "new-worker"));
		assert.equal(readFileSync(task, "utf8"), routing); assert.equal(readFileSync(harnessPath, "utf8"), harness);
		assert.deepEqual(readdirSync(consumer), []); assert.ok(!existsSync(join(dirnameOfRegistry(), ".targets.json.lock")));
	});
	const added = readFileSync(path, "utf8");
	form("new-worker", "builder", "different-model"); await handler("edit new-worker", ctx);
	check("confirmed edit changes model without routing mutation", () => {
		assert.equal(core.loadDelegateTargets(ledger).find((t) => t.alias === "new-worker")!.model, "different-model");
		assert.equal(readFileSync(task, "utf8"), routing);
	});
	confirm = false; await handler("remove new-worker", ctx);
	check("declined removal preserves alias", () => assert.ok(core.loadDelegateTargets(ledger).some((t) => t.alias === "new-worker")));
	confirm = true; await handler("remove new-worker", ctx);
	check("confirmed removal leaves other rows", () => assert.deepEqual(core.loadDelegateTargets(ledger).map((t) => t.alias), ["worker", "unavailable"]));
	const snapshot = readFileSync(path, "utf8");
	form(); onConfirm = () => writeFileSync(path, added); await handler("add", ctx);
	check("stale registry preview refused", () => { assert.equal(last().level, "error"); assert.equal(readFileSync(path, "utf8"), added); });
	onConfirm = undefined; writeFileSync(path, snapshot);
	form(); onConfirm = () => writeFileSync(harnessPath, harness.replace("test-model", "new-model")); await handler("add", ctx);
	check("inherited model change during confirmation refused", () => { assert.equal(last().level, "error"); assert.equal(readFileSync(path, "utf8"), snapshot); });
	onConfirm = undefined; writeFileSync(harnessPath, harness);
	writeFileSync(harnessPath, harness.replace("harness_id: builder", "harness_id: other"));
	form(); await handler("add", ctx);
	check("mismatched harness record ID refused", () => assert.equal(last().level, "error"));
	writeFileSync(harnessPath, harness);
	const lock = join(dirnameOfRegistry(), ".targets.json.lock"); writeFileSync(lock, "other writer");
	check("existing writer lock preserved", () => {
		assert.throws(() => saveRegistry(ledger, snapshot, added)); assert.equal(readFileSync(lock, "utf8"), "other writer");
	}); rmSync(lock);
	rmSync(path); symlinkSync(join(root, "elsewhere.json"), path);
	check("dangling symlink write refused", () => assert.throws(() => saveRegistry(ledger, null, added)));
	rmSync(path);
	await handler("list", ctx);
	check("missing registry lists defaults without creating file", () => { assert.match(last().headline, /built-in defaults/); assert.ok(!existsSync(path)); });
	const seeded = patchRegistry(null, "add", undefined, target);
	saveRegistry(ledger, null, seeded);
	check("first confirmed save seeds defaults without losing them", () => assert.equal(core.loadDelegateTargets(ledger).length, core.DEFAULT_DELEGATE_TARGETS.length + 1));
	assert.equal(readFileSync(task, "utf8"), routing);
	console.log(`${checks} target registry checks passed`);
	function dirnameOfRegistry() { return join(root, ".pi", "extensions", "operator"); }
} finally { rmSync(root, { recursive: true, force: true }); }
