/**
 * Verification path for the Operator pi extension.
 *
 * Run it directly:
 *
 *   node --experimental-strip-types .pi/extensions/operator/selftest.ts
 *
 * or through the repo suite: python3 -m pytest tests/test_pi_operator_extension.py -q
 *
 * Three tiers, each degrading to a SKIP rather than a false pass:
 *
 *   A. core.ts against a throwaway ledger built by the real ./operator, so the
 *      argv builders and output parsers are pinned to actual CLI output.
 *   B. index.ts loaded through pi's own extension loader, asserting the
 *      implemented /op:* commands (step 1 orientation including next-steps
 *      and project, step 2 authoring writes, step 3 supervisor-review, step 4
 *      delegate) register with no load errors and no tools. Skipped when pi
 *      is absent and the optional pi-server import cannot be satisfied.
 *   C. the registered command handlers driven end to end against the throwaway
 *      ledger with a stub UI, asserting the reports and, critically, that
 *      declining a confirmation leaves the ledger untouched -- for /op:use's
 *      current_task, for each of the step 2 authoring writes, for
 *      /op:supervisor-review's review bundle, and for /op:delegate child-task
 *      creation. Skipped when pi's loader internals are not reachable.
 *
 * No LLM call and no network access anywhere in here.
 */

import { spawnSync } from "node:child_process";
import {
	existsSync,
	mkdirSync,
	mkdtempSync,
	readdirSync,
	readFileSync,
	realpathSync,
	rmSync,
	symlinkSync,
	writeFileSync,
} from "node:fs";
import { registerHooks } from "node:module";
import { delimiter, dirname, join, resolve } from "node:path";
import { tmpdir } from "node:os";
import { pathToFileURL } from "node:url";

import * as core from "./core.ts";
import { OperatorClient } from "./client.ts";
import * as orientation from "./orientation/actions.ts";

const REPO_ROOT = resolve(dirname(new URL(import.meta.url).pathname), "../../..");
const OPERATOR = join(REPO_ROOT, "operator");

let passed = 0;
let failed = 0;
const skips: string[] = [];

function check(name: string, condition: unknown, detail = ""): void {
	if (condition) {
		passed += 1;
		console.log(`  ok   ${name}`);
	} else {
		failed += 1;
		console.log(`  FAIL ${name}${detail ? ` -- ${detail}` : ""}`);
	}
}

function eq(name: string, actual: unknown, expected: unknown): void {
	const a = JSON.stringify(actual);
	const e = JSON.stringify(expected);
	check(name, a === e, `got ${a}, want ${e}`);
}

function throws(name: string, fn: () => unknown): void {
	try {
		fn();
		check(name, false, "expected a throw, got a value");
	} catch {
		check(name, true);
	}
}

function throwsKind(name: string, fn: () => unknown, kind: core.LedgerDiscoveryFailureKind): void {
	try {
		fn();
		check(name, false, "expected a throw, got a value");
	} catch (err) {
		const actual = core.isLedgerDiscoveryError(err) ? err.kind : "";
		check(name, actual === kind, `got kind ${JSON.stringify(actual)}, want ${kind}`);
	}
}

function errorText(err: unknown): string {
	if (err instanceof Error) {
		const cause = "cause" in err && err.cause !== undefined ? ` | ${errorText(err.cause)}` : "";
		return `${err.message}${cause}`;
	}
	return String(err);
}

/** Only the optional-package miss, not every error that happens to mention pi-server. */
function isMissingOptionalPiServer(err: unknown): boolean {
	return /Cannot find package '@earendil-works\/pi-server'/.test(errorText(err));
}

type PiImportResult<T> =
	| { status: "ok"; mod: T }
	| { status: "skip"; reason: string }
	| { status: "fail"; reason: string };

const PI_SERVER_SKIP_REASON =
	"optional @earendil-works/pi-server is not installed; pi's loader statically imports the package root which pulls it";

async function importPiModule<T>(primary: string, fallback?: string): Promise<PiImportResult<T>> {
	try {
		return { status: "ok", mod: (await import(primary)) as T };
	} catch (err) {
		if (isMissingOptionalPiServer(err)) {
			return { status: "skip", reason: PI_SERVER_SKIP_REASON };
		}
		const primaryMissing =
			typeof err === "object" &&
			err !== null &&
			"code" in err &&
			(err as { code?: string }).code === "ERR_MODULE_NOT_FOUND" &&
			!isMissingOptionalPiServer(err);
		if (fallback && primaryMissing) {
			try {
				return { status: "ok", mod: (await import(fallback)) as T };
			} catch (err2) {
				if (isMissingOptionalPiServer(err2)) {
					return { status: "skip", reason: PI_SERVER_SKIP_REASON };
				}
				return { status: "fail", reason: `unexpected pi import error (${errorText(err2)})` };
			}
		}
		return { status: "fail", reason: `unexpected pi import error (${errorText(err)})` };
	}
}

/**
 * Isolated temp module so Pi's real loader can import. Installed
 * `@earendil-works/pi-coding-agent@0.85.0` statically imports the package
 * root, which re-exports `main`, which imports optional `@earendil-works/pi-server`.
 * That package is not a declared dependency and is not installed here.
 * The local pi-mono `packages/server` checkout is unbuilt 0.84.3 and does not
 * export the 0.85 names (`ServerError`, `getUnixSocketPath`).
 *
 * This is not a mock of `discoverAndLoadExtensions` / `loadExtensions`.
 * It only satisfies the optional-package static import.
 */
function installIsolatedPiServerImportFixture(): string | null {
	if (typeof registerHooks !== "function") return null;
	const dir = mkdtempSync(join(tmpdir(), "op-ext-pi-server-"));
	process.on("exit", () => rmSync(dir, { recursive: true, force: true }));
	const rootFile = join(dir, "index.js");
	const unixFile = join(dir, "unix.js");
	writeFileSync(
		rootFile,
		[
			'export class ServerError extends Error { constructor(message) { super(message); this.name = "ServerError"; } }',
			'export class SessionAmbiguousError extends Error { constructor(message) { super(message ?? "Session is ambiguous"); this.name = "SessionAmbiguousError"; } }',
			'export class SessionNotFoundError extends Error { constructor(message) { super(message ?? "Session was not found"); this.name = "SessionNotFoundError"; } }',
			"",
		].join("\n"),
	);
	writeFileSync(
		unixFile,
		[
			'export function createUnixServer() { throw new Error("isolated pi-server fixture: createUnixServer is not implemented"); }',
			'export function getUnixSocketPath() { throw new Error("isolated pi-server fixture: getUnixSocketPath is not implemented"); }',
			"",
		].join("\n"),
	);
	const rootUrl = pathToFileURL(rootFile).href;
	const unixUrl = pathToFileURL(unixFile).href;
	registerHooks({
		resolve(specifier, context, nextResolve) {
			if (specifier === "@earendil-works/pi-server") {
				return { shortCircuit: true, url: rootUrl };
			}
			if (specifier === "@earendil-works/pi-server/unix") {
				return { shortCircuit: true, url: unixUrl };
			}
			return nextResolve(specifier, context);
		},
	});
	return dir;
}

function applyImportResult<T>(tier: string, result: PiImportResult<T>): T | null {
	if (result.status === "ok") return result.mod;
	if (result.status === "skip") {
		skips.push(`${tier}: ${result.reason}`);
		console.log(`  skip (${result.reason})`);
		return null;
	}
	failed += 1;
	console.log(`  FAIL ${tier}: ${result.reason}`);
	return null;
}

const integrationCoverage = {
	tierA: false,
	tierB: false,
	tierC: false,
};

function writeLedgerContract(dir: string, payload: unknown): string {
	const contractDir = join(dir, ".pi");
	mkdirSync(contractDir, { recursive: true });
	const path = join(contractDir, "operator-ledger.json");
	writeFileSync(path, `${JSON.stringify(payload, null, 2)}\n`);
	return path;
}

function op(cwd: string, args: string[]) {
	const r = spawnSync(OPERATOR, args, { cwd, encoding: "utf8" });
	return { stdout: r.stdout ?? "", stderr: r.stderr ?? "", code: r.status ?? 1 };
}

// --- fixture -----------------------------------------------------------------

const fixture = mkdtempSync(join(tmpdir(), "op-ext-selftest-"));
process.on("exit", () => rmSync(fixture, { recursive: true, force: true }));

function buildFixture(): core.Ledger {
	op(fixture, ["init"]);
	op(fixture, ["task-create", "--id", "selftest-alpha", "-o", "Alpha objective", "-a", "claude", "--review", "codex"]);
	op(fixture, ["task-create", "--id", "selftest-beta", "-o", "Beta objective", "-a", "pi"]);
	// findLedger wants .operator/ and an executable 'operator' in the same
	// directory, which is what a real checkout looks like. Give the fixture a
	// symlink so the handlers resolve it the same way they would in the repo.
	symlinkSync(OPERATOR, join(fixture, core.OPERATOR_BIN));
	const ledger = core.findLedger(fixture);
	if (!ledger) throw new Error(`fixture ledger not discoverable at ${fixture}`);
	return ledger;
}

// --- tier A: core.ts ---------------------------------------------------------

function tierA(ledger: core.Ledger): void {
	console.log("\nTier A: core.ts against a real throwaway ledger");

	// argv allowlist
	eq("doctorArgv", core.doctorArgv(), ["doctor"]);
	eq("taskShowArgv passes --id explicitly", core.taskShowArgv("selftest-alpha"), ["task-show", "--id", "selftest-alpha"]);
	eq("claimListArgv passes --task explicitly", core.claimListArgv("selftest-alpha"), ["claim-list", "--task", "selftest-alpha"]);
	eq("claimShowArgv passes --id explicitly", core.claimShowArgv("claim-0001"), ["claim-show", "--id", "claim-0001"]);
	throws("claimShowArgv rejects a malformed claim id", () => core.claimShowArgv("claim-x"));
	eq("sessionListArgv passes --task explicitly", core.sessionListArgv("selftest-alpha"), [
		"session-list",
		"--task",
		"selftest-alpha",
	]);
	eq("taskListArgv default", core.taskListArgv(), ["task-list"]);
	eq("taskListArgv with filter", core.taskListArgv({ all: true, filter: "selftest" }), [
		"task-list",
		"--all",
		"--filter",
		"selftest",
	]);
	eq("taskUseArgv", core.taskUseArgv("selftest-beta"), ["task-use", "selftest-beta"]);

	// fail-closed guards
	throws("rejects a subcommand outside the allowlist", () => core.assertSafeArgv(["task-transition", "--to", "verified"]));
	throws("rejects verify", () => core.assertSafeArgv(["verify"]));
	eq("sessionStartArgv names --task and --harness", core.sessionStartArgv("selftest-alpha", "claude"), [
		"session-start",
		"--task",
		"selftest-alpha",
		"--harness",
		"claude",
	]);
	eq("sessionEndArgv names usage, outcome, and cost", core.sessionEndArgv("usage-0001", "useful", 0), [
		"session-end",
		"usage-0001",
		"--outcome",
		"useful",
		"--cost",
		"0",
	]);
	throws("sessionEndArgv rejects a malformed usage id", () => core.sessionEndArgv("usage-x", "useful", 0));
	throws("sessionEndArgv rejects a negative cost", () => core.sessionEndArgv("usage-0001", "useful", -1));
	throws("sessionEndArgv rejects an unknown outcome", () => core.sessionEndArgv("usage-0001", "verified", 0));
	throws("rejects session-end --status (lifecycle authority)", () =>
		core.assertSafeArgv(["session-end", "usage-0001", "--outcome", "useful", "--cost", "0", "--status", "verified"]),
	);
	throws("rejects session-end --force", () =>
		core.assertSafeArgv(["session-end", "usage-0001", "--outcome", "useful", "--cost", "0", "--force"]),
	);
	throws("rejects session-start --force (not in the flag allowlist)", () =>
		core.assertSafeArgv(["session-start", "--task", "selftest-alpha", "--harness", "claude", "--force"]),
	);
	throws("rejects a review-delegate flag outside the allowlist", () =>
		core.assertSafeArgv(["review-delegate", "claim-0001", "--model", "x"]),
	);
	throws("rejects --status", () => core.assertSafeArgv(["evidence-attach", "--status", "verified"]));
	throws("rejects --verified-by", () => core.assertSafeArgv(["evidence-attach", "--verified-by", "someone"]));
	throws("rejects --verdict", () => core.assertSafeArgv(["evidence-attach", "--verdict", "looks fine"]));
	throws("rejects --status=value", () => core.assertSafeArgv(["evidence-attach", "--status=verified"]));
	throws("rejects --verdict=value", () => core.assertSafeArgv(["evidence-attach", "--verdict=fine"]));
	// -v is evidence-attach's short alias for --verdict; short flags are refused wholesale.
	throws("rejects the -v short alias for --verdict", () => core.assertSafeArgv(["evidence-attach", "-v", "fine"]));
	throws("rejects a flag the subcommand does not allow", () => core.assertSafeArgv(["claim-add", "--diff-base", "HEAD"]));
	throws("rejects a flag-shaped task id", () => core.taskShowArgv("--help"));
	throws("rejects a task id with a space", () => core.taskShowArgv("a b"));
	throws("rejects a task id with a shell metacharacter", () => core.taskShowArgv("a;rm -rf /"));
	throws("rejects a flag-shaped filter", () => core.taskListArgv({ filter: "--all" }));
	throws("rejects empty argv", () => core.assertSafeArgv([]));
	check("doctor is read-only", core.isReadOnly(core.doctorArgv()));
	check("task-use is not read-only", !core.isReadOnly(core.taskUseArgv("selftest-alpha")));
	check(
		"every allowlisted subcommand is either read-only or a confirmed write",
		[...core.READ_ONLY_SUBCOMMANDS, ...core.CONFIRMED_WRITE_SUBCOMMANDS].every((sub) => sub in core.ALLOWED_FLAGS),
	);
	check(
		"no subcommand's flag allowlist contains a lifecycle flag",
		Object.values(core.ALLOWED_FLAGS).every((flags) => !flags.some((f) => (core.FORBIDDEN_FLAGS as readonly string[]).includes(f))),
	);

	// ledger discovery: walk up from a nested directory of the fixture. The
	// repo's own .operator/ is gitignored runtime state (absent in CI), so
	// relying on the real checkout here would pass locally and fail on any
	// fresh clone.
	const nested = join(fixture, "deep", "nested", "dir");
	mkdirSync(nested, { recursive: true });
	const found = core.findLedger(nested);
	check("findLedger walks up to the fixture root", found?.root === fixture, `got ${found?.root}`);
	check("findLedger fails closed above any ledger", core.findLedger("/") === null);

	// task record existence
	check("taskRecordExists finds a real task", core.taskRecordExists(ledger, "selftest-alpha"));
	check("taskRecordExists rejects a typo", !core.taskRecordExists(ledger, "selftest-alfa"));
	check("taskRecordExists rejects a traversal", !core.taskRecordExists(ledger, "../../etc/passwd"));

	// current_task read
	eq("current_task is null on a fresh ledger", core.readLedgerCurrentTask(ledger), null);
	op(fixture, ["task-use", "selftest-alpha"]);
	eq("current_task reads back after task-use", core.readLedgerCurrentTask(ledger), "selftest-alpha");

	// parsers against real output
	const listOut = op(fixture, core.taskListArgv()).stdout;
	const rows = core.parseTaskList(listOut);
	eq("parseTaskList row count", rows.length, 2);
	eq(
		"parseTaskList ids",
		rows.map((r) => r.id).sort(),
		["selftest-alpha", "selftest-beta"],
	);
	const alpha = rows.find((r) => r.id === "selftest-alpha");
	eq("parseTaskList status", alpha?.status, "assigned");
	eq("parseTaskList assigned harness", alpha?.assigned, "claude");
	eq("parseTaskList reviewer", alpha?.reviewer, "codex");
	check("parseTaskList drops the header row", !rows.some((r) => r.id === "TASK ID"));

	const showOut = op(fixture, core.taskShowArgv("selftest-alpha")).stdout;
	const show = core.parseTaskShow(showOut);
	eq("parseTaskShow task id", show.fields["Task ID"], "selftest-alpha");
	eq("parseTaskShow objective", show.fields.Objective, "Alpha objective");
	eq("parseTaskShow status", show.fields.Status, "assigned");
	eq("parseTaskShow assigned harness", show.fields["Assigned Harness"], "claude");
	eq("parseTaskShow review harness", show.fields["Review Harness"], "codex");
	eq("parseTaskShow counts no claims", show.claims, 0);
	eq("parseTaskShow counts no evidence", show.evidence, 0);
	eq("parseTaskShow counts no handoffs", show.handoffs, 0);

	eq("parseClaimList is empty for a new task", core.parseClaimList(op(fixture, core.claimListArgv("selftest-alpha")).stdout), []);
	eq("countSessionRows is 0 before any session", core.countSessionRows(op(fixture, core.sessionListArgv("selftest-alpha")).stdout), 0);
	op(fixture, ["session-start", "--task", "selftest-alpha", "--harness", "claude"]);
	eq("countSessionRows is 1 after session-start", core.countSessionRows(op(fixture, core.sessionListArgv("selftest-alpha")).stdout), 1);

	// doctor summary on a clean ledger and on this repo's real ledger
	const clean = core.summarizeDoctor(op(fixture, core.doctorArgv()));
	check("summarizeDoctor reports PASS on a clean ledger", clean.ok, clean.headline);
	eq("summarizeDoctor finds no errors on a clean ledger", clean.errors.length, 0);
	check("buildDoctorReport headline matches", core.buildDoctorReport(clean).headline === clean.headline);
	eq("buildDoctorReport records the invocation", core.buildDoctorReport(clean).invocations, ["./operator doctor"]);

	// severity parsing does not depend on this repo's ledger being dirty
	const synthetic = core.summarizeDoctor({
		stdout: "[Info] a\n[Warning] b\n[Error] c\nTotal consistency issues found: 3\n",
		stderr: "",
		code: 1,
	});
	eq("summarizeDoctor counts errors", synthetic.errors, ["c"]);
	eq("summarizeDoctor counts warnings", synthetic.warnings, ["b"]);
	eq("summarizeDoctor counts infos", synthetic.infos, ["a"]);
	eq("summarizeDoctor reads the total", synthetic.total, 3);
	check("summarizeDoctor fails on a non-zero exit", !synthetic.ok);
	eq("buildDoctorReport level on failure", core.buildDoctorReport(synthetic).level, "error");
	check(
		"buildDoctorReport flags doctor's total disagreeing with its printed lines",
		core.buildDoctorReport(synthetic).lines.some((l) => l.includes("both are reported as-is")),
	);

	// status report shape
	const status = core.buildStatusReport({
		ledgerRoot: fixture,
		sessionTask: "selftest-beta",
		ledgerCurrentTask: "selftest-alpha",
		activeTask: "selftest-beta",
		activeOrigin: "session",
		taskShow: show,
		claims: [],
		sessionCount: 0,
		doctor: clean,
		taskCount: 2,
		invocations: ["./operator task-show --id selftest-beta"],
		notes: [],
	});
	check(
		"status shows the session selection and ledger current_task separately",
		status.lines.some((l) => l.includes("Session selection: selftest-beta")) &&
			status.lines.some((l) => l.includes("Ledger current_task: selftest-alpha")),
	);
	check("status names where the shown task came from", status.lines.some((l) => l.includes("pi session selection")));
	check("status states that nothing was written", status.lines.some((l) => l.includes("No authority record was written")));
	integrationCoverage.tierA = true;
}

