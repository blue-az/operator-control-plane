import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import * as core from "../.pi/extensions/operator/core.ts";
import { createVerifyHandler, verifyRunArgv } from "../.pi/extensions/operator/workflows/verify.ts";
const root = mkdtempSync(join(tmpdir(), "op-verify-ui-"));
const oldAskpass = process.env.SUDO_ASKPASS;
let checks = 0;
const check = (name: string, fn: () => void) => { fn(); checks++; console.log(`ok ${name}`); };
try {
	mkdirSync(join(root, ".operator", "review_delegations"), { recursive: true });
	mkdirSync(join(root, "scripts"));
	writeFileSync(join(root, "scripts", "operator_verify_run.py"), "# fixture; never executed\n");
	writeFileSync(join(root, "operator"), "");
	const ledger = core.findLedger(root)!;
	const id = "review-claim-0001-fixture";
	writeFileSync(join(ledger.ledgerDir, "review_delegations", `${id}.yaml`), `mode: uid-isolated\nreview_user: verifier\nclaim_id: claim-0001\n`);
	writeFileSync(join(ledger.ledgerDir, "review_delegations", `${id}.sh`), "#!/bin/bash\nsudo -u verifier bash -lc 'cd /tmp && true'\n");
	const askpass = join(root, "askpass"); writeFileSync(askpass, "# never executed\n");
	process.env.SUDO_ASKPASS = askpass;
	let confirm = false, hasUI = true, preflightCode = 0, launchCode = 0;
	let selection: string | undefined = id;
	let calls: { command: string; args: string[] }[] = [];
	const reports: core.Report[] = [];
	const plan = { root, bundle_id: id, task_id: "fixture", claim_id: "claim-0001", review_user: "verifier", author_uid: 1000, verifier_uid: 1001,
		provider: "test", model: "model", verify_cmd: "pytest", verifier_home: "/home/verifier", token: "a".repeat(64) };
	const pi: any = { exec: async (command: string, args: string[]) => {
		calls.push({ command, args });
		return command === "python3" ? { code: preflightCode, stdout: JSON.stringify(plan), stderr: "" } : { code: launchCode, stdout: "runner report", stderr: "" };
	} };
	const ctx: any = { get hasUI() { return hasUI; }, ui: { select: async () => selection, confirm: async () => confirm } };
	const handler = createVerifyHandler(pi, { ledger: () => ledger, emit: (_ctx, report) => reports.push(report) });
	const last = () => reports.at(-1)!;
	const argv = verifyRunArgv("/repo/scripts/operator_verify_run.py", "/repo", id, "verifier", plan.token);
	check("fixed launch preserves HOME isolation and omits authority inputs", () => {
		assert.deepEqual(argv.slice(0, 6), ["-A", "-H", "-u", "verifier", "--", "python3"]);
		for (const forbidden of ["-S", "-E", "bash", "--status", "--verdict", "--verified-by"]) assert.ok(!argv.includes(forbidden));
		assert.throws(() => verifyRunArgv("/script", "/repo", id, "root", plan.token));
		assert.throws(() => verifyRunArgv("/script", "/repo", "../bad", "verifier", plan.token));
	});
	hasUI = false; await handler("", ctx);
	check("no UI means no process", () => assert.equal(calls.length, 0));
	hasUI = true; await handler("--verdict pass", ctx);
	check("raw flags refused", () => assert.equal(calls.length, 0));
	selection = undefined; await handler("", ctx);
	check("cancelled chooser executes nothing", () => assert.equal(calls.length, 0));
	selection = id; preflightCode = 1; await handler(id, ctx);
	check("failed preflight never sudo launches", () => assert.ok(calls.every((call) => call.command !== "sudo")));
	preflightCode = 0; calls = []; await handler(id, ctx);
	check("declined confirmation only inspected", () => { assert.equal(calls.length, 1); assert.equal(calls[0].command, "python3"); assert.match(last().headline, /declined/); });
	confirm = true; calls = []; await handler(id, ctx);
	check("confirmed launch uses fixed sudo runner, not stored shell", () => {
		assert.equal(calls.length, 2); assert.equal(calls[1].command, "sudo"); assert.ok(calls[1].args.includes("--expected"));
		assert.ok(!calls[1].args.some((a) => a.includes("cd /tmp"))); assert.equal(last().level, "info");
		assert.equal(process.env.SUDO_ASKPASS, askpass);
	});
	launchCode = 1; await handler(id, ctx);
	check("failed runner is not reported as verification", () => { assert.equal(last().level, "error"); assert.match(last().headline, /did not complete/); });
	plan.verifier_uid = plan.author_uid; calls = []; await handler(id, ctx);
	check("same UID plan never reaches sudo", () => { assert.equal(calls.length, 1); assert.equal(last().level, "error"); });
	plan.verifier_uid = 1001; process.env.SUDO_ASKPASS = "relative-invalid"; calls = []; await handler(id, ctx);
	check("invalid askpass has no fallback", () => { assert.equal(calls.length, 1); assert.equal(last().level, "error"); });
	console.log(`${checks} verifier UI checks passed`);
} finally {
	if (oldAskpass === undefined) delete process.env.SUDO_ASKPASS; else process.env.SUDO_ASKPASS = oldAskpass;
	rmSync(root, { recursive: true, force: true });
}
