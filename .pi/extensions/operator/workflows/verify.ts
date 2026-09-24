/** Human-confirmed launch only. Verdicts are produced and attached by the separate verifier runner. */
import { existsSync } from "node:fs";
import { join } from "node:path";
import type { ExtensionAPI, ExtensionCommandContext } from "@earendil-works/pi-coding-agent";
import * as core from "../core.ts";
import type { WorkflowHooks } from "./commands.ts";

export function verifyRunArgv(script: string, root: string, bundle: string, user: string, token: string): string[] {
	if (!script.startsWith("/") || !root.startsWith("/") || !/^review-[A-Za-z0-9._-]+$/.test(bundle) ||
		!core.isValidUnixUser(user) || user === "root" || !/^[0-9a-f]{64}$/.test(token)) throw new Error("Invalid verifier launch plan.");
	// Fixed executable/argv. Never execute the bundle's stored shell command.
	return ["-A", "-H", "-u", user, "--", "python3", script, "run", "--root", root, "--bundle", bundle, "--expected", token];
}
export function createVerifyHandler(pi: ExtensionAPI, hooks: Pick<WorkflowHooks, "ledger" | "emit">) {
	return async (args: string, ctx: ExtensionCommandContext): Promise<void> => {
		const emit = (headline: string, lines: string[] = [], invocations: string[] = [], error = false) => hooks.emit(ctx, {
			command: "/op:verify-run", title: "Distinct-UID verifier run", headline, lines, invocations, level: error ? "error" : "info",
		});
		try {
			if (!ctx.hasUI) throw new Error("Verifier runs need a UI and human authorization.");
			const ledger = hooks.ledger(ctx); if (!ledger) return;
			const script = join(ledger.root, "scripts", "operator_verify_run.py");
			if (!existsSync(script)) throw new Error(`Verifier runner unavailable: ${script}`);
			const token = args.trim();
			if (token && !/^review-[A-Za-z0-9._-]+$/.test(token)) throw new Error("Usage: /op:verify-run [review-bundle-id]");
			const choices = core.listSudoPopupTargets(ledger, { all: true }).filter((target) => target.kind === "uid-isolated-review");
			if (!choices.length) throw new Error("No UID-isolated review bundle. Use /op:supervisor-review first.");
			const picked = token || await ctx.ui.select("Choose a claim-scoped UID-isolated review", choices.map((t) => t.id));
			if (!picked) { emit("cancelled; nothing executed"); return; }
			if (!choices.some((t) => t.id === picked)) throw new Error("Review bundle not in the current chooser set.");
			const inspectArgs = [script, "inspect", "--root", ledger.root, "--bundle", picked];
			const inspected = await pi.exec("python3", inspectArgs, { cwd: ledger.root, timeout: 30_000 });
			if (inspected.code !== 0) { emit("preflight refused; no privileged launch", [inspected.stdout, inspected.stderr], [], true); return; }
			const plan = JSON.parse(inspected.stdout);
			if (plan.root !== ledger.root || plan.bundle_id !== picked || !Number.isSafeInteger(plan.verifier_uid) || plan.verifier_uid <= 0 || plan.verifier_uid === plan.author_uid) throw new Error("Invalid or non-isolated preflight result.");
			const askpass = core.resolveSudoAskpass();
			if (!askpass) throw new Error("GUI askpass unavailable; no terminal/password-stdin fallback.");
			const argv = verifyRunArgv(script, ledger.root, picked, plan.review_user, plan.token);
			const invocation = ["sudo", ...argv].map((s) => JSON.stringify(s)).join(" ");
			const preview = [
				`Task: ${plan.task_id}; claim: ${plan.claim_id}`,
				`Author UID: ${plan.author_uid}; verifier: ${plan.review_user} (UID ${plan.verifier_uid})`,
				`Review model: ${plan.provider}/${plan.model}`,
				`Command for independent review: ${plan.verify_cmd}`,
				`Verifier-owned logs: ${plan.verifier_home}/.operator-verifier-runs/`,
				"This launches a model review and may incur usage charges. GUI askpass collects any password; this extension never reads it.",
				"This helper's attachment path requires an approval decision file; exit zero alone is not enough. This is not an enforced boundary against the launched code.",
				"WARNING: the helper, Operator CLI and verification command come from the author-writable checkout and run with the verifier's permissions and credentials. That code can write verifier evidence without this helper's approval path. A different UID does not prove independent review or trustworthy code.",
				"Input hashes only check freshness since confirmation, not code trust. Uses the verifier's HOME/auth; no explicit author-credential forwarding or advisory fallback. Logs may contain review/test output.",
				invocation,
			];
			if (!await ctx.ui.confirm("[experimental] Authorize author-writable code under the verifier account?", preview.join("\n\n"))) {
				emit("declined; nothing executed", preview, [invocation + " (not run)"]); return;
			}
			const previousAskpass = process.env.SUDO_ASKPASS;
			process.env.SUDO_ASKPASS = askpass;
			try {
				const result = await pi.exec("sudo", argv, { cwd: ledger.root, timeout: 720_000 });
				emit(result.code === 0 ? "verifier runner reports attachment completed" : "verifier run did not complete attachment",
					[result.stdout, result.stderr, "Inspect claim/evidence records for authority; this panel is not evidence."], [invocation], result.code !== 0);
			} finally {
				if (previousAskpass === undefined) delete process.env.SUDO_ASKPASS; else process.env.SUDO_ASKPASS = previousAskpass;
			}
		} catch (err) { emit("refused / failed", [String(err)], [], true); }
	};
}