function validContract(ledgerRoot: string): Record<string, unknown> {
	return {
		schema: core.LEDGER_CONTRACT_SCHEMA,
		ledger_root: ledgerRoot,
		wired_into_findLedger: true,
		runtime_ledger_copied: false,
	};
}

/**
 * External-ledger contract wiring. Consumers are throwaway dirs that do not
 * sit inside the fixture, so walking up does not find the sibling pair.
 */
function tierAContract(external: core.Ledger): void {
	console.log("\nTier A-contract: findLedger reads .pi/operator-ledger.json");
	const consumers = mkdtempSync(join(tmpdir(), "op-ext-contract-"));
	process.on("exit", () => rmSync(consumers, { recursive: true, force: true }));
	const consumerA = join(consumers, "consumer-a");
	const consumerB = join(consumers, "consumer-b");
	mkdirSync(consumerA);
	mkdirSync(consumerB);
	writeLedgerContract(consumerA, validContract(external.root));
	writeLedgerContract(consumerB, validContract(external.root));

	const foundA = core.findLedger(consumerA);
	const foundB = core.findLedger(consumerB);
	eq("consumer A resolves the external ledger_root", foundA?.root, external.root);
	eq("consumer B resolves the same external ledger_root", foundB?.root, external.root);
	check("consumer A has no copied .operator/", !existsSync(join(consumerA, core.LEDGER_DIR)));
	check("consumer B has no copied .operator/", !existsSync(join(consumerB, core.LEDGER_DIR)));

	const nested = join(consumerA, "src", "nested");
	mkdirSync(nested, { recursive: true });
	eq("findLedger walks up to the consumer contract", core.findLedger(nested)?.root, external.root);

	const relative = join(consumers, "relative");
	mkdirSync(relative);
	writeLedgerContract(relative, { ...validContract(external.root), ledger_root: "relative/path" });
	throwsKind("relative ledger_root is malformed", () => core.findLedger(relative), "malformed");

	const badJson = join(consumers, "bad-json");
	mkdirSync(badJson);
	mkdirSync(join(badJson, ".pi"), { recursive: true });
	writeFileSync(join(badJson, ".pi", "operator-ledger.json"), "{not json");
	throwsKind("invalid JSON is malformed", () => core.findLedger(badJson), "malformed");

	const wrongSchema = join(consumers, "wrong-schema");
	mkdirSync(wrongSchema);
	writeLedgerContract(wrongSchema, { ...validContract(external.root), schema: "nope/v0" });
	throwsKind("wrong schema is malformed", () => core.findLedger(wrongSchema), "malformed");

	const missingRoot = join(consumers, "missing-root");
	mkdirSync(missingRoot);
	writeLedgerContract(missingRoot, { schema: core.LEDGER_CONTRACT_SCHEMA });
	throwsKind("missing ledger_root is malformed", () => core.findLedger(missingRoot), "malformed");

	const missingPair = join(consumers, "missing-pair");
	mkdirSync(missingPair);
	const emptyRoot = join(consumers, "empty-root");
	mkdirSync(emptyRoot);
	writeLedgerContract(missingPair, validContract(emptyRoot));
	throwsKind("absolute ledger_root without the sibling pair is missing-pair", () => core.findLedger(missingPair), "missing-pair");

	const traversal = join(consumers, "traversal");
	mkdirSync(traversal);
	writeLedgerContract(traversal, {
		...validContract(external.root),
		// Concatenate so the stored string still contains '..'. path.join()
		// would normalize it away before the contract is written.
		ledger_root: `${external.root}/../nope`,
	});
	throwsKind("ledger_root with '..' segments is malformed", () => core.findLedger(traversal), "malformed");

	const ambiguous = join(consumers, "ambiguous");
	mkdirSync(ambiguous);
	mkdirSync(join(ambiguous, core.LEDGER_DIR));
	symlinkSync(OPERATOR, join(ambiguous, core.OPERATOR_BIN));
	const other = join(consumers, "other-plane");
	mkdirSync(other);
	mkdirSync(join(other, core.LEDGER_DIR));
	symlinkSync(OPERATOR, join(other, core.OPERATOR_BIN));
	writeLedgerContract(ambiguous, validContract(other));
	throwsKind("sibling pair plus a different contract root is ambiguous", () => core.findLedger(ambiguous), "ambiguous");

	const matching = join(consumers, "matching");
	mkdirSync(matching);
	mkdirSync(join(matching, core.LEDGER_DIR));
	symlinkSync(OPERATOR, join(matching, core.OPERATOR_BIN));
	writeLedgerContract(matching, validContract(matching));
	eq("matching sibling pair and contract is not ambiguous", core.findLedger(matching)?.root, realpathSync(matching));

	const isolated = join(consumers, "env-isolated");
	mkdirSync(isolated);
	const previousDir = process.env.OPERATOR_DIR;
	const previousRoot = process.env.OPERATOR_LEDGER_ROOT;
	process.env.OPERATOR_DIR = external.root;
	process.env.OPERATOR_LEDGER_ROOT = external.root;
	try {
		eq("findLedger ignores OPERATOR_DIR / OPERATOR_LEDGER_ROOT", core.findLedger(isolated), null);
	} finally {
		if (previousDir === undefined) delete process.env.OPERATOR_DIR;
		else process.env.OPERATOR_DIR = previousDir;
		if (previousRoot === undefined) delete process.env.OPERATOR_LEDGER_ROOT;
		else process.env.OPERATOR_LEDGER_ROOT = previousRoot;
	}
}

// --- tier A2: the step 2 authoring writes ------------------------------------
// Same contract as tier A: everything is pinned to what the real CLI accepts
// and prints, not to a mock.

function tierA2(ledger: core.Ledger): void {
	console.log("\nTier A2: step 2 authoring writes against the same ledger");

	// --by derivation is session-scoped provenance and nothing else.
	eq("deriveAuthorLabel matches the ledger's <carrier>-<short id> convention", core.deriveAuthorLabel("01a05bf2-9c1e-7a2b-8000-0123456789ab"), "pi-01a05bf2");
	eq("deriveAuthorLabel strips separators", core.deriveAuthorLabel("01-a0-5b-f2-99"), "pi-01a05bf2");
	eq("deriveAuthorLabel fails closed on an empty session id", core.deriveAuthorLabel(""), null);
	eq("deriveAuthorLabel fails closed on a too-short session id", core.deriveAuthorLabel("ab-"), null);
	eq("deriveAuthorLabel honors a non-pi carrier", core.deriveAuthorLabel("e5502c31-aaaa", "claude"), "claude-e5502c31");

	const by = core.deriveAuthorLabel("01a05bf2-9c1e-7a2b-8000-0123456789ab")!;

	// claim-add argv
	const claimArgv = core.claimAddArgv({
		taskId: "selftest-alpha",
		type: "test_passes",
		text: "The selftest passes",
		by,
		gate: ".pi/extensions/operator/selftest.ts",
		verifyCmd: "node --experimental-strip-types .pi/extensions/operator/selftest.ts",
	});
	eq("claimAddArgv names its task explicitly", claimArgv.slice(0, 5), ["claim-add", "--task", "selftest-alpha", "--type", "test_passes"]);
	check("claimAddArgv passes free text inline", claimArgv.includes("--text=The selftest passes"));
	check("claimAddArgv passes the session-derived --by", claimArgv.includes(`--by=${by}`));
	check("claimAddArgv carries the verify command", claimArgv.some((a) => a.startsWith("--verify-cmd=node ")));
	check("claimAddArgv emits no lifecycle flag", claimArgv.every((a) => !/^--(status|verified-by|verdict)/.test(a)));

	// Text that looks like a lifecycle flag stays text, because it is inline.
	const sneaky = core.claimAddArgv({ taskId: "selftest-alpha", type: "file_exists", text: "--status=verified", by });
	check("a claim text that looks like --status is carried inline as text", sneaky.includes("--text=--status=verified"));
	check("...and no bare --status token is produced", !sneaky.includes("--status=verified"));

	throws("claimAddArgv rejects an unknown claim type", () => core.claimAddArgv({ taskId: "selftest-alpha", type: "vibes", text: "x", by }));
	throws("claimAddArgv rejects empty text", () => core.claimAddArgv({ taskId: "selftest-alpha", type: "file_exists", text: "   ", by }));
	throws("claimAddArgv rejects a missing --by", () => core.claimAddArgv({ taskId: "selftest-alpha", type: "file_exists", text: "x", by: "" }));
	throws("claimAddArgv rejects a flag-shaped --by", () => core.claimAddArgv({ taskId: "selftest-alpha", type: "file_exists", text: "x", by: "--verified-by" }));
	throws("claimAddArgv rejects a bad task id", () => core.claimAddArgv({ taskId: "../etc", type: "file_exists", text: "x", by }));
	throws("supervision_credit without --layer is refused (FR-12)", () =>
		core.claimAddArgv({ taskId: "selftest-alpha", type: "supervision_credit", text: "x", by }),
	);
	check(
		"supervision_credit with --layer is accepted",
		core.claimAddArgv({ taskId: "selftest-alpha", type: "supervision_credit", text: "x", by, layer: "evidence" }).includes("evidence"),
	);
	throws("an unknown supervision layer is refused", () =>
		core.claimAddArgv({ taskId: "selftest-alpha", type: "supervision_credit", text: "x", by, layer: "vibes" }),
	);

	// Run it for real, and pin the id parser to actual output.
	const claimRun = op(fixture, claimArgv);
	eq("claim-add exits 0 with the built argv", claimRun.code, 0);
	const claimId = core.parseRecordId(claimRun.stdout, "claim");
	check("parseRecordId reads the claim id from real output", /^claim-[0-9]+$/.test(claimId ?? ""), claimRun.stdout + claimRun.stderr);
	const claimRows = core.parseClaimList(op(fixture, core.claimListArgv("selftest-alpha")).stdout);
	eq("the claim shows up in claim-list", claimRows.length, 1);
	eq("the claim is recorded unverified", claimRows[0]?.status, "UNVERIFIED");
	const claimYaml = readFileSync(join(ledger.ledgerDir, "claims", `${claimId}.yaml`), "utf8");
	check("the record carries the session-derived made_by", claimYaml.includes(`made_by: ${by}`), claimYaml);
	check("the record has no verified_by", /verified_by:\s*(null|~)?\s*$/m.test(claimYaml), claimYaml);
	check("the record kept the free text intact", claimYaml.includes("The selftest passes"));

	// evidence-attach argv
	const artifact = join(fixture, "run.log");
	writeFileSync(artifact, "doctor PASS\n");
	const resolved = core.resolveEvidenceLocator(ledger, "run.log");
	eq("resolveEvidenceLocator resolves a relative path against the ledger root", resolved.locator, artifact);
	eq("resolveEvidenceLocator marks a local file as not remote", resolved.remote, false);
	eq("resolveEvidenceLocator recognizes an http(s) URL", core.resolveEvidenceLocator(ledger, "https://example.invalid/x"), {
		locator: "https://example.invalid/x",
		remote: true,
	});
	throws("resolveEvidenceLocator refuses a nonexistent local path", () => core.resolveEvidenceLocator(ledger, "no-such-file.log"));
	throws("resolveEvidenceLocator refuses a directory", () => core.resolveEvidenceLocator(ledger, "."));
	throws("resolveEvidenceLocator refuses a flag-shaped locator", () => core.resolveEvidenceLocator(ledger, "--status"));

	const evidenceArgv = core.evidenceAttachArgv({
		taskId: "selftest-alpha",
		locator: artifact,
		type: "run_log",
		by,
		claimId: claimId!,
		verifyCmd: "./operator doctor",
		notes: "clean run",
	});
	eq("evidenceAttachArgv puts the locator first", evidenceArgv.slice(0, 2), ["evidence-attach", artifact]);
	check("evidenceAttachArgv names its task explicitly", evidenceArgv.includes("--task") && evidenceArgv.includes("selftest-alpha"));
	check("evidenceAttachArgv binds the claim", evidenceArgv.includes("--claim") && evidenceArgv.includes(claimId!));
	check("evidenceAttachArgv carries a rerunnable verify command", evidenceArgv.includes("--verify-cmd=./operator doctor"));
	check(
		"evidenceAttachArgv emits no lifecycle flag",
		evidenceArgv.every((a) => !/^--(status|verified-by|verdict)/.test(a)),
	);
	check(
		"the evidence flag allowlist has no lifecycle flag in it at all",
		!core.ALLOWED_FLAGS["evidence-attach"].some((f) => ["--status", "--verified-by", "--verdict"].includes(f)),
	);
	eq("diff is not an offered evidence type at step 2", (core.EVIDENCE_TYPES as readonly string[]).includes("diff"), false);
	throws("evidenceAttachArgv rejects an unknown evidence type", () =>
		core.evidenceAttachArgv({ taskId: "selftest-alpha", locator: artifact, type: "diff", by, verifyCmd: "./operator doctor" }),
	);
	throws("evidenceAttachArgv refuses a missing verify-cmd", () =>
		core.evidenceAttachArgv({ taskId: "selftest-alpha", locator: artifact, type: "run_log", by, verifyCmd: "" }),
	);
	throws("evidenceAttachArgv refuses a whitespace-only verify-cmd", () =>
		core.evidenceAttachArgv({ taskId: "selftest-alpha", locator: artifact, type: "run_log", by, verifyCmd: "   " }),
	);
	throws("evidenceAttachArgv rejects a malformed claim id", () =>
		core.evidenceAttachArgv({
			taskId: "selftest-alpha",
			locator: artifact,
			type: "run_log",
			by,
			claimId: "claim-x",
			verifyCmd: "./operator doctor",
		}),
	);
	throws("evidenceAttachArgv rejects a non-sha256 --hash", () =>
		core.evidenceAttachArgv({
			taskId: "selftest-alpha",
			locator: artifact,
			type: "run_log",
			by,
			hash: "deadbeef",
			verifyCmd: "./operator doctor",
		}),
	);
	check(
		"evidenceAttachArgv accepts a real sha256",
		core
			.evidenceAttachArgv({
				taskId: "selftest-alpha",
				locator: "https://example.invalid/x",
				type: "run_log",
				by,
				hash: "A".repeat(64),
				verifyCmd: "./operator doctor",
			})
			.includes("a".repeat(64)),
	);
	throws("handoff-add refuses --file (no stdin/file passthrough)", () =>
		core.assertSafeArgv(["handoff-add", "--task", "selftest-alpha", "--file", "-"]),
	);

	const evidenceRun = op(fixture, evidenceArgv);
	eq("evidence-attach exits 0 with the built argv", evidenceRun.code, 0);
	const evidenceId = core.parseRecordId(evidenceRun.stdout, "evidence");
	check("parseRecordId reads the evidence id from real output", /^evidence-[0-9]+$/.test(evidenceId ?? ""), evidenceRun.stdout + evidenceRun.stderr);
	const evidenceYaml = readFileSync(join(ledger.ledgerDir, "evidence", "selftest-alpha", `${evidenceId}.yaml`), "utf8");
	check("the evidence record carries the session-derived produced_by", evidenceYaml.includes(`produced_by: ${by}`), evidenceYaml);
	check("the evidence record carries the verification command", evidenceYaml.includes("verification_command: ./operator doctor"), evidenceYaml);
	const claimAfter = readFileSync(join(ledger.ledgerDir, "claims", `${claimId}.yaml`), "utf8");
	check("attaching evidence did not verify the claim", /verification_status:\s*false/.test(claimAfter), claimAfter);
	check("attaching evidence did not set verified_by", !/verified_by:\s*\S+/.test(claimAfter.replace(/verified_by:\s*null/, "")), claimAfter);

	// handoff template and draft parsing
	const template = core.buildHandoffTemplate("selftest-alpha", by);
	check("the handoff template names the task", template.includes("selftest-alpha"));
	check("the handoff template names the --by label", template.includes(`--by=${by}`));
	check("the handoff template says continuity transfer is a mode of handoff", template.includes("Continuity transfer is a mode of handoff"));
	for (const section of core.HANDOFF_SECTIONS) {
		check(`the handoff template offers '${section.heading}'`, template.includes(`## ${section.heading}`));
	}
	const generated = core.buildGeneratedHandoffDraft("selftest-alpha", by);
	eq("an untouched generated template parses to the generated draft", core.parseHandoffDraft(template), generated);
	throws("an empty handoff is refused before spawning", () => core.handoffAddArgv({ taskId: "selftest-alpha", by, draft: {} }));

	const filled = core.buildHandoffTemplate("selftest-alpha", by, {
		"--changed": "Added the step 2 commands.",
		"--next-action": "Ask a distinct identity to verify.",
	});
	const draft = core.parseHandoffDraft(filled);
	eq("parseHandoffDraft reads the edited sections", draft, {
		"--changed": "Added the step 2 commands.",
		"--next-action": "Ask a distinct identity to verify.",
	});
	eq("parseHandoffDraft drops '#' comment lines", core.parseHandoffDraft("# a comment\n## What changed\n# dropped\nkept\n"), {
		"--changed": "kept",
	});
	eq("parseHandoffDraft ignores an unknown heading", core.parseHandoffDraft("## Something Else\ntext\n"), {});

	const handoffArgv = core.handoffAddArgv({ taskId: "selftest-alpha", by, draft });
	eq("handoffAddArgv names its task explicitly", handoffArgv.slice(0, 3), ["handoff-add", "--task", "selftest-alpha"]);
	check("handoffAddArgv passes the session-derived --by", handoffArgv.includes(`--by=${by}`));
	check("handoffAddArgv passes only the filled sections", handoffArgv.filter((a) => a.startsWith("--changed=") || a.startsWith("--next-action=")).length === 2);
	check("handoffAddArgv omits the empty sections", !handoffArgv.some((a) => a.startsWith("--open=") || a.startsWith("--verified=")));
	check("handoffAddArgv emits no lifecycle flag", handoffArgv.every((a) => !/^--(status|verified-by|verdict)/.test(a)));
	// handoff-add's --verified is prose ("what was verified"), not a verifier name.
	check(
		"handoff --verified is a prose field and is allowed",
		core.handoffAddArgv({ taskId: "selftest-alpha", by, draft: { "--verified": "the suite ran green" } }).includes("--verified=the suite ran green"),
	);

	const handoffRun = op(fixture, handoffArgv);
	eq("handoff-add exits 0 with the built argv", handoffRun.code, 0);
	const handoffId = core.parseRecordId(handoffRun.stdout, "handoff");
	check("parseRecordId reads the handoff id from real output", /^handoff-[0-9]+$/.test(handoffId ?? ""), handoffRun.stdout + handoffRun.stderr);
	const handoffYaml = readFileSync(join(ledger.ledgerDir, "handoffs", "selftest-alpha", `${handoffId}.yaml`), "utf8");
	check("the handoff record carries the session-derived by", handoffYaml.includes(`by: ${by}`), handoffYaml);
	check("the handoff record carries the edited prose", handoffYaml.includes("Added the step 2 commands."), handoffYaml);

	// The ledger still passes its own consistency check after three writes,
	// with the claim unverified rather than self-verified.
	const after = core.summarizeDoctor(op(fixture, core.doctorArgv()));
	check("doctor still passes after the step 2 writes", after.ok, after.headline);
	check(
		"doctor did not treat the new claim as verified",
		!after.errors.some((e) => e.includes(claimId ?? "") && /\bverified\b/.test(e)),
		after.errors.join(" | ") || after.headline,
	);

	// Report shaping: the boundary sentences are not optional.
	const written = core.buildWriteReport({
		command: "/op:claim",
		title: "Operator claim",
		noun: "claim",
		taskId: "selftest-alpha",
		by,
		argv: claimArgv,
		result: { stdout: claimRun.stdout, stderr: "", code: 0 },
		recordId: claimId,
		detail: [],
	});
	eq("a successful write reports at info level", written.level, "info");
	check("a successful write names the record", written.headline.startsWith(`${claimId} on selftest-alpha`), written.headline);
	check(
		"every write report says --by confers no authority",
		written.lines.some((l) => l.includes("not a verifier identity")),
	);
	check(
		"every write report says nothing was verified",
		written.lines.some((l) => l.includes("Nothing here verifies anything")),
	);
	const failedWrite = core.buildWriteReport({
		command: "/op:evidence",
		title: "Operator evidence",
		noun: "evidence",
		taskId: "selftest-alpha",
		by,
		argv: evidenceArgv,
		result: { stdout: "", stderr: "Error: Local evidence file does not exist: x", code: 1 },
		recordId: null,
		detail: [],
	});
	eq("a failed write reports at error level", failedWrite.level, "error");
	check("a failed write surfaces operator's own stderr", failedWrite.lines.some((l) => l.includes("does not exist")));
	const declined = core.buildDeclinedReport("/op:claim", "Operator claim", "Declined at the confirmation dialog.", claimArgv);
	eq("a declined write is a warning, not a silence", declined.level, "warning");
	check("a declined write marks the invocation as not run", declined.invocations[0].endsWith("(not run)"), declined.invocations[0]);
	check("a declined write says the ledger was untouched", declined.lines.some((l) => l.includes("was not touched")));
}

// --- tier A3: step 3 supervisor-review / review-delegate ---------------------

function tierA3(ledger: core.Ledger): void {
	console.log("\nTier A3: step 3 supervisor-review against the same ledger");

	const by = core.deriveAuthorLabel("01a05bf2-9c1e-7a2b-8000-0123456789ab")!;
	const claimArgv = core.claimAddArgv({
		taskId: "selftest-alpha",
		type: "file_exists",
		text: "Step 3 review-delegate wrap exists",
		by,
		gate: ".pi/extensions/operator/core.ts",
		verifyCmd: "./operator doctor",
	});
	const claimRun = op(fixture, claimArgv);
	eq("A3 claim-add exits 0", claimRun.code, 0);
	const claimId = core.parseRecordId(claimRun.stdout, "claim");
	check("A3 minted a claim id", /^claim-[0-9]+$/.test(claimId ?? ""), claimRun.stdout + claimRun.stderr);
	if (!claimId) return;

	const shown = core.parseClaimShow(op(fixture, core.claimShowArgv(claimId)).stdout);
	eq("parseClaimShow reads the claim id", shown.claimId, claimId);
	eq("parseClaimShow reads the task id", shown.taskId, "selftest-alpha");
	eq("parseClaimShow reads the recorded verify command", shown.verifyCmd, "./operator doctor");
	eq("parseClaimShow reads made_by", shown.madeBy, by);
	check("parseClaimShow reads the author uid", shown.authorUid === 1000 || typeof shown.authorUid === "number");

	const noVerify = op(fixture, [
		"claim-add",
		"--task",
		"selftest-alpha",
		"--type",
		"file_exists",
		"--text",
		"no verify command recorded",
		"--by",
		by,
		"--gate",
		".pi/extensions/operator/core.ts",
	]);
	eq("a claim without verify-cmd can still be recorded by the CLI", noVerify.code, 0);
	const noVerifyId = core.parseRecordId(noVerify.stdout, "claim");
	const shownBare = core.parseClaimShow(op(fixture, core.claimShowArgv(noVerifyId!)).stdout);
	eq("parseClaimShow treats a missing verify command as null", shownBare.verifyCmd, null);

	eq("listHarnessIds includes init defaults", core.listHarnessIds(ledger).includes("codex"), true);
	check("harnessRecordExists finds codex", core.harnessRecordExists(ledger, "codex"));
	check("harnessRecordExists rejects a typo", !core.harnessRecordExists(ledger, "codez"));
	check("claimRecordExists finds the new claim", core.claimRecordExists(ledger, claimId));
	check("isValidClaimId accepts claim-0001", core.isValidClaimId("claim-0001"));
	check("isValidClaimId rejects claim-x", !core.isValidClaimId("claim-x"));

	const advisoryArgv = core.reviewDelegateArgv({
		claimId,
		taskId: "selftest-alpha",
		reviewer: "codex",
		mode: "advisory-agent",
		verifyCmd: "./operator doctor",
	});
	eq("reviewDelegateArgv starts with the subcommand and claim", advisoryArgv.slice(0, 2), ["review-delegate", claimId]);
	check("reviewDelegateArgv names --task explicitly", advisoryArgv.includes("--task") && advisoryArgv.includes("selftest-alpha"));
	check("reviewDelegateArgv names --reviewer explicitly", advisoryArgv.includes("--reviewer") && advisoryArgv.includes("codex"));
	check("reviewDelegateArgv names --mode", advisoryArgv.includes("--mode") && advisoryArgv.includes("advisory-agent"));
	check("reviewDelegateArgv carries --verify-cmd inline", advisoryArgv.includes("--verify-cmd=./operator doctor"));
	check("advisory argv has no --review-user", !advisoryArgv.includes("--review-user"));
	check(
		"reviewDelegateArgv emits no lifecycle flag",
		advisoryArgv.every((a) => !/^--(status|verified-by|verdict)/.test(a)),
	);
	check(
		"the review-delegate flag allowlist has no lifecycle flag",
		!core.ALLOWED_FLAGS["review-delegate"].some((f) => ["--status", "--verified-by", "--verdict"].includes(f)),
	);
	check("review-delegate is not read-only", !core.isReadOnly(advisoryArgv));

	throws("reviewDelegateArgv refuses a missing reviewer", () =>
		core.reviewDelegateArgv({ claimId, taskId: "selftest-alpha", reviewer: "", mode: "advisory-agent", verifyCmd: "./operator doctor" }),
	);
	throws("reviewDelegateArgv refuses a flag-shaped reviewer", () =>
		core.reviewDelegateArgv({
			claimId,
			taskId: "selftest-alpha",
			reviewer: "--verified-by",
			mode: "advisory-agent",
			verifyCmd: "./operator doctor",
		}),
	);
	throws("reviewDelegateArgv refuses a missing verify-cmd", () =>
		core.reviewDelegateArgv({ claimId, taskId: "selftest-alpha", reviewer: "codex", mode: "advisory-agent", verifyCmd: "" }),
	);
	throws("reviewDelegateArgv refuses a whitespace-only verify-cmd", () =>
		core.reviewDelegateArgv({ claimId, taskId: "selftest-alpha", reviewer: "codex", mode: "advisory-agent", verifyCmd: "   " }),
	);
	throws("reviewDelegateArgv refuses an unknown mode", () =>
		core.reviewDelegateArgv({ claimId, taskId: "selftest-alpha", reviewer: "codex", mode: "vibes", verifyCmd: "./operator doctor" }),
	);
	throws("reviewDelegateArgv refuses uid-isolated without --review-user", () =>
		core.reviewDelegateArgv({
			claimId,
			taskId: "selftest-alpha",
			reviewer: "codex",
			mode: "uid-isolated",
			verifyCmd: "./operator doctor",
		}),
	);
	throws("reviewDelegateArgv refuses a placeholder review-user", () =>
		core.reviewDelegateArgv({
			claimId,
			taskId: "selftest-alpha",
			reviewer: "codex",
			mode: "uid-isolated",
			verifyCmd: "./operator doctor",
			reviewUser: "<review-unix-user>",
		}),
	);
	throws("reviewDelegateArgv refuses --review-user on advisory-agent", () =>
		core.reviewDelegateArgv({
			claimId,
			taskId: "selftest-alpha",
			reviewer: "codex",
			mode: "advisory-agent",
			verifyCmd: "./operator doctor",
			reviewUser: "nobody",
		}),
	);
	throws("reviewDelegateArgv refuses a malformed claim id", () =>
		core.reviewDelegateArgv({
			claimId: "claim-x",
			taskId: "selftest-alpha",
			reviewer: "codex",
			mode: "advisory-agent",
			verifyCmd: "./operator doctor",
		}),
	);
	throws("refuseSelfReview rejects the session author as reviewer", () => core.refuseSelfReview(by, by));
	core.refuseSelfReview("codex", by);
	check("refuseSelfReview allows a distinct reviewer", true);

	const isolatedArgv = core.reviewDelegateArgv({
		claimId,
		taskId: "selftest-alpha",
		reviewer: "codex",
		mode: "uid-isolated",
		verifyCmd: "./operator doctor",
		reviewUser: "nobody",
	});
	check("uid-isolated argv includes --review-user", isolatedArgv.includes("--review-user") && isolatedArgv.includes("nobody"));
	eq("parseReviewModeChoice reads the trusted path", core.parseReviewModeChoice(core.REVIEW_MODE_OPTIONS[0]), "uid-isolated");
	eq("parseReviewModeChoice reads the advisory path", core.parseReviewModeChoice(core.REVIEW_MODE_OPTIONS[1]), "advisory-agent");
	eq("parseReviewModeChoice rejects junk", core.parseReviewModeChoice("vibes"), null);

	const policy = core.parseIdentityPolicy(
		["mode: enforced", "uids:", "  1000:", "    name: builder-one", "    roles:", "      - builder", "  966:", "    name: operator-verifier", "    roles:", "      - verifier"].join(
			"\n",
		),
	);
	eq("parseIdentityPolicy reads mode", policy.mode, "enforced");
	eq("parseIdentityPolicy reads verifier names", core.verifierIdentities(policy).map((u) => u.name), ["operator-verifier"]);
	check(
		"describeVerifierAuthPrompt names the human-auth path",
		core.describeVerifierAuthPrompt(policy, 1000).some((l) => l.includes("authorize the sudo -u run yourself")),
	);

	eq(
		"classifyReviewDelegateError detects broker enrollment",
		core.classifyReviewDelegateError("Error: review-delegate is only implemented for local file-backed ledgers.\n"),
		"broker_enrolled",
	);
	eq(
		"classifyReviewDelegateError detects a missing reviewer",
		core.classifyReviewDelegateError("Error: --reviewer is required; review_harness is routing metadata and cannot supply verifier identity.\n"),
		"missing_reviewer",
	);
	eq(
		"classifyReviewDelegateError detects a missing verify-cmd",
		core.classifyReviewDelegateError("Error: no verification command is recorded; provide --verify-cmd (required_gate is an artifact path, not a command).\n"),
		"missing_verify_cmd",
	);
	check("brokerEnrollmentMessage is explicit", core.brokerEnrollmentMessage().includes("unavailable under broker enrollment"));

	const brokerReport = core.buildSupervisorReviewReport({
		taskId: "selftest-alpha",
		opts: { claimId, taskId: "selftest-alpha", reviewer: "codex", mode: "advisory-agent", verifyCmd: "./operator doctor" },
		argv: advisoryArgv,
		result: {
			stdout: "",
			stderr: "Error: review-delegate is only implemented for local file-backed ledgers.\n",
			code: 1,
		},
	});
	eq("broker failure reports as unavailable", brokerReport.headline, "unavailable under broker enrollment");
	eq("broker failure is an error", brokerReport.level, "error");
	check("broker failure names the local-ledger constraint", brokerReport.lines.some((l) => l.includes("local file-backed ledgers")));

	const reviewDir = join(ledger.ledgerDir, "review_delegations");
	const beforeBundles = existsSync(reviewDir) ? readdirSync(reviewDir).filter((n) => n.endsWith(".yaml")).length : 0;
	const advisoryRun = op(fixture, advisoryArgv);
	eq("review-delegate advisory exits 0 with the built argv", advisoryRun.code, 0);
	if (advisoryRun.code !== 0) {
		check("advisory review-delegate stderr", false, advisoryRun.stdout + advisoryRun.stderr);
	}
	const parsed = core.parseReviewDelegate(advisoryRun);
	check("parseReviewDelegate reads the bundle path", typeof parsed.bundlePath === "string" && parsed.bundlePath!.includes(claimId), parsed.bundlePath ?? "");
	check("parseReviewDelegate reads the script path", typeof parsed.scriptPath === "string" && parsed.scriptPath!.endsWith(".sh"), parsed.scriptPath ?? "");
	check("parseReviewDelegate sees the never-verifies note", parsed.neverVerifies);
	check("the advisory bundle exists on disk", existsSync(parsed.bundlePath ?? ""), parsed.bundlePath ?? "");
	const bundleText = readFileSync(parsed.bundlePath!, "utf8");
	check("the bundle records advisory authority", bundleText.includes("expected_verification_authority: advisory"), bundleText);
	check("the bundle names the explicit reviewer", bundleText.includes("reviewer: codex"), bundleText);
	check("the bundle names the one claim", bundleText.includes(`claim_id: ${claimId}`), bundleText);
	eq(
		"advisory review-delegate wrote exactly one new yaml bundle",
		readdirSync(reviewDir).filter((n) => n.endsWith(".yaml")).length,
		beforeBundles + 1,
	);

	const isolatedRun = op(fixture, isolatedArgv);
	eq("review-delegate uid-isolated exits 0 with the built argv", isolatedRun.code, 0);
	if (isolatedRun.code !== 0) {
		check("uid-isolated review-delegate stderr", false, isolatedRun.stdout + isolatedRun.stderr);
	}
	const isolatedParsed = core.parseReviewDelegate(isolatedRun);
	check("uid-isolated bundle exists", existsSync(isolatedParsed.bundlePath ?? ""));
	const isolatedText = readFileSync(isolatedParsed.bundlePath!, "utf8");
	check("the uid-isolated bundle names review_user", isolatedText.includes("review_user: nobody"), isolatedText);
	check("the uid-isolated run command is sudo, not a silent same-UID fallback", (isolatedParsed.runCommand ?? "").includes("sudo -u nobody"), isolatedParsed.runCommand ?? "");
	check(
		"the generated script is not executed by review-delegate itself",
		isolatedRun.stdout.includes("never verifies by itself"),
	);

	const written = core.buildSupervisorReviewReport({
		taskId: "selftest-alpha",
		opts: { claimId, taskId: "selftest-alpha", reviewer: "codex", mode: "advisory-agent", verifyCmd: "./operator doctor" },
		argv: advisoryArgv,
		result: advisoryRun,
	});
	eq("a successful supervisor-review report is info or warning", written.level === "info" || written.level === "warning", true);
	check("a successful report names the claim", written.headline.includes(claimId), written.headline);
	check(
		"every supervisor-review report says it does not verify",
		written.lines.some((l) => l.includes("does not verify")),
	);
	check(
		"every supervisor-review report distinguishes evidence kinds",
		written.lines.some((l) => l.includes("Verifier-owned status-setting evidence")),
	);
	check("the report records the invocation", written.invocations[0].startsWith("./operator review-delegate"));
	check(
		"the plan separates review target from verifier UID",
		core
			.describeSupervisorReviewPlan({
				claimId,
				taskId: "selftest-alpha",
				reviewer: "codex",
				mode: "advisory-agent",
				verifyCmd: "./operator doctor",
				reviewHarness: "pi",
				sessionAuthor: by,
			})
			.some((l) => l.includes("separate from verifier UID")),
	);

	const after = core.summarizeDoctor(op(fixture, core.doctorArgv()));
	check("doctor still passes after review-delegate writes", after.ok, after.headline);

	eq("sudo credentials argv is sudo -A -v", core.sudoCredentialsArgv(), ["sudo", "-A", "-v"]);
	eq("sudo sample argv is sudo -A true", core.sudoSampleArgv(), ["sudo", "-A", "true"]);
	throws("sudo popup refuses -S", () => core.assertSafeSudoArgv(["sudo", "-S", "-v"]));
	throws("sudo popup refuses missing -A", () => core.assertSafeSudoArgv(["sudo", "-v"]));
	throws("sudo run line refuses -S", () => core.parseSudoURunLine("sudo -S -u nobody bash -lc 'cd /tmp && true'"));
	const sampleRun = "sudo -u nobody bash -lc 'cd /tmp/x && echo hi'";
	eq("sudo review argv injects -A and keeps -u user", core.sudoReviewLaunchArgv(sampleRun), [
		"sudo",
		"-A",
		"-u",
		"nobody",
		"bash",
		"-lc",
		"cd /tmp/x && echo hi",
	]);
	check("sudo review argv has no -S", !core.sudoReviewLaunchArgv(sampleRun).includes("-S"));
	const popupTargets = core.listSudoPopupTargets(ledger);
	check(
		"popup targets include the uid-isolated launch",
		popupTargets.some((t) => t.kind === "uid-isolated-review" && t.reviewUser === "nobody"),
	);
	check("a single launch does not add a credentials extra", !popupTargets.some((t) => t.kind === "credentials"));
	eq("pickSudoPopupTarget skips the chooser for one launch", core.pickSudoPopupTarget(popupTargets, "")?.kind, "uid-isolated-review");
	eq("pickSudoPopupTarget credentials arg is sudo -A -v", core.pickSudoPopupTarget(popupTargets, "credentials")?.kind, "credentials");
	eq("pickSudoPopupTarget sample arg is sudo -A true", core.pickSudoPopupTarget(popupTargets, "sample")?.kind, "sample");
	check(
		"formatSudoInvocation truncates a long review payload",
		core.formatSudoInvocation(core.sudoReviewLaunchArgv(`sudo -u nobody bash -lc 'cd /tmp && ${"pi ".repeat(80)}'`)).length < 160,
	);
	if (isolatedParsed.runCommand) {
		const launchArgv = core.sudoReviewLaunchArgv(isolatedParsed.runCommand);
		eq("live uid-isolated launch uses sudo -A", launchArgv[1], "-A");
		eq("live uid-isolated launch keeps review user", launchArgv[3], "nobody");
		check("live uid-isolated launch has no lifecycle flag", launchArgv.every((a) => !/^--(status|verified-by|verdict)/.test(a)));
	}
}

// --- tier A4: step 4 /op:delegate -------------------------------------------

function tierA4(ledger: core.Ledger): void {
	console.log("\nTier A4: step 4 delegate against the same ledger");

	const createArgv = core.taskCreateArgv({
		taskId: "selftest-alpha-via-grok",
		objective: "Bounded grok implementation from selftest-alpha",
		assign: "grok",
	});
	eq("taskCreateArgv starts with task-create --id", createArgv.slice(0, 3), ["task-create", "--id", "selftest-alpha-via-grok"]);
	check("taskCreateArgv passes --assign grok", createArgv.includes("--assign") && createArgv.includes("grok"));
	check("taskCreateArgv passes objective inline", createArgv.some((a) => a.startsWith("--objective=Bounded grok")));
	check("taskCreateArgv emits no lifecycle flag", createArgv.every((a) => !/^--(status|verified-by|verdict)/.test(a)));
	check("taskCreateArgv does not copy a reviewer by default", !createArgv.includes("--review"));
	throws("taskCreateArgv refuses dual --assign/--review", () =>
		core.taskCreateArgv({
			taskId: "selftest-dual-role",
			objective: "should not land",
			assign: "claude",
			review: "claude",
		}),
	);
	throws("taskCreateArgv refuses an empty objective", () =>
		core.taskCreateArgv({ taskId: "selftest-x", objective: "  ", assign: "grok" }),
	);
	throws("taskCreateArgv refuses a flag-shaped assign", () =>
		core.taskCreateArgv({ taskId: "selftest-x", objective: "x", assign: "--verified-by" }),
	);

	eq("briefArgv names --for and --task", core.briefArgv("selftest-alpha", "claude"), [
		"brief",
		"--for",
		"claude",
		"--task",
		"selftest-alpha",
	]);
	eq("exportBriefArgv names --for and --task", core.exportBriefArgv("selftest-alpha", "claude"), [
		"export-brief",
		"--for",
		"claude",
		"--task",
		"selftest-alpha",
	]);
	throws("session-start --lane is not in the allowlist", () =>
		core.assertSafeArgv(["session-start", "--task", "selftest-alpha", "--harness", "claude", "--lane", "local"]),
	);
	throws("task-create --repo is not in the allowlist", () =>
		core.assertSafeArgv(["task-create", "--id", "x", "--objective=y", "--assign", "grok", "--repo", "."]),
	);

	const parentRouted = core.classifyDelegateTarget({
		target: { alias: "claude", harnessId: "claude", carrierId: "claude" },
		assignedHarness: "claude",
		reviewHarness: "codex",
	});
	eq("assigned_harness is parent-routed", parentRouted.action, "parent-routed");
	const childRoute = core.classifyDelegateTarget({
		target: { alias: "grok", harnessId: "grok", carrierId: "grok" },
		assignedHarness: "claude",
		reviewHarness: "codex",
	});
	eq("unrouted implementer is child-task", childRoute.action, "child-task");
	check("child-task reason names --assign", childRoute.reason.includes("--assign grok"));
	const reviewOnly = core.classifyDelegateTarget({
		target: { alias: "codex", harnessId: "codex", carrierId: "codex" },
		assignedHarness: "claude",
		reviewHarness: "codex",
	});
	eq("review_harness-only is child-task, not a parent reviewer brief", reviewOnly.action, "child-task");
	check("review_harness-only reason says reviewer brief is wrong", reviewOnly.reason.includes("reviewer brief"));
	const dual = core.classifyDelegateTarget({
		target: { alias: "claude", harnessId: "claude", carrierId: "claude" },
		assignedHarness: "claude",
		reviewHarness: "claude",
	});
	eq("dual assigned+review is refused", dual.action, "refuse");
	const selfRoute = core.classifyDelegateTarget({
		target: { alias: "pi-01a05bf2", harnessId: "pi-01a05bf2", carrierId: "pi" },
		assignedHarness: "claude",
		reviewHarness: "codex",
		sessionAuthor: "pi-01a05bf2",
	});
	eq("session author as implementer is refused", selfRoute.action, "refuse");
	throws("refuseSelfDelegate rejects the session author", () => core.refuseSelfDelegate("pi-01a05bf2", "pi-01a05bf2"));
	throws("refuseDualRole rejects matching assign and review", () => core.refuseDualRole("grok", "grok", "task-create"));
	throws("unknown carrier fails closed", () =>
		core.classifyDelegateTarget({
			target: { alias: "fable", harnessId: "fable", carrierId: "fable" },
			assignedHarness: "claude",
			reviewHarness: "codex",
		}),
	);

	eq("defaultChildTaskId uses -via-", core.defaultChildTaskId("selftest-alpha", "grok"), "selftest-alpha-via-grok");
	eq("parseDelegateArgs empty", core.parseDelegateArgs(""), {});
	eq("parseDelegateArgs alias-or-task token", core.parseDelegateArgs("grok"), { token: "grok" });
	eq("parseDelegateArgs task and alias", core.parseDelegateArgs("selftest-alpha grok"), {
		taskId: "selftest-alpha",
		alias: "grok",
	});
	throws("parseDelegateArgs rejects extra tokens", () => core.parseDelegateArgs("a b c"));

	const tokenAlias = core.resolveDelegateToken(ledger, "grok", core.DEFAULT_DELEGATE_TARGETS);
	eq("resolveDelegateToken treats grok as an alias", tokenAlias, { alias: "grok" });
	const tokenTask = core.resolveDelegateToken(ledger, "selftest-alpha", core.DEFAULT_DELEGATE_TARGETS);
	eq("resolveDelegateToken treats selftest-alpha as a task", tokenTask, { taskId: "selftest-alpha" });
	throws("resolveDelegateToken refuses an unknown token", () =>
		core.resolveDelegateToken(ledger, "not-a-thing", core.DEFAULT_DELEGATE_TARGETS),
	);

	throws("parseDelegateTargetsJson refuses assigned_harness override", () =>
		core.parseDelegateTargetsJson(JSON.stringify({ assigned_harness: "grok", targets: [] })),
	);
	throws("parseDelegateTargetsJson refuses a target that overrides review_harness", () =>
		core.parseDelegateTargetsJson(
			JSON.stringify({
				targets: [{ alias: "x", harness_id: "claude", carrier_id: "claude", review_harness: "codex" }],
			}),
		),
	);
	throws("parseDelegateTargetsJson refuses an unknown carrier", () =>
		core.parseDelegateTargetsJson(
			JSON.stringify({
				targets: [{ alias: "fable", harness_id: "fable", carrier_id: "fable" }],
			}),
		),
	);
	const parsedTargets = core.parseDelegateTargetsJson(
		JSON.stringify({
			targets: [
				{
					alias: "gemini-agy",
					harness_id: "gemini-agy",
					carrier_id: "agy",
					isolation: "in-repo",
					brief_format: "export",
				},
			],
		}),
	);
	eq("gemini-agy keeps ledger harness id distinct from carrier id", [parsedTargets[0]?.harnessId, parsedTargets[0]?.carrierId], [
		"gemini-agy",
		"agy",
	]);

	const loaded = core.loadDelegateTargets(ledger);
	check("loadDelegateTargets uses defaults when targets.json is absent", loaded.some((t) => t.alias === "grok"));
	const grokTarget = loaded.find((t) => t.alias === "grok")!;
	const resolvedGrok = core.resolveDelegateTarget(ledger, grokTarget);
	eq("resolveDelegateTarget reads model from harness yaml", resolvedGrok.model, "configured-grok-model");
	eq("resolveDelegateTarget keeps carrier grok", resolvedGrok.carrierId, "grok");
	const agyTarget = loaded.find((t) => t.alias === "gemini-agy")!;
	const resolvedAgy = core.resolveDelegateTarget(ledger, agyTarget);
	eq("gemini-agy carrier is agy, not gemini-agy", resolvedAgy.carrierId, "agy");
	eq("gemini-agy harness id stays gemini-agy", resolvedAgy.harnessId, "gemini-agy");
	check("gemini-agy kind is not used as the carrier", resolvedAgy.harness.kind !== resolvedAgy.carrierId);
	throws("resolveDelegateTarget refuses an invented harness id", () =>
		core.resolveDelegateTarget(ledger, {
			alias: "nope",
			harnessId: "not-a-harness",
			carrierId: "claude",
			model: null,
			isolation: "in-repo",
			briefFormat: "export",
			commandTemplate: null,
		}),
	);

	const harness = core.parseHarnessRecord(["harness_id: grok", "kind: grok", "command: grok", "model: configured-grok-model"].join("\n"));
	eq("parseHarnessRecord reads harness_id", harness.harnessId, "grok");
	eq("parseHarnessRecord reads model", harness.model, "configured-grok-model");
	eq("parseHarnessRecord treats command null", core.parseHarnessRecord("harness_id: x\ncommand: null\n").command, null);

	const label = core.chooserLabelForTarget(
		resolvedGrok,
		childRoute,
		"claude",
		"codex",
	);
	check("chooser label names ledger harness", label.includes("harness=grok"));
	check("chooser label names carrier", label.includes("carrier=grok"));
	check("chooser label names model", label.includes("model=configured-grok-model"));
	check("chooser label names isolation", label.includes("isolation=in-repo"));
	check("chooser label names brief format", label.includes("brief=export"));
	check("chooser label says child-task", label.includes("child task"));
	eq("parseDispatchChoice reads adapter", core.parseDispatchChoice(core.DELEGATE_DISPATCH_OPTIONS[0]), "adapter");
	eq("parseDispatchChoice reads paste-fallback", core.parseDispatchChoice(core.DELEGATE_DISPATCH_OPTIONS[1]), "paste-fallback");
	eq(
		"decideDispatchPath honors paste-fallback",
		core.decideDispatchPath({ requested: "paste-fallback", isolation: "in-repo", briefExists: true }).path,
		"paste-fallback",
	);
	eq(
		"decideDispatchPath refuses to silently run worktree in-repo",
		core.decideDispatchPath({ requested: "adapter", isolation: "worktree", briefExists: true }).path,
		"paste-fallback",
	);
	eq(
		"decideDispatchPath chooses adapter when in-repo and brief exists",
		core.decideDispatchPath({ requested: "adapter", isolation: "in-repo", briefExists: true }).path,
		"adapter",
	);

	const adapterArgv = core.adapterInvokeArgv({
		moduleRoot: core.adapterModuleRoot(ledger),
		carrierId: "grok",
		model: "configured-grok-model",
		briefPath: "/tmp/brief.md",
		workspace: ledger.root,
	});
	eq("adapterInvokeArgv starts with python3 -c", adapterArgv.slice(0, 2), ["python3", "-c"]);
	eq("adapterInvokeArgv uses the fixed IMPLEMENTER script", adapterArgv[2], core.ADAPTER_INVOKE_SCRIPT);
	check("the adapter script calls IMPLEMENTER", core.ADAPTER_INVOKE_SCRIPT.includes("ha.Role.IMPLEMENTER"));
	check("the adapter script does not call JUDGE", !core.ADAPTER_INVOKE_SCRIPT.includes("JUDGE"));
	check("adapterInvokeArgv names the grok carrier", adapterArgv.includes("grok"));
	throws("assertSafeAdapterArgv rejects a mutated script", () =>
		core.assertSafeAdapterArgv(["python3", "-c", "print(1)", ledger.root, "grok", "m", "/tmp/b", ledger.root]),
	);
	throws("adapterInvokeArgv refuses an unknown carrier", () =>
		core.adapterInvokeArgv({
			moduleRoot: ledger.root,
			carrierId: "fable",
			model: "x",
			briefPath: "/tmp/b",
			workspace: ledger.root,
		}),
	);

	const profileDump = spawnSync(
		"python3",
		["-c", "import harness_adapter as ha; print(','.join(sorted(ha.PROFILES)))"],
		{ cwd: REPO_ROOT, encoding: "utf8" },
	);
	eq("python harness_adapter import for profile dump exits 0", profileDump.status ?? 1, 0);
	const pyProfiles = (profileDump.stdout ?? "").trim().split(",").filter(Boolean).sort();
	eq("ADAPTER_CARRIER_IDS matches harness_adapter.PROFILES", [...core.ADAPTER_CARRIER_IDS].sort(), pyProfiles);

	const parentBefore = readFileSync(join(ledger.ledgerDir, "tasks", "selftest-alpha.yaml"), "utf8");
	check("parent starts assigned to claude", parentBefore.includes("assigned_harness: claude"), parentBefore);
	check("parent starts reviewed by codex", parentBefore.includes("review_harness: codex"), parentBefore);

	const childRun = op(fixture, createArgv);
	eq("task-create child exits 0", childRun.code, 0);
	eq("parseTaskCreate reads the child id", core.parseTaskCreate(childRun.stdout), "selftest-alpha-via-grok");
	check("the child task exists on disk", core.taskRecordExists(ledger, "selftest-alpha-via-grok"));
	const childYaml = readFileSync(join(ledger.ledgerDir, "tasks", "selftest-alpha-via-grok.yaml"), "utf8");
	check("the child is assigned grok", childYaml.includes("assigned_harness: grok"), childYaml);
	check("the child did not copy parent review_harness", !childYaml.includes("review_harness: codex"), childYaml);
	const parentAfter = readFileSync(join(ledger.ledgerDir, "tasks", "selftest-alpha.yaml"), "utf8");
	check("parent assigned_harness is unchanged", parentAfter.includes("assigned_harness: claude"), parentAfter);
	check("parent review_harness is unchanged", parentAfter.includes("review_harness: codex"), parentAfter);

	const unroutedStart = op(fixture, core.sessionStartArgv("selftest-beta", "grok"));
	eq("session-start grok on an unrouted non-running task fails", unroutedStart.code === 0 ? 0 : 1, 1);
	eq(
		"classifySessionStartError sees an unrouted harness",
		core.classifySessionStartError(unroutedStart.stderr, unroutedStart.stdout),
		"unrouted",
	);

	const childStart = op(fixture, core.sessionStartArgv("selftest-alpha-via-grok", "grok"));
	eq("session-start on the child exits 0", childStart.code, 0);
	const parsedStart = core.parseSessionStart(childStart.stdout);
	eq("parseSessionStart reads the child task id", parsedStart.taskId, "selftest-alpha-via-grok");
	check("parseSessionStart reads the export brief path", typeof parsedStart.briefPath === "string" && (parsedStart.briefPath ?? "").includes("selftest-alpha-via-grok.grok.export.md"));
	check("the export brief exists", existsSync(parsedStart.briefPath ?? ""), parsedStart.briefPath ?? "");
	check("parseSessionStart reads a usage id", /^usage-[0-9]+$/.test(parsedStart.usageId ?? ""), parsedStart.usageId ?? "");
	const briefText = readFileSync(parsedStart.briefPath!, "utf8");
	check("the child brief is a builder brief, not a reviewer brief", briefText.includes("Builders attach evidence but do NOT set `--status`."));
	check("the child brief names grok", briefText.includes("`grok`"));

	const dualCreate = op(fixture, [
		"task-create",
		"--id",
		"selftest-dual",
		"-o",
		"Dual assigned and review",
		"-a",
		"claude",
		"--review",
		"claude",
	]);
	eq("CLI can still record a dual-role task (the extension must refuse it)", dualCreate.code, 0);
	const dualClass = core.classifyDelegateTarget({
		target: { alias: "claude", harnessId: "claude", carrierId: "claude" },
		assignedHarness: "claude",
		reviewHarness: "claude",
	});
	eq("the extension refuses to delegate to a dual-role target", dualClass.action, "refuse");

	const already = op(fixture, core.sessionStartArgv("selftest-alpha", "claude"));
	eq(
		"classifySessionStartError sees already running",
		core.classifySessionStartError(already.stderr, already.stdout),
		"already_running",
	);

	const plan = core.describeDelegatePlan({
		parentTaskId: "selftest-alpha",
		workTaskId: "selftest-alpha-via-grok",
		target: resolvedGrok,
		route: childRoute,
		childObjective: "Bounded grok implementation from selftest-alpha",
		sessionAuthor: "pi-01a05bf2",
		assignedHarness: "claude",
		reviewHarness: "codex",
		dispatch: "paste-fallback",
		dispatchReason: "user chose the labeled paste/export fallback",
	});
	check("the plan names ledger harness vs carrier", plan.some((l) => l.includes("ledger harness")) && plan.some((l) => l.includes("carrier/adapter")));
	check("the plan says parent routing is unchanged", plan.some((l) => l.includes("parent routing unchanged")));
	check("the plan labels paste as fallback", plan.some((l) => l.includes("LABELED FALLBACK")));
	check(
		"every delegate plan says --by is not --harness",
		plan.some((l) => l.includes("provenance only")),
	);

	const report = core.buildDelegateReport({
		parentTaskId: "selftest-alpha",
		workTaskId: "selftest-alpha-via-grok",
		target: resolvedGrok,
		route: childRoute,
		dispatch: "paste-fallback",
		dispatchReason: "user chose the labeled paste/export fallback",
		childCreated: true,
		parentAssignedHarness: "claude",
		parentReviewHarness: "codex",
		briefFile: parsedStart.briefPath,
		usageId: parsedStart.usageId,
		adapterState: null,
		invocations: [core.formatInvocation(createArgv), core.formatInvocation(core.sessionStartArgv("selftest-alpha-via-grok", "grok"))],
		results: [childRun, childStart],
	});
	eq("a paste-fallback report is a warning, not a silent success", report.level, "warning");
	check("the report names the labeled fallback", report.headline.includes("fallback") && report.headline.includes("grok"));
	check("the report says parent routing is unchanged", report.lines.some((l) => l.includes("routing is unchanged")));
	check("the report keeps the boundary notes", report.lines.some((l) => l.includes("Paste/export-only is a labeled fallback")));
	check("the report records operator invocations", report.invocations.some((i) => i.startsWith("./operator task-create")));

	const after = core.summarizeDoctor(op(fixture, core.doctorArgv()));
	check("doctor still passes after delegate child-task writes", after.ok, after.headline);
}

// --- tier A5: orientation next-steps / project / workflow guidance -----------

function sampleRoadmap(): core.RoadmapPbc {
	return {
		path: "owners-manual/pbc/appendix-pi-operator-extension.pbc.md",
		steps: [{ step: 1, name: "Read-only orientation", gate: "doctor/status/tasks/use" }],
		futureFeatures: [
			{ id: "POE-FUT-010", name: "next-steps", command: "/op:next-steps", description: "prioritized actions" },
			{ id: "POE-FUT-011", name: "dashboard", command: "/op:project", description: "prefix dashboard" },
			{ id: "POE-FUT-013", name: "workflow", command: null, description: "strictness guidance" },
		],
		issues: [
			{ id: "POE-ISS-009", summary: "handoff go treated as prose", nextStep: "generate a closeout draft" },
			{ id: "POE-ISS-013", summary: "review/delegation UI plumbing", nextStep: "rename prompts around model/persona" },
		],
	};
}

function sampleTaskShow(overrides: Partial<core.TaskShowSummary["fields"]> = {}, counts: Partial<core.TaskShowSummary> = {}): core.TaskShowSummary {
	return {
		fields: {
			"Task ID": "selftest-alpha",
			Status: "assigned",
			"Assigned Harness": "claude",
			"Review Harness": "codex",
			"Next Action": "Ask a distinct identity to verify claim-0001.",
			...overrides,
		},
		assumptions: 0,
		claims: 1,
		evidence: 0,
		handoffs: 0,
		...counts,
	};
}

function tierA5(): void {
	console.log("\nTier A5: orientation next-steps, project dashboard, workflow guidance");

	eq("parseNextStepsArgs empty", orientation.parseNextStepsArgs(""), { popup: false, mode: "unset", unknown: [] });
	eq("parseNextStepsArgs popup + trust", orientation.parseNextStepsArgs("popup engineering-trust"), {
		popup: true,
		mode: "engineering-trust",
		unknown: [],
	});
	eq("parseNextStepsArgs mode=support", orientation.parseNextStepsArgs("mode=support"), {
		popup: false,
		mode: "support",
		unknown: [],
	});
	eq("parseProjectArgs missing", orientation.parseProjectArgs(""), {
		prefix: null,
		error: "Project prefix required. Example: /op:project pi-operator-extension",
	});
	eq("parseProjectArgs extra tokens are ambiguous", orientation.parseProjectArgs("foo bar").prefix, null);
	check("parseProjectArgs extra tokens error names ambiguous", (orientation.parseProjectArgs("foo bar").error ?? "").includes("Ambiguous"));
	eq("parseProjectArgs roadmap flag", orientation.parseProjectArgs("--project selftest"), { prefix: "selftest", error: null });
	check("flag-shaped prefix is refused", (orientation.parseProjectArgs("--status").error ?? "").includes("flag-shaped"));

	const empty = orientation.buildNextStepsReport({
		roadmap: sampleRoadmap(),
		activeTask: null,
		activeOrigin: "none",
		taskShow: null,
		claims: [],
		invocations: ["./operator task-list"],
		taskCount: 0,
	});
	check("empty ledger is explicit", empty.headline === "empty ledger" && empty.lines.some((l) => l.includes("Empty ledger")));
	check("empty ledger is a warning", empty.level === "warning");
	check("empty ledger agent text includes the action", orientation.orientationAgentContent(empty).includes("Empty ledger"));
	const emptyMsg = orientation.orientationSendMessage(empty);
	eq("orientation sendMessage uses nextTurn", emptyMsg.options.deliverAs, "nextTurn");
	eq("orientation sendMessage is not TUI-only display", emptyMsg.message.display, false);
	eq("orientation sendMessage customType", emptyMsg.message.customType, "operator-orientation");
	check("orientation sendMessage content is the action list", emptyMsg.message.content.includes("Empty ledger"));

	const noTask = orientation.buildNextStepsReport({
		roadmap: sampleRoadmap(),
		activeTask: null,
		activeOrigin: "none",
		taskShow: null,
		claims: [],
		invocations: ["./operator task-list"],
		taskCount: 2,
	});
	check("no-active-task is explicit", noTask.headline === "no active task selected" && noTask.lines.some((l) => l.includes("/op:use")));

	const unverified: core.ClaimRow[] = [
		{ id: "claim-0001", taskId: "selftest-alpha", type: "file_exists", status: "UNVERIFIED", text: "exists" },
	];
	const withNext = orientation.buildNextStepsReport({
		roadmap: sampleRoadmap(),
		activeTask: "selftest-alpha",
		activeOrigin: "session",
		taskShow: sampleTaskShow(),
		claims: unverified,
		invocations: ["./operator task-show --id selftest-alpha"],
		identity: { mode: "enforced", uids: [{ uid: 966, name: "operator-verifier", roles: ["verifier"] }] },
		taskCount: 2,
	});
	const withNextActions = orientation.prioritizeNextActions({
		roadmap: sampleRoadmap(),
		activeTask: "selftest-alpha",
		activeOrigin: "session",
		taskShow: sampleTaskShow(),
		claims: unverified,
		invocations: [],
		identity: { mode: "enforced", uids: [] },
		taskCount: 2,
	});
	eq("next_action is priority 1", withNextActions[0]?.kind, "next_action");
	eq("unverified claims come after next_action", withNextActions[1]?.kind, "unverified-claim");
	check("missing evidence gate is listed", withNextActions.some((a) => a.kind === "missing-gate" && a.text.includes("Missing evidence gate")));
	check("next-steps distinguishes approval", withNext.lines.some((l) => l.includes("Approval / user acceptance")));
	check("next-steps distinguishes advisory", withNext.lines.some((l) => l.includes("Advisory review")));
	check("next-steps distinguishes uid-isolated", withNext.lines.some((l) => l.includes("UID-isolated verification")));
	check("enforced mode says policy is unchanged", withNext.lines.some((l) => l.includes("Enforced identity policy is unchanged")));
	check("agent content includes next_action text", orientation.orientationAgentContent(withNext).includes("Ask a distinct identity to verify claim-0001"));
	check("future slices are PBC id order not last-3-only", withNext.lines.some((l) => l.includes("POE-FUT-010") && l.includes("/op:next-steps")));
	check("next-steps does not execute a verify command", withNext.lines.some((l) => l.includes("does not execute stored verification commands")));

	const staleHandoff = orientation.detectStaleNextAction({
		nextAction: "Reload Pi and run /op:handoff go",
		status: "verified",
		claims: [],
		evidenceCount: 0,
		handoffCount: 2,
	});
	check("completed handoff go is stale", staleHandoff.stale);
	const staleVerified = orientation.detectStaleNextAction({
		nextAction: "Verify claim-0001",
		status: "assigned",
		claims: [{ id: "claim-0001", taskId: "t", type: "file_exists", status: "VERIFIED", text: "x" }],
		evidenceCount: 1,
		handoffCount: 0,
	});
	check("verifying an already-VERIFIED claim is stale", staleVerified.stale);
	const notStaleOwnerDecision = orientation.detectStaleNextAction({
		nextAction: "Owner decision: proceed to Step 2",
		status: "verified",
		claims: [{ id: "claim-0001", taskId: "t", type: "file_exists", status: "VERIFIED", text: "x" }],
		evidenceCount: 1,
		handoffCount: 1,
	});
	check("owner decision to proceed is not stale", !notStaleOwnerDecision.stale);
	const staleReport = orientation.buildNextStepsReport({
		roadmap: sampleRoadmap(),
		activeTask: "selftest-alpha",
		activeOrigin: "ledger",
		taskShow: sampleTaskShow({ Status: "verified", "Next Action": "Reload Pi and run /op:handoff go" }, { handoffs: 1, evidence: 1 }),
		claims: [{ id: "claim-0001", taskId: "selftest-alpha", type: "file_exists", status: "VERIFIED", text: "x" }],
		invocations: [],
		taskCount: 2,
	});
	check("stale next_action is warned rather than recommended blindly", staleReport.lines.some((l) => l.includes("STALE ledger next_action")));
	check("stale report level is warning", staleReport.level === "warning");

	const missingReview = orientation.prioritizeNextActions({
		roadmap: sampleRoadmap(),
		activeTask: "selftest-alpha",
		activeOrigin: "session",
		taskShow: sampleTaskShow({ "Review Harness": "None", "Next Action": "None" }),
		claims: unverified,
		invocations: [],
		identity: { mode: "enforced", uids: [] },
		taskCount: 1,
	});
	check("missing review harness is a gate", missingReview.some((a) => a.kind === "missing-gate" && a.text.includes("Missing review gate")));

	const support = orientation.buildNextStepsReport({
		roadmap: sampleRoadmap(),
		activeTask: "selftest-alpha",
		activeOrigin: "session",
		taskShow: sampleTaskShow(),
		claims: unverified,
		invocations: [],
		identity: { mode: "enforced", uids: [{ uid: 966, name: "operator-verifier", roles: ["verifier"] }] },
		taskCount: 1,
		mode: "support",
	});
	check("support mode names user acceptance", support.lines.some((l) => l.includes("user acceptance may close the deliverable")));
	check("support mode says acceptance is not verification", support.lines.some((l) => /User acceptance is not verification/i.test(l)));
	check("support mode does not weaken enforced UID policy", support.lines.some((l) => l.includes("cannot downgrade UID-isolated")));
	check("support mode still lists unverified claims", support.lines.some((l) => l.includes("Unverified claim(s): claim-0001")));

	const light = orientation.buildNextStepsReport({
		roadmap: sampleRoadmap(),
		activeTask: "selftest-alpha",
		activeOrigin: "session",
		taskShow: sampleTaskShow(),
		claims: unverified,
		invocations: [],
		identity: { mode: "single_user", uids: [] },
		taskCount: 1,
		mode: "engineering-light",
	});
	check("engineering-light expects claim/evidence/handoff", light.lines.some((l) => l.includes("claim, evidence, and handoff")));
	check("engineering-light treats advisory as not trusted", light.lines.some((l) => l.includes("not trusted verification")));

	const trust = orientation.buildNextStepsReport({
		roadmap: sampleRoadmap(),
		activeTask: "selftest-alpha",
		activeOrigin: "session",
		taskShow: sampleTaskShow(),
		claims: unverified,
		invocations: [],
		identity: { mode: "enforced", uids: [] },
		taskCount: 1,
		mode: "engineering-trust",
	});
	check("engineering-trust requires distinct verifier", trust.lines.some((l) => l.includes("distinct verifier UID")));
	check("engineering-trust rejects same-UID as sufficient", trust.lines.some((l) => l.includes("Same-UID advisory review cannot satisfy")));
	check("engineering-trust rejects acceptance as substitute", trust.lines.some((l) => l.includes("User acceptance cannot substitute")));
	eq(
		"engineering-trust unverified authority is uid-isolated",
		orientation.prioritizeNextActions({
			roadmap: sampleRoadmap(),
			activeTask: "selftest-alpha",
			activeOrigin: "session",
			taskShow: sampleTaskShow(),
			claims: unverified,
			invocations: [],
			identity: { mode: "enforced", uids: [] },
			taskCount: 1,
			mode: "engineering-trust",
		}).find((a) => a.kind === "unverified-claim")?.authority,
		"uid-isolated",
	);
	eq(
		"support unverified authority stays approval, not a verifier",
		orientation.prioritizeNextActions({
			roadmap: sampleRoadmap(),
			activeTask: "selftest-alpha",
			activeOrigin: "session",
			taskShow: sampleTaskShow(),
			claims: unverified,
			invocations: [],
			identity: { mode: "enforced", uids: [] },
			taskCount: 1,
			mode: "support",
		}).find((a) => a.kind === "unverified-claim")?.authority,
		"approval",
	);

	eq("parseClaimsCell", orientation.parseClaimsCell("V:1 Q:0 O:3"), {
		verified: 1,
		quarantined: 0,
		open: 3,
		total: 4,
		parsed: true,
	});

	const rows: core.TaskRow[] = [
		{ id: "selftest-beta", status: "assigned", assigned: "pi", reviewer: "None", claims: "V:0 Q:0 O:1", nextAction: "None" },
		{ id: "selftest-alpha", status: "verified", assigned: "claude", reviewer: "codex", claims: "V:1 Q:0 O:0", nextAction: "Reload Pi and run /op:handoff go" },
		{ id: "other-task", status: "new", assigned: "None", reviewer: "None", claims: "V:0 Q:0 O:0", nextAction: "None" },
	];
	const matched = orientation.matchTasksByPrefix(rows, "selftest");
	eq(
		"prefix grouping is lexicographic",
		matched.matches.map((r) => r.id),
		["selftest-alpha", "selftest-beta"],
	);
	check("prefix grouping does not invent phases", !matched.warnings.some((w) => /phase 1|planning|implementation phase/i.test(w)));
	eq("unrelated ids are excluded", matched.matches.some((r) => r.id === "other-task"), false);
	eq("empty prefix match set", orientation.matchTasksByPrefix(rows, "no-such").matches.length, 0);
	const incomplete = orientation.matchTasksByPrefix(rows, "selftest-alp");
	check("incomplete token boundary is warned", incomplete.incompleteBoundary && incomplete.warnings.some((w) => w.includes("token boundary")));
	const ambiguous = orientation.matchTasksByPrefix(
		[
			{ id: "pi-alpha-one", status: "new", assigned: "None", reviewer: "None", claims: "V:0 Q:0 O:0", nextAction: "None" },
			{ id: "pi-beta-one", status: "new", assigned: "None", reviewer: "None", claims: "V:0 Q:0 O:0", nextAction: "None" },
		],
		"pi",
	);
	check("single-token prefix across families is ambiguous", ambiguous.ambiguousFamilies);

	const dash = orientation.buildProjectDashboardReport({
		prefix: "selftest",
		match: matched,
		snapshots: [
			{
				row: rows[1]!,
				taskShow: sampleTaskShow({ Status: "verified", "Next Action": "Reload Pi and run /op:handoff go" }, { evidence: 2, handoffs: 1, claims: 1 }),
				claims: [{ id: "claim-0001", taskId: "selftest-alpha", type: "file_exists", status: "VERIFIED", text: "x" }],
			},
			{
				row: rows[0]!,
				taskShow: sampleTaskShow({ "Task ID": "selftest-beta", Status: "assigned", "Next Action": "None", "Review Harness": "None" }, { evidence: 0, handoffs: 0, claims: 1 }),
				claims: [{ id: "claim-0002", taskId: "selftest-beta", type: "file_exists", status: "UNVERIFIED", text: "y" }],
			},
		],
		roadmap: sampleRoadmap(),
		activeTask: "selftest-beta",
		invocations: ["./operator task-list"],
		identity: { mode: "enforced", uids: [] },
	});
	check("dashboard headline counts tasks", dash.headline.includes("2 task(s)"));
	check("dashboard lists both task ids", dash.lines.some((l) => l.includes("selftest-alpha")) && dash.lines.some((l) => l.includes("selftest-beta")));
	check("dashboard shows verified/total claims", dash.lines.some((l) => l.includes("1/1")) && dash.lines.some((l) => l.includes("0/1")));
	check("dashboard shows latest verified claim", dash.lines.some((l) => l.includes("claim-0001")));
	check("dashboard flags stale next_action", dash.lines.some((l) => /STALE/.test(l)));
	check("dashboard labels grouping as not a phase order", dash.lines.some((l) => l.includes("Not a project phase order")));
	check("dashboard uses the active task for recommended next", dash.lines.some((l) => l.includes("task selftest-beta") && l.includes("active task")));
	check("dashboard does not mutate", dash.lines.some((l) => l.includes("Task status was not mutated")));

	const emptyDash = orientation.buildProjectDashboardReport({
		prefix: "missing",
		match: { matches: [], families: [], incompleteBoundary: false, ambiguousFamilies: false, warnings: [] },
		snapshots: [],
		roadmap: sampleRoadmap(),
		activeTask: null,
		invocations: [],
	});
	check("empty prefix match is explicit", emptyDash.headline.includes("no tasks match") && emptyDash.lines.some((l) => l.includes("No tasks match prefix")));
	const required = orientation.buildPrefixRequiredReport("Project prefix required. Example: /op:project pi-operator-extension");
	check("missing prefix is explicit", required.headline === "prefix required");
}

// --- carrier-neutral client --------------------------------------------------

function stubRunner(script: Array<{ stdout?: string; stderr?: string; code: number }>): {
	calls: string[][];
	runner: { exec: (command: string, args: string[]) => Promise<core.CommandResult> };
} {
	const calls: string[][] = [];
	let i = 0;
	return {
		calls,
		runner: {
			async exec(_command: string, args: string[]) {
				calls.push(args);
				const next = script[Math.min(i, script.length - 1)] ?? { code: 1 };
				i += 1;
				return { stdout: next.stdout ?? "", stderr: next.stderr ?? "", code: next.code };
			},
		},
	};
}

async function tierAClient(ledger: core.Ledger): Promise<void> {
	console.log("\nTier A-client: carrier-neutral OperatorClient (no Pi UI)");
	const already = stubRunner([{ stdout: "", stderr: "Error: Task 'selftest-alpha' is already running. Use --force to override.", code: 1 }]);
	const startClient = new OperatorClient(ledger, already.runner);
	const started = await startClient.startSession("selftest-alpha", "claude");
	eq("startSession already-running is idempotent", started.idempotent, true);
	eq("startSession already-running reports success", started.code, 0);
	eq("startSession argv is session-start --task --harness", already.calls[0], [
		"session-start",
		"--task",
		"selftest-alpha",
		"--harness",
		"claude",
	]);
	check("startSession argv has no --status", !already.calls[0]?.some((a) => a === "--status" || a.startsWith("--status=")));

	const closed = stubRunner([
		{ stdout: "", stderr: "Error: Usage record 'usage-0001' is already closed (ended_at: 2026-01-01). Use --force to override.", code: 1 },
	]);
	const endClient = new OperatorClient(ledger, closed.runner);
	const ended = await endClient.endSession("usage-0001", "useful", 0);
	eq("endSession already-closed is idempotent", ended.idempotent, true);
	eq("endSession already-closed reports success", ended.code, 0);
	eq("endSession argv is session-end usage --outcome --cost", closed.calls[0], [
		"session-end",
		"usage-0001",
		"--outcome",
		"useful",
		"--cost",
		"0",
	]);
	check("endSession argv has no --status", !closed.calls[0]?.some((a) => a === "--status" || a.startsWith("--status=")));

	try {
		await startClient.taskShow("no-such-task");
		check("taskShow missing task throws", false, "expected a throw");
	} catch {
		check("taskShow missing task throws", true);
	}

	const created = op(fixture, ["task-create", "--id", "selftest-client", "-o", "Client lifecycle", "-a", "claude"]);
	eq("selftest-client task-create exits 0", created.code, 0);
	const realRunner = {
		async exec(command: string, args: string[], options?: { cwd?: string }) {
			const r = spawnSync(command, args, { cwd: options?.cwd, encoding: "utf8" });
			return { stdout: r.stdout ?? "", stderr: r.stderr ?? "", code: r.status ?? 1 };
		},
	};
	const live = new OperatorClient(ledger, realRunner);
	const first = await live.startSession("selftest-client", "claude");
	check("live startSession exits 0", first.code === 0 && !first.idempotent, `${first.stderr}${first.stdout}`);
	const usageId = core.parseSessionStart(first.stdout).usageId;
	const second = await live.startSession("selftest-client", "claude");
	eq("repeating live startSession is idempotent", second.idempotent, true);
	eq("repeating live startSession does not fail", second.code, 0);
	if (usageId) {
		const close1 = await live.endSession(usageId, "useful", 0);
		check("live endSession exits 0", close1.code === 0 && !close1.idempotent, `${close1.stderr}${close1.stdout}`);
		const close2 = await live.endSession(usageId, "useful", 0);
		eq("repeating live endSession is idempotent", close2.idempotent, true);
		eq("repeating live endSession does not fail", close2.code, 0);
	} else {
		check("live startSession minted a usage id", false, first.stdout + first.stderr);
	}
}

// --- pi discovery ------------------------------------------------------------

function findPiPackage(): string | null {
	const fromEnv = process.env.PI_PACKAGE_DIR;
	if (fromEnv && existsSync(join(fromEnv, "dist", "index.js"))) return fromEnv;
	for (const dir of (process.env.PATH ?? "").split(delimiter)) {
		const candidate = join(dir, "pi");
		if (!existsSync(candidate)) continue;
		let real: string;
		try {
			real = realpathSync(candidate);
		} catch {
			continue;
		}
		let probe = dirname(real);
		for (let i = 0; i < 6; i += 1) {
			if (existsSync(join(probe, "dist", "index.js")) && existsSync(join(probe, "package.json"))) return probe;
			const parent = dirname(probe);
			if (parent === probe) break;
			probe = parent;
		}
	}
	return null;
}

// --- tier B: real extension load --------------------------------------------

async function tierB(piPackage: string | null): Promise<unknown[] | null> {
	console.log("\nTier B: index.ts through pi's own extension loader");
	if (!piPackage) {
		skips.push("Tier B: pi package not found (set PI_PACKAGE_DIR to run it)");
		console.log("  skip (pi not installed)");
		return null;
	}
	type PiLoader = {
		discoverAndLoadExtensions: (...args: never[]) => Promise<{
			errors: unknown[];
			extensions: Array<{
				path: string;
				commands: Map<string, { description?: string }>;
				tools: Map<string, unknown>;
				entryRenderers?: Map<string, unknown>;
			}>;
		}>;
	};
	const imported = applyImportResult<PiLoader>(
		"Tier B",
		await importPiModule<PiLoader>(
			join(piPackage, "dist", "core", "extensions", "index.js"),
			join(piPackage, "dist", "index.js"),
		),
	);
	if (!imported) return null;
	const pi = imported;
	if (typeof pi.discoverAndLoadExtensions !== "function") {
		skips.push("Tier B: pi package has no discoverAndLoadExtensions");
		console.log("  skip (pi loader shape changed)");
		return null;
	}
	const agentDir = mkdtempSync(join(tmpdir(), "op-ext-agentdir-"));
	process.on("exit", () => rmSync(agentDir, { recursive: true, force: true }));
	const result = await pi.discoverAndLoadExtensions([], REPO_ROOT, agentDir);
	eq("no extension load errors", result.errors, []);
	const ext = result.extensions.find((e: { path: string }) => e.path.includes(join(".pi", "extensions", "operator")));
	check("the operator extension was discovered", !!ext, `paths: ${result.extensions.map((e: { path: string }) => e.path).join(", ")}`);
	if (!ext) return null;
	const names = [...ext.commands.keys()].sort();
	eq("registers exactly the implemented Operator commands", names, [
		"op:claim",
		"op:delegate",
		"op:doctor",
		"op:evidence",
		"op:handoff",
		"op:next-steps",
		"op:popup",
		"op:project",
		"op:roadmap",
		"op:status",
		"op:supervisor-review",
		"op:tasks",
		"op:use",
	]);
	check(
		"every command has a description",
		names.every((n: string) => !!ext.commands.get(n)?.description),
	);
	check("registers no model-callable tools at step 4", ext.tools.size === 0, `tools: ${[...ext.tools.keys()].join(", ")}`);
	check("registers /op:delegate", ext.commands.has("op:delegate"));
	check("registers /op:supervisor-review", ext.commands.has("op:supervisor-review"));
	check("does not register /pbc:define", !ext.commands.has("pbc:define"));
	check("does not register /pbc:feature", !ext.commands.has("pbc:feature"));
	// The renderer load is deliberately non-fatal, so assert it actually
	// happened: without it /op:* output never reaches the transcript.
	check(
		"registers the report entry renderer",
		!!ext.entryRenderers?.get("operator-report"),
		`renderers: ${[...(ext.entryRenderers?.keys() ?? [])].join(", ")}`,
	);
	integrationCoverage.tierB = true;
	return [pi, ext];
}

// --- tier C: drive the real handlers ----------------------------------------

interface StubReport {
	type: string;
	data: core.Report | { taskId?: string };
}

async function tierC(piPackage: string | null, ledger: core.Ledger): Promise<void> {
	console.log("\nTier C: the registered handlers, end to end, with a stub UI");
	if (!piPackage) {
		skips.push("Tier C: pi package not found");
		console.log("  skip (pi not installed)");
		return;
	}
	type Loader = {
		createExtensionRuntime: () => Record<string, unknown>;
		loadExtensions: (
			paths: string[],
			cwd: string,
			eventBus: unknown,
			runtime: unknown,
		) => Promise<{
			errors: unknown[];
			extensions: Array<{ commands: Map<string, { handler: (a: string, c: unknown) => Promise<void> }> }>;
		}>;
	};
	const loader = applyImportResult<Loader>(
		"Tier C",
		await importPiModule<Loader>(join(piPackage, "dist", "core", "extensions", "loader.js")),
	);
	if (!loader) return;
	if (typeof loader.loadExtensions !== "function" || typeof loader.createExtensionRuntime !== "function") {
		skips.push("Tier C: pi loader internals changed shape");
		console.log("  skip (loader internals changed shape)");
		return;
	}

	const entries: StubReport[] = [];
	const runtime = loader.createExtensionRuntime();
	runtime.appendEntry = (type: string, data: unknown) => {
		entries.push({ type, data: data as core.Report });
	};
	const agentMessages: Array<{ content: string; deliverAs?: string; customType?: string }> = [];
	runtime.sendMessage = (
		message: { customType?: string; content?: string },
		options?: { deliverAs?: string },
	) => {
		agentMessages.push({
			content: message.content ?? "",
			deliverAs: options?.deliverAs,
			customType: message.customType,
		});
	};

	// The extension resolves its ledger from ctx.cwd, so run it in a directory
	// that has both a .operator dir and an operator binary: a copy of the repo
	// root's binary next to the fixture ledger.
	const extPath = join(REPO_ROOT, ".pi", "extensions", "operator", "index.ts");
	const loaded = await loader.loadExtensions([extPath], ledger.root, undefined, runtime);
	eq("tier C load has no errors", loaded.errors, []);
	const commands = loaded.extensions[0]?.commands;
	check("tier C got the command map", !!commands);
	if (!commands) return;

	let confirmAnswer = false;
	let selectAnswer: string | undefined;
	const selectQueue: Array<string | undefined> = [];
	const inputQueue: Array<string | undefined> = [];
	let editorFn: (prefill: string) => string | undefined = () => undefined;
	let sessionIdValue: string | null = "01a05bf2-9c1e-7a2b-8000-0123456789ab";
	const notifications: Array<[string, string]> = [];
	const ctx = {
		cwd: ledger.root,
		hasUI: true,
		mode: "tui",
		isProjectTrusted: () => true,
		sessionManager: {
			getEntries: () => [],
			getSessionId: () => sessionIdValue ?? "",
		},
		ui: {
			notify: (message: string, level = "info") => {
				notifications.push([level, message]);
			},
			confirm: async () => confirmAnswer,
			select: async (_title: string, _options: string[]) =>
				selectQueue.length > 0 ? selectQueue.shift() : selectAnswer,
			input: async () => (inputQueue.length > 0 ? inputQueue.shift() : undefined),
			editor: async (_title: string, prefill = "") => editorFn(prefill),
			setStatus: () => {},
			setWidget: () => {},
		},
	};

	const yamlNames = (dir: string): string[] => {
		try {
			return readdirSync(dir)
				.filter((n) => n.endsWith(".yaml"))
				.sort();
		} catch {
			return [];
		}
	};

	const lastReport = (): core.Report => entries[entries.length - 1].data as core.Report;

	await commands.get("op:doctor")!.handler("", ctx);
	let report = lastReport();
	eq("/op:doctor emits a report entry", report.command, "/op:doctor");
	eq("/op:doctor names its invocation", report.invocations, ["./operator doctor"]);
	check("/op:doctor passes on the clean fixture ledger", report.level !== "error", report.headline);

	await commands.get("op:tasks")!.handler("", ctx);
	report = lastReport();
	eq("/op:tasks emits a report entry", report.command, "/op:tasks");
	eq("/op:tasks reports the fixture tasks plus A4/client children", report.headline, "5 tasks");

	await commands.get("op:tasks")!.handler("beta", ctx);
	report = lastReport();
	eq("/op:tasks filters", report.headline, "1 task");
	check("/op:tasks records the filtered invocation", report.invocations[0].includes("--filter beta"), report.invocations[0]);

	// current_task is selftest-alpha at this point (tier A set it).
	await commands.get("op:status")!.handler("", ctx);
	report = lastReport();
	eq("/op:status emits a report entry", report.command, "/op:status");
	check("/op:status falls back to ledger current_task", report.headline.startsWith("selftest-alpha"), report.headline);
	check(
		"/op:status passes --task explicitly on every task-scoped call",
		report.invocations.filter((i) => /task-show|claim-list|session-list/.test(i)).every((i) => /--id |--task /.test(i)),
		report.invocations.join(" | "),
	);
	check(
		"/op:status never emits a lifecycle flag",
		report.invocations.every((i) => !i.includes("--status") && !i.includes("--verified-by")),
	);

	await commands.get("op:roadmap")!.handler("", ctx);
	report = lastReport();
	eq("/op:roadmap emits a report entry", report.command, "/op:roadmap");
	check("/op:roadmap shows the implementation ladder", report.lines.some((l) => l.includes("Implementation ladder")));
	check("/op:roadmap shows future features", report.lines.some((l) => l.includes("POE-FUT-009") || l.includes("Recommended next feature slices")));
	check("/op:roadmap is read-only", report.invocations.every((i) => !/task-use|claim-add|evidence-attach|handoff-add|review-delegate/.test(i)), report.invocations.join(" | "));

	const notificationsBeforeNextSteps = notifications.length;
	const agentBeforeNextSteps = agentMessages.length;
	await commands.get("op:next-steps")!.handler("", ctx);
	report = lastReport();
	eq("/op:next-steps emits a report entry", report.command, "/op:next-steps");
	check("/op:next-steps shows recommendations", report.lines.some((l) => l.includes("Recommended next steps")));
	check("/op:next-steps is read-only", report.invocations.every((i) => !/task-use|claim-add|evidence-attach|handoff-add|review-delegate/.test(i)), report.invocations.join(" | "));
	check("/op:next-steps distinguishes approval vs advisory vs uid-isolated", report.lines.some((l) => l.includes("Approval / user acceptance")) && report.lines.some((l) => l.includes("Advisory review")) && report.lines.some((l) => l.includes("UID-isolated verification")));
	check("/op:next-steps default does not open chooser", !notifications.slice(notificationsBeforeNextSteps).some(([, m]) => m.includes("Selected next step:")), notifications.slice(notificationsBeforeNextSteps).map((n) => n.join(":")).join(" | "));
	check("/op:next-steps sends action text to agent context", agentMessages.length === agentBeforeNextSteps + 1 && (agentMessages[agentMessages.length - 1]?.content ?? "").includes("Recommended next steps"));
	eq("/op:next-steps agent delivery is nextTurn", agentMessages[agentMessages.length - 1]?.deliverAs, "nextTurn");
	eq("/op:next-steps agent customType", agentMessages[agentMessages.length - 1]?.customType, "operator-orientation");
	selectQueue.push("1. Current ledger next_action: test");
	await commands.get("op:next-steps")!.handler("popup", ctx);
	check("/op:next-steps popup is opt-in", notifications.some(([, m]) => m.includes("Selected next step:")));

	await commands.get("op:next-steps")!.handler("engineering-trust", ctx);
	report = lastReport();
	check("/op:next-steps engineering-trust guidance is present", report.lines.some((l) => l.includes("Workflow guidance (engineering-trust)")));
	check("/op:next-steps engineering-trust does not treat acceptance as verification", report.lines.some((l) => l.includes("User acceptance cannot substitute")));

	await commands.get("op:project")!.handler("", ctx);
	report = lastReport();
	eq("/op:project without prefix is explicit", report.headline, "prefix required");
	await commands.get("op:project")!.handler("selftest", ctx);
	report = lastReport();
	eq("/op:project emits a report entry", report.command, "/op:project");
	check("/op:project lists multiple selftest tasks", report.lines.some((l) => l.includes("selftest-alpha")) && report.lines.some((l) => l.includes("selftest-beta")));
	check("/op:project labels grouping as not a phase order", report.lines.some((l) => /not a project phase order/i.test(l)));
	check("/op:project is read-only", report.invocations.every((i) => !/task-use|claim-add|evidence-attach|handoff-add|review-delegate/.test(i)), report.invocations.join(" | "));
	check("/op:project sends dashboard text to agent context", agentMessages.some((m) => m.customType === "operator-orientation" && m.content.includes("Operator project dashboard")));

	await commands.get("op:roadmap")!.handler("--project selftest", ctx);
	report = lastReport();
	eq("/op:roadmap --project reuses the dashboard", report.command, "/op:project");
	check("/op:roadmap --project lists the prefix", report.lines.some((l) => l.includes("Project prefix: selftest")));


	// The load-bearing one: declining the confirmation must not write the ledger.
	confirmAnswer = false;
	await commands.get("op:use")!.handler("selftest-beta", ctx);
	report = lastReport();
	eq("/op:use selects for the session", report.headline, "selftest-beta (this pi session only)");
	eq(
		"declining the confirmation leaves current_task untouched",
		core.readLedgerCurrentTask(ledger),
		"selftest-alpha",
	);
	check("/op:use says the ledger was left alone", report.lines.some((l) => l.includes("Declined")));

	// /op:status must now follow the session selection, not the ledger.
	await commands.get("op:status")!.handler("", ctx);
	report = lastReport();
	check("/op:status follows the session selection", report.headline.startsWith("selftest-beta"), report.headline);
	check(
		"/op:status still shows the ledger value alongside it",
		report.lines.some((l) => l.includes("Ledger current_task: selftest-alpha")),
	);

	// Confirming does write, through task-use and nothing else.
	confirmAnswer = true;
	await commands.get("op:use")!.handler("selftest-beta", ctx);
	report = lastReport();
	eq("confirming writes current_task", core.readLedgerCurrentTask(ledger), "selftest-beta");
	eq("the write went through task-use", report.invocations, ["./operator task-use selftest-beta"]);

	// Unknown and malformed ids fail closed without touching the ledger.
	const before = core.readLedgerCurrentTask(ledger);
	confirmAnswer = true;
	await commands.get("op:use")!.handler("selftest-nonexistent", ctx);
	eq("an unknown task id does not change current_task", core.readLedgerCurrentTask(ledger), before);
	check(
		"an unknown task id is reported as an error",
		notifications.some(([level, m]) => level === "error" && m.includes("selftest-nonexistent")),
	);
	await commands.get("op:use")!.handler("--all", ctx);
	eq("a flag-shaped task id does not change current_task", core.readLedgerCurrentTask(ledger), before);

	// The chooser path.
	selectAnswer = "selftest-alpha  [assigned]  assigned:claude  V:0 Q:0 O:0";
	confirmAnswer = false;
	await commands.get("op:use")!.handler("", ctx);
	report = lastReport();
	eq("the chooser selects the picked task", report.headline, "selftest-alpha (this pi session only)");

	// --- step 2 authoring writes, driven through the real handlers -----------
	// Point the session at the unused fixture task so these writes are isolated
	// from the records tier A2 already created on selftest-alpha.
	selectAnswer = undefined;
	selectQueue.length = 0;
	inputQueue.length = 0;
	confirmAnswer = false;
	await commands.get("op:use")!.handler("selftest-beta", ctx);
	eq("step 2 tests run against selftest-beta", core.readLedgerCurrentTask(ledger), "selftest-beta");

	const claimsDir = join(ledger.ledgerDir, "claims");
	const evidenceDir = join(ledger.ledgerDir, "evidence", "selftest-beta");
	const handoffsDir = join(ledger.ledgerDir, "handoffs", "selftest-beta");
	const expectedBy = "pi-01a05bf2";

	sessionIdValue = "";
	const claimsBeforeMissingBy = yamlNames(claimsDir);
	await commands.get("op:claim")!.handler("should not land", ctx);
	eq("a missing session id writes no claim", yamlNames(claimsDir), claimsBeforeMissingBy);
	check(
		"a missing session id is reported as an error",
		notifications.some(([level, m]) => level === "error" && m.includes("session-scoped --by")),
	);
	sessionIdValue = "01a05bf2-9c1e-7a2b-8000-0123456789ab";

	selectQueue.push("file_exists");
	editorFn = () => "Step 2 claim/evidence/handoff commands exist";
	inputQueue.push(".pi/extensions/operator/index.ts", "ls .pi/extensions/operator/");
	confirmAnswer = false;
	const claimsBeforeDecline = yamlNames(claimsDir);
	await commands.get("op:claim")!.handler("", ctx);
	report = lastReport();
	eq("declining /op:claim writes no claim", yamlNames(claimsDir), claimsBeforeDecline);
	eq("declining /op:claim reports nothing written", report.headline, "nothing written");
	check("declining /op:claim marks the invocation as not run", report.invocations[0]?.endsWith("(not run)") === true);

	selectQueue.push("file_exists");
	editorFn = () => "Step 2 claim/evidence/handoff commands exist";
	inputQueue.push(".pi/extensions/operator/index.ts", "ls .pi/extensions/operator/");
	confirmAnswer = true;
	await commands.get("op:claim")!.handler("", ctx);
	report = lastReport();
	eq("/op:claim emits a report entry", report.command, "/op:claim");
	check("/op:claim records a claim id", /^claim-[0-9]+ on selftest-beta$/.test(report.headline), report.headline);
	const writtenClaimId = report.headline.split(" ")[0];
	const claimYaml = readFileSync(join(claimsDir, `${writtenClaimId}.yaml`), "utf8");
	check("/op:claim writes session-derived made_by", claimYaml.includes(`made_by: ${expectedBy}`), claimYaml);
	check("/op:claim leaves the claim unverified", /verification_status:\s*false/.test(claimYaml), claimYaml);
	check("/op:claim names --task explicitly", report.invocations.some((i) => i.includes("--task selftest-beta")));
	check(
		"/op:claim emits no lifecycle flag",
		report.invocations.every((i) => !/--status\b|--verified-by\b|--verdict\b/.test(i)),
		report.invocations.join(" | "),
	);
	check("/op:claim says nothing was verified", report.lines.some((l) => l.includes("Nothing here verifies anything")));

	const betaLog = join(ledger.root, "beta.log");
	writeFileSync(betaLog, "step 2 evidence\n");
	selectAnswer = undefined;
	editorFn = () => undefined;
	selectQueue.length = 0;
	inputQueue.length = 0;
	selectQueue.push(writtenClaimId, "run_log");
	inputQueue.push("./operator doctor", "fixture run");
	confirmAnswer = false;
	eq("no evidence dir exists on selftest-beta yet", yamlNames(evidenceDir), []);
	await commands.get("op:evidence")!.handler(betaLog, ctx);
	report = lastReport();
	eq("declining /op:evidence writes no evidence", yamlNames(evidenceDir), []);
	eq("declining /op:evidence reports nothing written", report.headline, "nothing written");

	selectQueue.push(writtenClaimId, "run_log");
	inputQueue.push("./operator doctor", "fixture run");
	confirmAnswer = true;
	await commands.get("op:evidence")!.handler(betaLog, ctx);
	report = lastReport();
	eq("/op:evidence emits a report entry", report.command, "/op:evidence");
	check("/op:evidence records an evidence id", /^evidence-[0-9]+ on selftest-beta$/.test(report.headline), report.headline);
	const writtenEvidenceId = report.headline.split(" ")[0];
	const evidenceYaml = readFileSync(join(evidenceDir, `${writtenEvidenceId}.yaml`), "utf8");
	check("/op:evidence writes session-derived produced_by", evidenceYaml.includes(`produced_by: ${expectedBy}`), evidenceYaml);
	check("/op:evidence records the verify command", evidenceYaml.includes("verification_command: ./operator doctor"), evidenceYaml);
	const claimAfterEvidence = readFileSync(join(claimsDir, `${writtenClaimId}.yaml`), "utf8");
	check("/op:evidence does not verify the claim", /verification_status:\s*false/.test(claimAfterEvidence), claimAfterEvidence);
	check(
		"/op:evidence emits no lifecycle flag",
		report.invocations.every((i) => !/--status\b|--verified-by\b|--verdict\b/.test(i)),
		report.invocations.join(" | "),
	);
	check("/op:evidence names --task explicitly", report.invocations.some((i) => i.includes("--task selftest-beta")));
	check("/op:evidence names --claim", report.invocations.some((i) => i.includes(`--claim ${writtenClaimId}`)));

	selectQueue.push(writtenClaimId, "run_log");
	inputQueue.push("");
	confirmAnswer = true;
	const evidenceBeforeEmptyVerify = yamlNames(evidenceDir);
	await commands.get("op:evidence")!.handler(betaLog, ctx);
	eq("empty verify-cmd writes no evidence", yamlNames(evidenceDir), evidenceBeforeEmptyVerify);
	check(
		"empty verify-cmd is refused",
		notifications.some(([, m]) => m.includes("without a rerunnable --verify-cmd")),
	);

	editorFn = () => {
		throw new Error("default /op:handoff should not open an editor");
	};
	confirmAnswer = true;
	eq("no handoff dir exists on selftest-beta yet", yamlNames(handoffsDir), []);
	await commands.get("op:handoff")!.handler("", ctx);
	report = lastReport();
	check("default /op:handoff writes a generated handoff", yamlNames(handoffsDir).length === 1, yamlNames(handoffsDir).join(","));
	check("default /op:handoff is not recorded as literal next_action", !readFileSync(join(handoffsDir, yamlNames(handoffsDir)[0]!), "utf8").includes("next_action: go"));

	editorFn = () => "## Something Else\ntext\n";
	const handoffsBeforeEmpty = yamlNames(handoffsDir);
	await commands.get("op:handoff")!.handler("edit", ctx);
	eq("an empty edited handoff is refused before spawning", yamlNames(handoffsDir), handoffsBeforeEmpty);
	check(
		"an empty handoff is refused before spawning",
		notifications.some(([, m]) => m.includes("empty handoff")),
	);

	editorFn = () => core.buildHandoffTemplate("selftest-beta", expectedBy, {
		"--changed": "Added the step 2 commands.",
		"--next-action": "Ask a distinct identity to verify.",
	});
	confirmAnswer = false;
	const handoffsBeforeDecline = yamlNames(handoffsDir);
	await commands.get("op:handoff")!.handler("edit", ctx);
	report = lastReport();
	eq("declining /op:handoff writes no handoff", yamlNames(handoffsDir), handoffsBeforeDecline);
	eq("declining /op:handoff reports nothing written", report.headline, "nothing written");

	confirmAnswer = true;
	await commands.get("op:handoff")!.handler("edit", ctx);
	report = lastReport();
	eq("/op:handoff emits a report entry", report.command, "/op:handoff");
	check("/op:handoff records a handoff id", /^handoff-[0-9]+ on selftest-beta$/.test(report.headline), report.headline);
	const writtenHandoffId = report.headline.split(" ")[0];
	const handoffYaml = readFileSync(join(handoffsDir, `${writtenHandoffId}.yaml`), "utf8");
	check("/op:handoff writes session-derived by", handoffYaml.includes(`by: ${expectedBy}`), handoffYaml);
	check("/op:handoff records the edited prose", handoffYaml.includes("Added the step 2 commands."), handoffYaml);
	check("/op:handoff names --task explicitly", report.invocations.some((i) => i.includes("--task selftest-beta")));
	check(
		"/op:handoff emits no lifecycle flag",
		report.invocations.every((i) => !/--status\b|--verified-by\b|--verdict\b/.test(i)),
		report.invocations.join(" | "),
	);

	// --- step 3 supervisor-review, driven through the real handler -----------
	const reviewDir = join(ledger.ledgerDir, "review_delegations");
	const reviewYamlNames = (): string[] => yamlNames(reviewDir);
	selectAnswer = undefined;
	selectQueue.length = 0;
	inputQueue.length = 0;

	selectQueue.push("codex", core.REVIEW_MODE_OPTIONS[1]);
	confirmAnswer = false;
	const reviewsBeforeDecline = reviewYamlNames();
	await commands.get("op:supervisor-review")!.handler(writtenClaimId, ctx);
	report = lastReport();
	eq("declining /op:supervisor-review writes no bundle", reviewYamlNames(), reviewsBeforeDecline);
	eq("declining /op:supervisor-review reports nothing written", report.headline, "nothing written");
	check(
		"declining /op:supervisor-review marks the invocation as not run",
		report.invocations[0]?.endsWith("(not run)") === true,
	);

	await commands.get("op:supervisor-review")!.handler("claim-x", ctx);
	check(
		"a malformed claim id is refused",
		notifications.some(([, m]) => m.includes("expected claim-NNNN")),
	);

	const reviewsBeforeForeign = reviewYamlNames();
	await commands.get("op:supervisor-review")!.handler("claim-0001", ctx);
	eq("a claim from another task writes no bundle", reviewYamlNames(), reviewsBeforeForeign);
	check(
		"a claim from another task is refused",
		notifications.some(([, m]) => m.includes("is not on task selftest-beta")),
	);

	writeFileSync(join(ledger.ledgerDir, "harnesses", `${expectedBy}.yaml`), `harness_id: ${expectedBy}\nkind: pi\n`);
	selectQueue.length = 0;
	selectQueue.push(expectedBy);
	const reviewsBeforeSelf = reviewYamlNames();
	await commands.get("op:supervisor-review")!.handler(writtenClaimId, ctx);
	eq("self-review writes no bundle", reviewYamlNames(), reviewsBeforeSelf);
	check(
		"self-review is refused",
		notifications.some(([, m]) => m.includes("never reuses the current agent")),
	);

	const bareClaim = op(ledger.root, [
		"claim-add",
		"--task",
		"selftest-beta",
		"--type",
		"file_exists",
		"--text",
		"no verify command",
		"--by",
		expectedBy,
	]);
	eq("bare claim-add for missing verify-cmd exits 0", bareClaim.code, 0);
	const bareClaimId = core.parseRecordId(bareClaim.stdout, "claim");
	selectQueue.length = 0;
	inputQueue.length = 0;
	inputQueue.push("");
	const reviewsBeforeBare = reviewYamlNames();
	await commands.get("op:supervisor-review")!.handler(bareClaimId!, ctx);
	eq("missing verify-cmd writes no bundle", reviewYamlNames(), reviewsBeforeBare);
	check(
		"missing verify-cmd gets a default review command",
		notifications.some(([, m]) => m.includes("defaulting review command to ./operator doctor")),
	);

	selectQueue.length = 0;
	inputQueue.length = 0;
	selectQueue.push("codex", core.REVIEW_MODE_OPTIONS[0]);
	inputQueue.push("");
	const reviewsBeforeNoUser = reviewYamlNames();
	await commands.get("op:supervisor-review")!.handler(writtenClaimId, ctx);
	eq("uid-isolated without review-user writes no bundle", reviewYamlNames(), reviewsBeforeNoUser);
	check(
		"uid-isolated without review-user is refused",
		notifications.some(([, m]) => m.includes("without --review-user")),
	);

	selectQueue.length = 0;
	inputQueue.length = 0;
	selectQueue.push("codex", core.REVIEW_MODE_OPTIONS[1]);
	confirmAnswer = true;
	await commands.get("op:supervisor-review")!.handler(writtenClaimId, ctx);
	report = lastReport();
	eq("/op:supervisor-review emits a report entry", report.command, "/op:supervisor-review");
	check(
		"/op:supervisor-review records a bundle",
		report.headline.includes(writtenClaimId) && report.headline.includes("advisory-agent"),
		report.headline,
	);
	check("/op:supervisor-review names --task explicitly", report.invocations.some((i) => i.includes("--task selftest-beta")));
	check("/op:supervisor-review names --reviewer", report.invocations.some((i) => i.includes("--reviewer") && i.includes("codex")));
	check("/op:supervisor-review names the claim", report.invocations.some((i) => i.includes(writtenClaimId)));
	check(
		"/op:supervisor-review emits no lifecycle flag",
		report.invocations.every((i) => !/--status\b|--verified-by\b|--verdict\b/.test(i)),
		report.invocations.join(" | "),
	);
	check("/op:supervisor-review says it does not verify", report.lines.some((l) => l.includes("does not verify")));
	check(
		"/op:supervisor-review distinguishes evidence kinds",
		report.lines.some((l) => l.includes("Verifier-owned status-setting evidence")),
	);
	const newBundles = reviewYamlNames().filter((n) => !reviewsBeforeNoUser.includes(n));
	eq("advisory supervisor-review wrote one yaml bundle", newBundles.length, 1);
	const writtenBundle = readFileSync(join(reviewDir, newBundles[0]), "utf8");
	check("the handler-written bundle is advisory", writtenBundle.includes("expected_verification_authority: advisory"), writtenBundle);
	check("the handler-written bundle names the claim", writtenBundle.includes(`claim_id: ${writtenClaimId}`), writtenBundle);
	check("the handler-written bundle names the explicit reviewer", writtenBundle.includes("reviewer: codex"), writtenBundle);
	const claimAfterReview = readFileSync(join(claimsDir, `${writtenClaimId}.yaml`), "utf8");
	check(
		"/op:supervisor-review does not verify the claim",
		/verification_status:\s*false/.test(claimAfterReview),
		claimAfterReview,
	);

	selectQueue.length = 0;
	inputQueue.length = 0;
	selectQueue.push("codex", core.REVIEW_MODE_OPTIONS[0]);
	inputQueue.push("nobody");
	confirmAnswer = true;
	await commands.get("op:supervisor-review")!.handler(writtenClaimId, ctx);
	report = lastReport();
	check(
		"/op:supervisor-review uid-isolated records a bundle",
		report.headline.includes("uid-isolated"),
		report.headline,
	);
	check("/op:supervisor-review uid-isolated names --review-user", report.invocations.some((i) => i.includes("--review-user") && i.includes("nobody")));
	check(
		"/op:supervisor-review uid-isolated does not run sudo itself",
		report.lines.some((l) => l.includes("not executed by this extension") || l.includes("Human-auth next step")),
	);
	// review-delegate ids are second-resolution, so a fast follow-up can overwrite
	// the advisory yaml with the same filename. Assert the trusted-path contents.
	const isolatedMatch = reviewYamlNames().filter((n) => {
		const text = readFileSync(join(reviewDir, n), "utf8");
		return (
			text.includes(`claim_id: ${writtenClaimId}`) &&
			text.includes("mode: uid-isolated") &&
			text.includes("review_user: nobody")
		);
	});
	check("uid-isolated supervisor-review left a uid-isolated bundle", isolatedMatch.length >= 1, isolatedMatch.join(","));
	if (isolatedMatch.length >= 1) {
		const isolatedBundle = readFileSync(join(reviewDir, isolatedMatch[0]), "utf8");
		check("the uid-isolated bundle names review_user", isolatedBundle.includes("review_user: nobody"), isolatedBundle);
		check("the uid-isolated bundle is not a silent advisory fallback", isolatedBundle.includes("mode: uid-isolated"), isolatedBundle);
	}

	// --- step 4 delegate, driven through the real handler --------------------
	selectAnswer = undefined;
	selectQueue.length = 0;
	inputQueue.length = 0;
	editorFn = () => undefined;
	const alphaTaskPath = join(ledger.ledgerDir, "tasks", "selftest-alpha.yaml");
	const parentAssignedBefore = readFileSync(alphaTaskPath, "utf8");
	const tasksBeforeDelegate = yamlNames(join(ledger.ledgerDir, "tasks"));

	inputQueue.push("selftest-alpha-via-codex");
	editorFn = () => "Bounded child from the handler decline path.";
	selectQueue.push(core.DELEGATE_DISPATCH_OPTIONS[1]);
	confirmAnswer = false;
	await commands.get("op:delegate")!.handler("selftest-alpha grok", ctx);
	report = lastReport();
	eq("declining /op:delegate writes no child task", yamlNames(join(ledger.ledgerDir, "tasks")), tasksBeforeDelegate);
	eq("declining /op:delegate reports nothing written", report.headline, "nothing written");
	eq(
		"declining /op:delegate leaves parent assigned_harness untouched",
		readFileSync(alphaTaskPath, "utf8"),
		parentAssignedBefore,
	);

	await commands.get("op:delegate")!.handler("selftest-dual claude", ctx);
	check(
		"dual assigned+review target is refused",
		notifications.some(([, m]) => m.includes("both assigned_harness and review_harness")),
	);
	eq("refusing dual-role writes no extra task", yamlNames(join(ledger.ledgerDir, "tasks")), tasksBeforeDelegate);

	await commands.get("op:delegate")!.handler("not-a-target", ctx);
	check(
		"an unknown alias is refused",
		notifications.some(([, m]) => m.includes("not a task record") || m.includes("not a configured target alias")),
	);

	selectQueue.length = 0;
	inputQueue.length = 0;
	inputQueue.push("selftest-beta-via-grok");
	editorFn = () => "Bounded grok implementation from selftest-beta via /op:delegate.";
	selectQueue.push(core.DELEGATE_DISPATCH_OPTIONS[1]);
	confirmAnswer = true;
	const betaBefore = readFileSync(join(ledger.ledgerDir, "tasks", "selftest-beta.yaml"), "utf8");
	await commands.get("op:delegate")!.handler("selftest-beta grok", ctx);
	report = lastReport();
	eq("/op:delegate emits a report entry", report.command, "/op:delegate");
	check("/op:delegate names the paste fallback", report.headline.includes("fallback") && report.headline.includes("grok"), report.headline);
	check("the handler created the child task", core.taskRecordExists(ledger, "selftest-beta-via-grok"));
	const childFromHandler = readFileSync(join(ledger.ledgerDir, "tasks", "selftest-beta-via-grok.yaml"), "utf8");
	check("the handler child is assigned grok", childFromHandler.includes("assigned_harness: grok"), childFromHandler);
	const betaAfter = readFileSync(join(ledger.ledgerDir, "tasks", "selftest-beta.yaml"), "utf8");
	check("selftest-beta assigned_harness remains pi", betaAfter.includes("assigned_harness: pi"), betaAfter);
	check("the handler did not rewrite parent selftest-beta assigned_harness", /assigned_harness:\s*pi/.test(betaAfter) && /assigned_harness:\s*pi/.test(betaBefore));
	check(
		"/op:delegate names task-create --assign",
		report.invocations.some((i) => i.includes("task-create") && i.includes("--assign") && i.includes("grok")),
	);
	check(
		"/op:delegate names session-start --task on the child",
		report.invocations.some((i) => i.includes("session-start") && i.includes("--task selftest-beta-via-grok") && i.includes("--harness grok")),
	);
	check(
		"/op:delegate emits no lifecycle flag",
		report.invocations.every((i) => !/--status\b|--verified-by\b|--verdict\b/.test(i)),
		report.invocations.join(" | "),
	);
	check("/op:delegate says parent routing is unchanged", report.lines.some((l) => l.includes("routing is unchanged")));
	check("/op:delegate labels paste as fallback", report.lines.some((l) => /LABELED FALLBACK|paste\/export/i.test(l)));
	check("the child export brief exists", existsSync(join(ledger.ledgerDir, "briefs", "selftest-beta-via-grok.grok.export.md")));
	selectQueue.length = 0;
	selectQueue.push(core.DELEGATE_DISPATCH_OPTIONS[1]);
	confirmAnswer = false;
	const tasksBeforeParentDecline = yamlNames(join(ledger.ledgerDir, "tasks"));
	await commands.get("op:delegate")!.handler("selftest-alpha claude", ctx);
	report = lastReport();
	eq("declining parent-routed /op:delegate writes no extra task", yamlNames(join(ledger.ledgerDir, "tasks")), tasksBeforeParentDecline);
	eq("declining parent-routed /op:delegate reports nothing written", report.headline, "nothing written");

	selectQueue.length = 0;
	confirmAnswer = false;
	await commands.get("op:popup")!.handler("credentials", ctx);
	report = lastReport();
	eq("/op:popup decline is /op:popup", report.command, "/op:popup");
	eq("declining /op:popup executes nothing", report.headline, "nothing executed");
	check("declining /op:popup marks sudo as not run", report.invocations[0]?.endsWith("(not run)") === true);
	check("declining /op:popup does not verify", report.lines.some((l) => l.toLowerCase().includes("password") || l.includes("not touched")));
	integrationCoverage.tierC = true;
}

// --- main --------------------------------------------------------------------

async function main(): Promise<void> {
	if (!existsSync(OPERATOR)) {
		console.error(`operator CLI not found at ${OPERATOR}`);
		process.exit(2);
	}
	console.log(`repo:    ${REPO_ROOT}`);
	console.log(`fixture: ${fixture}`);
	check(
		"pi-server skip matcher requires the optional-package miss",
		isMissingOptionalPiServer(new Error("Cannot find package '@earendil-works/pi-server' imported from /x")),
	);
	check(
		"pi-server skip matcher ignores unrelated errors that mention pi-server",
		!isMissingOptionalPiServer(new Error("TypeError: pi-server returned 500")),
	);
	const ledger = buildFixture();
	tierA(ledger);
	tierAContract(ledger);
	tierA2(ledger);
	tierA3(ledger);
	tierA4(ledger);
	tierA5();
	await tierAClient(ledger);
	const piPackage = findPiPackage();
	console.log(`\npi package: ${piPackage ?? "(not found)"}`);
	let piServerFixture: string | null = null;
	try {
		piServerFixture = installIsolatedPiServerImportFixture();
	} catch (err) {
		console.log(`pi-server import fixture failed to register: ${errorText(err)}`);
	}
	if (piServerFixture) {
		console.log(
			`pi-server import fixture: ${piServerFixture} (isolated temp module; real Pi loader; optional package not installed)`,
		);
	} else {
		console.log("pi-server import fixture: unavailable (need node:module.registerHooks)");
	}
	await tierB(piPackage);
	await tierC(piPackage, ledger);

	console.log(`\n${passed} passed, ${failed} failed, ${skips.length} skipped`);
	for (const s of skips) console.log(`  skipped: ${s}`);
	console.log("\nIntegration coverage:");
	console.log(
		`  Tier A-A5 (core unit, throwaway ledger): ${integrationCoverage.tierA ? "executed" : "not executed"}`,
	);
	console.log(
		`  Tier B (pi discoverAndLoadExtensions): ${integrationCoverage.tierB ? "executed" : "not executed"}`,
	);
	console.log(
		`  Tier C (handler e2e with stub UI): ${integrationCoverage.tierC ? "executed" : "not executed"}`,
	);
	process.exit(failed === 0 ? 0 : 1);
}

await main();
