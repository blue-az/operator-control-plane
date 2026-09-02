/**
 * Pure logic for the project-local Operator Pi extension.
 *
 * Nothing here imports pi. This file owns ledger discovery, the fixed argv
 * allowlist for `./operator`, and the parsers for its output, so that the
 * shipped command wiring (index.ts) and the selftest (selftest.ts) exercise
 * exactly the same code.
 *
 * Authority boundary, per owners-manual/pbc/appendix-pi-operator-extension.pbc.md:
 *   POE-RUL-101  ergonomic wrapper only; no alternate ledger or hidden state
 *                that can supersede files under .operator/
 *   POE-RUL-102  --by is session-derived provenance; --verified-by, --for,
 *                --harness and --reviewer are never derived from the session
 *   POE-RUL-104  narrow and fail-closed; no raw arbitrary operator execution
 *   POE-RUL-105  output is terminal output, not evidence
 *   POE-RUL-112  every invocation names its task explicitly
 *   POE-RUL-113  --status / --verified-by / --verdict are never emitted
 *
 * Step 4 of the implementation ladder adds /op:delegate, a chooser-first wrap
 * of task-create --assign (unrouted targets), session-start / brief /
 * export-brief (routed implementer targets), and harness_adapter invocation.
 * Step 1 orientation, step 2 authoring writes, and step 3 supervisor-review
 * stay as they were. The PBC commands and model-callable tools remain absent.
 *
 * Two encoding rules keep user text from ever being read as a flag:
 *   - validated identifiers (task ids, claim ids, enum members, digests) are
 *     passed as a separate token after their flag;
 *   - arbitrary human text is passed inline as --flag=value, which argparse
 *     cannot re-read as an option no matter what the human typed.
 * assertSafeArgv then enforces that every '--' token is a long flag this
 * subcommand is allowed to use, and that no short flag is ever emitted.
 */

import { existsSync, readdirSync, readFileSync, realpathSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

/** Directory name of the ledger, relative to the repository root. */
export const LEDGER_DIR = ".operator";

/** Name of the ledger CLI executable, relative to the repository root. */
export const OPERATOR_BIN = "operator";

/**
 * Subcommands this extension is allowed to invoke at step 4.
 *
 * READ_ONLY never mutates the ledger. CONFIRMED_WRITE mutates it and may only
 * be reached after an explicit user confirmation in index.ts.
 * claim-show is read-only inspection used by /op:supervisor-review so it can
 * require a recorded or supplied verify command without guessing.
 * review-delegate writes a bundle under .operator/review_delegations/; it
 * never verifies.
 * task-create / session-start / brief / export-brief are used only by
 * /op:delegate, and only after confirmation. They are not a raw operator
 * passthrough (POE-RUL-104).
 */
export const READ_ONLY_SUBCOMMANDS = [
	"doctor",
	"task-list",
	"task-show",
	"claim-list",
	"claim-show",
	"session-list",
] as const;
export const CONFIRMED_WRITE_SUBCOMMANDS = [
	"task-use",
	"claim-add",
	"evidence-attach",
	"handoff-add",
	"review-delegate",
	"task-create",
	"session-start",
	"brief",
	"export-brief",
] as const;

export type ReadOnlySubcommand = (typeof READ_ONLY_SUBCOMMANDS)[number];
export type ConfirmedWriteSubcommand = (typeof CONFIRMED_WRITE_SUBCOMMANDS)[number];
export type AllowedSubcommand = ReadOnlySubcommand | ConfirmedWriteSubcommand;

/**
 * Flags that carry lifecycle/verdict authority. The extension must omit them
 * entirely rather than validate them (POE-RUL-113), so they are rejected even
 * if a future edit tries to route one through a builder.
 *
 * Note that handoff-add's --verified is a *prose* field ("what was verified")
 * and is not one of these: only --verified-by names a verifier.
 */
export const FORBIDDEN_FLAGS = ["--status", "--verified-by", "--verified_by", "--verdict"] as const;

/**
 * The long flags each subcommand may carry. This is an allowlist, not a
 * denylist: a flag that is not named here cannot reach argparse even if a
 * future builder tries to pass it. Short flags are refused outright, so
 * evidence-attach's `-v` (an alias for --verdict) has no way in either.
 */
export const ALLOWED_FLAGS: Record<AllowedSubcommand, readonly string[]> = {
	doctor: [],
	"task-list": ["--all", "--filter"],
	"task-show": ["--id"],
	"claim-list": ["--task"],
	"claim-show": ["--id"],
	"session-list": ["--task"],
	"task-use": [],
	"claim-add": ["--task", "--type", "--text", "--by", "--gate", "--verify-cmd", "--layer"],
	"evidence-attach": ["--task", "--claim", "--type", "--by", "--notes", "--verify-cmd", "--hash"],
	"handoff-add": ["--task", "--by", "--changed", "--verified", "--claimed", "--open", "--assumptions", "--next-action"],
	"review-delegate": ["--task", "--reviewer", "--mode", "--review-user", "--verify-cmd"],
	"task-create": ["--id", "--objective", "--assign", "--review"],
	"session-start": ["--task", "--harness"],
	brief: ["--for", "--task"],
	"export-brief": ["--for", "--task"],
};

/** Claim types accepted by `./operator claim-add --type`. */
export const CLAIM_TYPES = [
	"file_exists",
	"test_passes",
	"numeric_measurement",
	"real_data",
	"model_output",
	"firmware_behavior",
	"deployment_state",
	"supervision_credit",
	"paper_or_report_claim",
] as const;

/** Supervision layers; required for supervision_credit claims (FR-12). */
export const SUPERVISION_LAYERS = ["design", "execution", "evidence", "release", "end_to_end"] as const;

/**
 * Evidence types this extension offers.
 *
 * `diff` is in the CLI's enum but deliberately not here: it ignores the
 * positional path and synthesizes a git diff from --diff-base or the task's
 * created_at, which is a different surface with its own base-ref semantics.
 * Attaching one is `./operator evidence-attach --type diff` by hand.
 */
export const EVIDENCE_TYPES = [
	"run_log",
	"test_output",
	"manifest",
	"database_query",
	"git_commit",
	"screenshot",
	"transcript",
	"paper_section",
	"external_doc",
	"session_crystal",
] as const;

export type ClaimType = (typeof CLAIM_TYPES)[number];
export type SupervisionLayer = (typeof SUPERVISION_LAYERS)[number];
export type EvidenceType = (typeof EVIDENCE_TYPES)[number];

/** review-delegate --mode values. The extension never infers one. */
export const REVIEW_MODES = ["uid-isolated", "advisory-agent"] as const;
export type ReviewMode = (typeof REVIEW_MODES)[number];

/**
 * Chooser labels for /op:supervisor-review mode. First token is the mode id.
 * Trusted UID run is listed first so it is not a silent downgrade to advisory.
 */
export const REVIEW_MODE_OPTIONS = [
	"uid-isolated  Trusted verifier UID run (human-authorized; this session cannot verify)",
	"advisory-agent  Same-UID advisory review notes (not trusted verification)",
] as const;

/** Task ids are slugs; anything else is refused before it reaches argparse. */
const TASK_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;

/** Claim ids as minted by get_next_claim_id: claim-0001. */
const CLAIM_ID_RE = /^claim-[0-9]{4,}$/;

/** A bare SHA-256 digest, the only thing --hash may carry. */
const SHA256_RE = /^[0-9a-fA-F]{64}$/;

/** http(s) evidence locators; everything else must be an existing local file. */
const REMOTE_LOCATOR_RE = /^https?:\/\//i;

export interface Ledger {
	/** Repository root holding both the ledger dir and the operator binary. */
	root: string;
	/** Absolute path of the .operator directory. */
	ledgerDir: string;
	/** Absolute path of the operator executable. */
	operatorBin: string;
	/** Absolute path of .operator/operator.yaml. */
	operatorYaml: string;
	/** Absolute path of .operator/tasks. */
	tasksDir: string;
}

/**
 * Walk upward from `startDir` for a directory holding both `.operator/` and an
 * `operator` executable. Fails closed (null) rather than guessing: a ledger
 * without its CLI, or a CLI without its ledger, is not something to wrap.
 */
export function findLedger(startDir: string): Ledger | null {
	let dir = resolve(startDir);
	for (;;) {
		const ledgerDir = join(dir, LEDGER_DIR);
		const operatorBin = join(dir, OPERATOR_BIN);
		if (isDir(ledgerDir) && isFile(operatorBin)) {
			return {
				root: dir,
				ledgerDir,
				operatorBin,
				operatorYaml: join(ledgerDir, "operator.yaml"),
				tasksDir: join(ledgerDir, "tasks"),
			};
		}
		const parent = dirname(dir);
		if (parent === dir) return null;
		dir = parent;
	}
}

function isDir(p: string): boolean {
	try {
		return statSync(p).isDirectory();
	} catch {
		return false;
	}
}

function isFile(p: string): boolean {
	try {
		return statSync(p).isFile();
	} catch {
		return false;
	}
}

export function isValidTaskId(taskId: string): boolean {
	return TASK_ID_RE.test(taskId);
}

export function isValidClaimId(claimId: string): boolean {
	return CLAIM_ID_RE.test(claimId);
}

export function isValidHarnessId(harnessId: string): boolean {
	return TASK_ID_RE.test(harnessId);
}

/** POSIX-ish user names; flag-shaped values are refused. */
const UNIX_USER_RE = /^[A-Za-z_][A-Za-z0-9_.-]*$/;

export function isValidUnixUser(name: string): boolean {
	return UNIX_USER_RE.test(name);
}

/** True when `.operator/tasks/<id>.yaml` exists. Used to fail closed on typos. */
export function taskRecordExists(ledger: Ledger, taskId: string): boolean {
	if (!isValidTaskId(taskId)) return false;
	return existsSync(join(ledger.tasksDir, `${taskId}.yaml`));
}

/**
 * Read `current_task` out of .operator/operator.yaml.
 *
 * This is a read of the ledger's own projection for display. Nothing in this
 * extension *acts* on it: every invocation names its task explicitly
 * (POE-RUL-112).
 */
export function readLedgerCurrentTask(ledger: Ledger): string | null {
	let text: string;
	try {
		text = readFileSync(ledger.operatorYaml, "utf8");
	} catch {
		return null;
	}
	for (const line of text.split("\n")) {
		const m = /^current_task:\s*(.*)$/.exec(line);
		if (!m) continue;
		const raw = m[1].trim().replace(/^['"]|['"]$/g, "");
		if (!raw || raw === "null" || raw === "~") return null;
		return raw;
	}
	return null;
}

/**
 * Last gate before spawn. Every argv reaching ./operator goes through here.
 *
 * Throws rather than returning a flag so a mistake in a builder cannot degrade
 * into a silently weaker invocation.
 */
export function assertSafeArgv(argv: string[]): string[] {
	if (argv.length === 0) throw new Error("refusing to run ./operator with no subcommand");
	const sub = argv[0];
	const allowed: readonly string[] = [...READ_ONLY_SUBCOMMANDS, ...CONFIRMED_WRITE_SUBCOMMANDS];
	if (!allowed.includes(sub)) {
		throw new Error(`refusing to run ./operator ${sub}: not in this extension's allowlist (${allowed.join(", ")})`);
	}
	const flagsHere = ALLOWED_FLAGS[sub as AllowedSubcommand] ?? [];
	for (const arg of argv.slice(1)) {
		for (const forbidden of FORBIDDEN_FLAGS) {
			if (arg === forbidden || arg.startsWith(`${forbidden}=`)) {
				throw new Error(`refusing to pass ${forbidden}: lifecycle authority is not an extension input`);
			}
		}
		if (arg.startsWith("--")) {
			const name = arg.split("=", 1)[0];
			if (!flagsHere.includes(name)) {
				throw new Error(
					`refusing to pass ${name} to ${sub}: not in this subcommand's flag allowlist (${flagsHere.join(", ") || "none"})`,
				);
			}
			continue;
		}
		if (arg.startsWith("-") && arg.length > 1) {
			// Short flags are never emitted, so anything that looks like one is
			// either a bug or a value that would be read as a flag. Both fail closed.
			throw new Error(`refusing to pass '${arg}': the extension emits long-form flags only`);
		}
	}
	return argv;
}

export function isReadOnly(argv: string[]): boolean {
	return (READ_ONLY_SUBCOMMANDS as readonly string[]).includes(argv[0]);
}

// --- argv builders -----------------------------------------------------------
// One builder per surfaced operation. Callers never assemble argv themselves,
// so there is no path from user text to an arbitrary operator command.

export function doctorArgv(): string[] {
	return assertSafeArgv(["doctor"]);
}

export function taskListArgv(opts: { all?: boolean; filter?: string } = {}): string[] {
	const argv = ["task-list"];
	if (opts.all) argv.push("--all");
	if (opts.filter !== undefined && opts.filter !== "") {
		const filter = opts.filter.trim();
		if (filter.startsWith("-")) {
			throw new Error(`refusing filter '${filter}': a filter starting with '-' would be read as a flag`);
		}
		argv.push("--filter", filter);
	}
	return assertSafeArgv(argv);
}

export function taskShowArgv(taskId: string): string[] {
	requireTaskId(taskId, "task-show");
	return assertSafeArgv(["task-show", "--id", taskId]);
}

export function claimListArgv(taskId: string): string[] {
	requireTaskId(taskId, "claim-list");
	return assertSafeArgv(["claim-list", "--task", taskId]);
}

export function sessionListArgv(taskId: string): string[] {
	requireTaskId(taskId, "session-list");
	return assertSafeArgv(["session-list", "--task", taskId]);
}

export function taskUseArgv(taskId: string): string[] {
	requireTaskId(taskId, "task-use");
	return assertSafeArgv(["task-use", taskId]);
}

export function claimShowArgv(claimId: string): string[] {
	requireClaimId(claimId, "claim-show");
	return assertSafeArgv(["claim-show", "--id", claimId]);
}

function requireTaskId(taskId: string, forCommand: string): void {
	if (!isValidTaskId(taskId)) {
		throw new Error(`refusing ${forCommand} with task id '${taskId}': expected [A-Za-z0-9][A-Za-z0-9._-]*`);
	}
}

function requireClaimId(claimId: string, forCommand: string): void {
	if (!isValidClaimId(claimId)) {
		throw new Error(`refusing ${forCommand} with claim id '${claimId}': expected claim-NNNN`);
	}
}

// --- step 2 authoring writes -------------------------------------------------
// claim-add, evidence-attach and handoff-add. Each one names its task
// explicitly (POE-RUL-112), carries a session-derived --by (POE-RUL-102), and
// has no way to reach --status, --verified-by or --verdict (POE-RUL-113).

/**
 * Encode a free-text value as `--flag=value`.
 *
 * The inline form is the point: argparse cannot re-read the value as an option,
 * so a claim text of "--status=verified" stays a claim text. Callers pass
 * identifiers as separate tokens instead, because those are validated.
 */
export function textFlag(flag: string, value: string): string {
	if (!flag.startsWith("--")) throw new Error(`textFlag expects a long flag, got '${flag}'`);
	if (value.includes("\0")) throw new Error(`refusing ${flag}: value contains a NUL byte`);
	return `${flag}=${value}`;
}

/**
 * Derive the `--by` label for this pi session, matching the ledger's existing
 * `<carrier>-<short session id>` provenance convention (claude-e5502c31,
 * pi-01a03792).
 *
 * This is provenance text and nothing else. It confers no authority, it is not
 * a harness id, and it must never be offered as a `--verified-by`
 * (POE-RUL-003, review finding F5).
 */
export function deriveAuthorLabel(sessionId: string | null | undefined, carrier = "pi"): string | null {
	if (!sessionId) return null;
	const short = sessionId.replace(/[^A-Za-z0-9]/g, "").slice(0, 8);
	if (short.length < 4) return null;
	return `${carrier}-${short}`;
}

export interface ClaimAddOptions {
	taskId: string;
	type: string;
	text: string;
	by: string;
	gate?: string;
	verifyCmd?: string;
	layer?: string;
}

export function claimAddArgv(opts: ClaimAddOptions): string[] {
	requireTaskId(opts.taskId, "claim-add");
	if (!(CLAIM_TYPES as readonly string[]).includes(opts.type)) {
		throw new Error(`refusing claim type '${opts.type}': expected one of ${CLAIM_TYPES.join(", ")}`);
	}
	const text = opts.text.trim();
	if (!text) throw new Error("refusing claim-add with empty claim text");
	const by = requireAuthorLabel(opts.by, "claim-add");
	// FR-12: an unnamed layer on a supervision_credit claim is flagged ambiguous
	// by doctor. Refuse here rather than write a record doctor will complain about.
	if (opts.type === "supervision_credit" && !opts.layer) {
		throw new Error("refusing a supervision_credit claim without --layer (doctor flags it as an ambiguous credit, FR-12)");
	}
	const argv = ["claim-add", "--task", opts.taskId, "--type", opts.type, textFlag("--text", text), textFlag("--by", by)];
	const gate = (opts.gate ?? "").trim();
	if (gate) argv.push(textFlag("--gate", gate));
	const verifyCmd = (opts.verifyCmd ?? "").trim();
	if (verifyCmd) argv.push(textFlag("--verify-cmd", verifyCmd));
	if (opts.layer) {
		if (!(SUPERVISION_LAYERS as readonly string[]).includes(opts.layer)) {
			throw new Error(`refusing supervision layer '${opts.layer}': expected one of ${SUPERVISION_LAYERS.join(", ")}`);
		}
		argv.push("--layer", opts.layer);
	}
	return assertSafeArgv(argv);
}

export interface EvidenceAttachOptions {
	taskId: string;
	locator: string;
	type: string;
	by: string;
	/** Required: evidence is attached with a rerunnable command, not a static blob. */
	verifyCmd: string;
	claimId?: string;
	notes?: string;
	hash?: string;
}

export function evidenceAttachArgv(opts: EvidenceAttachOptions): string[] {
	requireTaskId(opts.taskId, "evidence-attach");
	if (!(EVIDENCE_TYPES as readonly string[]).includes(opts.type)) {
		throw new Error(`refusing evidence type '${opts.type}': expected one of ${EVIDENCE_TYPES.join(", ")}`);
	}
	const locator = opts.locator.trim();
	if (!locator) throw new Error("refusing evidence-attach with an empty path or URL");
	if (locator.startsWith("-")) {
		throw new Error(`refusing evidence locator '${locator}': a locator starting with '-' would be read as a flag`);
	}
	const by = requireAuthorLabel(opts.by, "evidence-attach");
	const verifyCmd = (opts.verifyCmd ?? "").trim();
	if (!verifyCmd) {
		throw new Error("refusing evidence-attach without a rerunnable --verify-cmd");
	}
	const argv = [
		"evidence-attach",
		locator,
		"--task",
		opts.taskId,
		"--type",
		opts.type,
		textFlag("--by", by),
		textFlag("--verify-cmd", verifyCmd),
	];
	if (opts.claimId) {
		if (!CLAIM_ID_RE.test(opts.claimId)) {
			throw new Error(`refusing claim id '${opts.claimId}': expected claim-NNNN`);
		}
		argv.push("--claim", opts.claimId);
	}
	const notes = (opts.notes ?? "").trim();
	if (notes) argv.push(textFlag("--notes", notes));
	const hash = (opts.hash ?? "").trim();
	if (hash) {
		if (!SHA256_RE.test(hash)) throw new Error(`refusing --hash '${hash}': expected 64 hex characters`);
		argv.push("--hash", hash.toLowerCase());
	}
	return assertSafeArgv(argv);
}

/** True when the locator is an http(s) URL rather than a local file path. */
export function isRemoteLocator(locator: string): boolean {
	return REMOTE_LOCATOR_RE.test(locator.trim());
}

/**
 * Resolve an evidence locator, failing closed on anything that is neither an
 * http(s) URL nor an existing regular file. Local paths come back absolute so
 * the confirmation dialog shows exactly what will be fingerprinted.
 */
export function resolveEvidenceLocator(ledger: Ledger, raw: string): { locator: string; remote: boolean } {
	const trimmed = raw.trim();
	if (!trimmed) throw new Error("refusing evidence-attach with an empty path or URL");
	if (isRemoteLocator(trimmed)) return { locator: trimmed, remote: true };
	if (trimmed.startsWith("-")) {
		throw new Error(`refusing evidence locator '${trimmed}': a locator starting with '-' would be read as a flag`);
	}
	const abs = resolve(ledger.root, trimmed);
	if (!isFile(abs)) {
		throw new Error(`refusing evidence locator '${trimmed}': ${abs} is not an existing regular file (and is not an http(s) URL)`);
	}
	return { locator: abs, remote: false };
}

/** The six structured fields handoff-add records, in the order the CLI lists them. */
export const HANDOFF_SECTIONS = [
	{ flag: "--changed", heading: "What changed", field: "what_changed" },
	{ flag: "--verified", heading: "What was verified", field: "what_verified" },
	{ flag: "--claimed", heading: "What is claimed (not yet verified)", field: "what_claimed" },
	{ flag: "--open", heading: "What remains open", field: "what_remains_open" },
	{ flag: "--assumptions", heading: "Unchecked assumptions", field: "unchecked_assumptions" },
	{ flag: "--next-action", heading: "Next action", field: "next_action" },
] as const;

export type HandoffDraft = Record<string, string>;

/**
 * The prefill for the /op:handoff editor.
 *
 * Handoff quality depends on prose context, so the editor is the primary
 * surface rather than six separate one-line prompts. Continuity transfer is a
 * mode of handoff, not a separate command: the successor is named under
 * "Next action" (POE-RUL-107, review finding F9).
 */
export function buildHandoffTemplate(taskId: string, by: string, prior?: HandoffDraft): string {
	const lines = [
		`# Handoff for ${taskId}, recorded as --by=${by}.`,
		"# Lines starting with a single '#' are comments and are dropped.",
		"# Leave a section empty to omit it; at least one section must have text.",
		"# Type 'go' as the whole editor contents to accept the generated draft below.",
		"# Continuity transfer is a mode of handoff: name the successor under 'Next action'.",
		"",
	];
	const seed = prior ?? buildGeneratedHandoffDraft(taskId, by);
	for (const section of HANDOFF_SECTIONS) {
		lines.push(`## ${section.heading}`, "", (seed[section.flag] ?? "").trim(), "");
	}
	return `${lines.join("\n").replace(/\n{3,}/g, "\n\n")}\n`;
}

/** Deterministic fallback handoff used when the user says "go". */
export function buildGeneratedHandoffDraft(taskId: string, by: string, taskShow?: TaskShowSummary | null): HandoffDraft {
	const status = taskShow?.fields.Status ? ` Status: ${taskShow.fields.Status}.` : "";
	const rawNext = taskShow?.fields["Next Action"]?.trim();
	const staleSelfTestNext = rawNext && /\/(?:op:)?handoff\s+go\b/i.test(rawNext);
	const next = rawNext && !staleSelfTestNext ? rawNext : undefined;
	const counts = taskShow
		? ` Task currently shows ${taskShow.claims} claim(s), ${taskShow.evidence} evidence item(s), and ${taskShow.handoffs} prior handoff(s).`
		: "";
	return {
		"--changed": `Generated /op:handoff closeout for ${taskId} by ${by}.${status}${counts}`,
		"--verified": "No new verification was performed by this handoff; it records continuity only.",
		"--claimed": "No new product claim is made by this handoff.",
		"--open": "Review the task status, claims, evidence, and latest handoff before proceeding.",
		"--assumptions": staleSelfTestNext
			? "Generated from Operator task context; previous next_action was a completed /op:handoff go dogfood instruction and was not carried forward."
			: "Generated from Operator task context; edit if more specific continuity details are needed.",
		"--next-action": next || "Continue from the current Operator task state.",
	};
}

/**
 * Parse the edited template back into flag -> text. Unknown headings are
 * ignored rather than guessed at, and a body with no recognized heading at all
 * is reported as such by the caller (the returned draft is simply empty).
 */
export function parseHandoffDraft(text: string): HandoffDraft {
	const byHeading = new Map<string, string>();
	for (const section of HANDOFF_SECTIONS) byHeading.set(section.heading.toLowerCase(), section.flag);
	const draft: HandoffDraft = {};
	let current: string | null = null;
	let buffer: string[] = [];
	const flush = () => {
		if (current) {
			const body = buffer.join("\n").trim();
			if (body) draft[current] = body;
		}
		buffer = [];
	};
	for (const line of splitLines(text)) {
		const heading = /^##\s*(.+?)\s*$/.exec(line);
		if (heading) {
			flush();
			current = byHeading.get(heading[1].toLowerCase()) ?? null;
			continue;
		}
		if (/^#(?!#)/.test(line)) continue;
		if (current) buffer.push(line);
	}
	flush();
	return draft;
}

export interface HandoffAddOptions {
	taskId: string;
	by: string;
	draft: HandoffDraft;
}

export function handoffAddArgv(opts: HandoffAddOptions): string[] {
	requireTaskId(opts.taskId, "handoff-add");
	const by = requireAuthorLabel(opts.by, "handoff-add");
	const argv = ["handoff-add", "--task", opts.taskId, textFlag("--by", by)];
	let fields = 0;
	for (const section of HANDOFF_SECTIONS) {
		const body = (opts.draft[section.flag] ?? "").trim();
		if (!body) continue;
		argv.push(textFlag(section.flag, body));
		fields += 1;
	}
	// handoff-add reads YAML from stdin when it gets no field flags, which would
	// leave the spawned process waiting on a descriptor pi does not drive. The
	// CLI also rejects an empty handoff outright; refuse before spawning either way.
	if (fields === 0) {
		throw new Error("refusing an empty handoff: fill in at least one section");
	}
	return assertSafeArgv(argv);
}

function requireAuthorLabel(by: string, forCommand: string): string {
	const label = (by ?? "").trim();
	if (!label) {
		throw new Error(`refusing ${forCommand} without a session-derived --by label`);
	}
	if (!TASK_ID_RE.test(label)) {
		throw new Error(`refusing --by '${label}': expected [A-Za-z0-9][A-Za-z0-9._-]*`);
	}
	return label;
}

// --- step 3 supervisor-review ------------------------------------------------
// Wraps ./operator review-delegate. One named claim, explicit reviewer, a
// recorded or supplied verify command, fail-closed under broker enrollment.
// Never emits lifecycle flags, never attaches evidence, never verifies.

export interface ReviewDelegateOptions {
	claimId: string;
	taskId: string;
	reviewer: string;
	mode: string;
	verifyCmd: string;
	reviewUser?: string;
}

/**
 * Refuse using this session's author label as the reviewer.
 *
 * --reviewer is a harness id; the session label is provenance. They live on
 * different axes (POE-RUL-003), and supervisor-review never reuses the
 * current agent (POE-RUL-102).
 */
export function refuseSelfReview(reviewer: string, sessionAuthor: string | null | undefined): void {
	const who = (sessionAuthor ?? "").trim();
	if (who && reviewer === who) {
		throw new Error(
			`refusing reviewer '${reviewer}': that is this session's author label; supervisor-review never reuses the current agent (POE-RUL-102)`,
		);
	}
}

export function reviewDelegateArgv(opts: ReviewDelegateOptions): string[] {
	requireClaimId(opts.claimId, "review-delegate");
	requireTaskId(opts.taskId, "review-delegate");
	const reviewer = (opts.reviewer ?? "").trim();
	if (!reviewer) {
		throw new Error(
			"refusing review-delegate without an explicit --reviewer (review_harness is routing metadata only)",
		);
	}
	if (!isValidHarnessId(reviewer)) {
		throw new Error(
			`refusing --reviewer '${reviewer}': expected a harness id like [A-Za-z0-9][A-Za-z0-9._-]*`,
		);
	}
	if (!(REVIEW_MODES as readonly string[]).includes(opts.mode)) {
		throw new Error(`refusing review mode '${opts.mode}': expected one of ${REVIEW_MODES.join(", ")}`);
	}
	const verifyCmd = (opts.verifyCmd ?? "").trim();
	if (!verifyCmd) {
		throw new Error(
			"refusing review-delegate without a verification command; provide --verify-cmd (required_gate is an artifact path, not a command)",
		);
	}
	const argv = [
		"review-delegate",
		opts.claimId,
		"--task",
		opts.taskId,
		"--reviewer",
		reviewer,
		"--mode",
		opts.mode,
		textFlag("--verify-cmd", verifyCmd),
	];
	if (opts.mode === "uid-isolated") {
		const user = (opts.reviewUser ?? "").trim();
		if (!user) {
			throw new Error(
				"refusing uid-isolated review-delegate without --review-user; trusted verification needs a visible human-auth path, not a placeholder",
			);
		}
		if (!isValidUnixUser(user)) {
			throw new Error(`refusing --review-user '${user}': expected a Unix user name`);
		}
		argv.push("--review-user", user);
	} else if ((opts.reviewUser ?? "").trim()) {
		throw new Error(
			"refusing --review-user on advisory-agent review-delegate: that flag is the trusted uid-isolated auth path",
		);
	}
	return assertSafeArgv(argv);
}

export function claimRecordExists(ledger: Ledger, claimId: string): boolean {
	if (!isValidClaimId(claimId)) return false;
	return existsSync(join(ledger.ledgerDir, "claims", `${claimId}.yaml`));
}

export function harnessRecordExists(ledger: Ledger, harnessId: string): boolean {
	if (!isValidHarnessId(harnessId)) return false;
	return existsSync(join(ledger.ledgerDir, "harnesses", `${harnessId}.yaml`));
}

export function listHarnessIds(ledger: Ledger): string[] {
	try {
		return readdirSync(join(ledger.ledgerDir, "harnesses"))
			.filter((name) => name.endsWith(".yaml"))
			.map((name) => name.slice(0, -".yaml".length))
			.filter((id) => isValidHarnessId(id))
			.sort();
	} catch {
		return [];
	}
}

export function listClaimIds(ledger: Ledger): string[] {
	try {
		return readdirSync(join(ledger.ledgerDir, "claims"))
			.filter((name) => name.endsWith(".yaml"))
			.map((name) => name.slice(0, -".yaml".length))
			.filter((id) => isValidClaimId(id))
			.sort();
	} catch {
		return [];
	}
}

export interface IdentityUid {
	uid: number;
	name: string;
	roles: string[];
}

export interface IdentityPolicy {
	mode: string;
	uids: IdentityUid[];
}

/**
 * Parse the small identity.yaml shape this repo uses. Fail soft (empty uids)
 * rather than inventing roles: hints are optional, authority is not.
 */
export function parseIdentityPolicy(text: string): IdentityPolicy {
	let mode = "single_user";
	const uids: IdentityUid[] = [];
	let current: IdentityUid | null = null;
	let inRoles = false;
	for (const line of splitLines(text)) {
		const modeMatch = /^mode:\s*(\S+)/.exec(line);
		if (modeMatch) {
			mode = modeMatch[1].replace(/^['"]|['"]$/g, "");
			continue;
		}
		const uidMatch = /^ {2}(\d+):\s*$/.exec(line);
		if (uidMatch) {
			if (current) uids.push(current);
			current = { uid: Number(uidMatch[1]), name: "", roles: [] };
			inRoles = false;
			continue;
		}
		if (!current) continue;
		const nameMatch = /^\s+name:\s*(.+)$/.exec(line);
		if (nameMatch) {
			current.name = nameMatch[1].trim().replace(/^['"]|['"]$/g, "");
			inRoles = false;
			continue;
		}
		if (/^\s+roles:\s*$/.test(line)) {
			inRoles = true;
			continue;
		}
		const roleMatch = /^\s+-\s+(\S+)/.exec(line);
		if (inRoles && roleMatch) {
			current.roles.push(roleMatch[1].replace(/^['"]|['"]$/g, ""));
		}
	}
	if (current) uids.push(current);
	return { mode, uids };
}

export function readIdentityPolicy(ledger: Ledger): IdentityPolicy | null {
	try {
		return parseIdentityPolicy(readFileSync(join(ledger.ledgerDir, "identity.yaml"), "utf8"));
	} catch {
		return null;
	}
}

export function verifierIdentities(policy: IdentityPolicy): IdentityUid[] {
	return policy.uids.filter((u) => u.roles.includes("verifier"));
}

/** Copy for the uid-isolated confirmation: human-auth, not a hidden sudo. */
export function describeVerifierAuthPrompt(policy: IdentityPolicy | null, authorUid: number | null): string[] {
	const lines = [
		"Trusted uid-isolated review needs a Unix user whose UID is a registered verifier and is distinct from the claim author.",
		"This session will only write the bundle; you authorize the sudo -u run yourself (POE-ISS-007).",
		"A verifier-only identity cannot attach draft/no-status evidence; do not use this path to invent that (POE-ISS-008).",
	];
	if (authorUid !== null) lines.push(`Claim author UID: ${authorUid}`);
	if (policy) {
		lines.push(`Identity mode: ${policy.mode}`);
		const vers = verifierIdentities(policy);
		if (vers.length > 0) {
			lines.push("Registered verifier identities (authority names, not harness reviewers):");
			for (const v of vers) lines.push(`  uid ${v.uid}  name ${v.name}  roles ${v.roles.join(",")}`);
		}
	}
	return lines;
}

export interface ClaimShowSummary {
	claimId: string | null;
	taskId: string | null;
	type: string | null;
	text: string | null;
	madeBy: string | null;
	verifyCmd: string | null;
	requiredGate: string | null;
	authorUid: number | null;
	authorUser: string | null;
	verificationStatus: string | null;
}

function naToNull(value: string | undefined): string | null {
	const v = (value ?? "").trim();
	if (!v || v === "N/A") return null;
	return v;
}

/** Parse the Label: value header printed by `./operator claim-show`. */
export function parseClaimShow(stdout: string): ClaimShowSummary {
	const fields: Record<string, string> = {};
	for (const line of splitLines(stdout)) {
		const m = /^(Claim ID|Task ID|Type|Text|Made By|Required Gate|Verification Command|Verification status|Author Executor):\s*(.*)$/.exec(
			line,
		);
		if (m) fields[m[1]] = m[2].trim();
	}
	let authorUid: number | null = null;
	let authorUser: string | null = null;
	const author = fields["Author Executor"];
	if (author) {
		const parsed = /uid\s+(\d+)\s+\(([^)]+)\)/.exec(author);
		if (parsed) {
			authorUid = Number(parsed[1]);
			authorUser = parsed[2];
		}
	}
	return {
		claimId: naToNull(fields["Claim ID"]),
		taskId: naToNull(fields["Task ID"]),
		type: naToNull(fields["Type"]),
		text: naToNull(fields["Text"]),
		madeBy: naToNull(fields["Made By"]),
		verifyCmd: naToNull(fields["Verification Command"]),
		requiredGate: naToNull(fields["Required Gate"]),
		authorUid,
		authorUser,
		verificationStatus: naToNull(fields["Verification status"]),
	};
}

export interface ReviewDelegateSummary {
	bundlePath: string | null;
	scriptPath: string | null;
	warnings: string[];
	runCommand: string | null;
	neverVerifies: boolean;
}

/** Parse the success lines printed by `./operator review-delegate`. */
export function parseReviewDelegate(result: CommandResult): ReviewDelegateSummary {
	const text = `${result.stdout}\n${result.stderr}`;
	let bundlePath: string | null = null;
	let scriptPath: string | null = null;
	let runCommand: string | null = null;
	const warnings: string[] = [];
	const lines = splitLines(text);
	for (let i = 0; i < lines.length; i += 1) {
		const line = lines[i];
		const bundle = /^Created review delegation bundle:\s+(.+)$/.exec(line);
		if (bundle) bundlePath = bundle[1].trim();
		const script = /^Created reviewer launch script:\s+(.+)$/.exec(line);
		if (script) scriptPath = script[1].trim();
		if (line.startsWith("[Warning]")) warnings.push(line.slice("[Warning]".length).trim());
		if (line === "Run command:" && i + 1 < lines.length) runCommand = lines[i + 1].trim();
	}
	return {
		bundlePath,
		scriptPath,
		warnings,
		runCommand,
		neverVerifies: /never verifies by itself/.test(text),
	};
}

export type ReviewDelegateFailure =
	| "broker_enrolled"
	| "missing_reviewer"
	| "missing_verify_cmd"
	| "claim_mismatch"
	| "other";

export const BROKER_ENROLLMENT_MARK = "review-delegate is only implemented for local file-backed ledgers";

export function classifyReviewDelegateError(stderr: string, stdout = ""): ReviewDelegateFailure {
	const text = `${stderr}\n${stdout}`;
	if (text.includes(BROKER_ENROLLMENT_MARK) || text.includes("only implemented for local file-backed ledgers")) {
		return "broker_enrolled";
	}
	if (text.includes("--reviewer is required") || text.includes("review_harness is routing metadata")) {
		return "missing_reviewer";
	}
	if (text.includes("no verification command is recorded") || text.includes("required_gate is an artifact path")) {
		return "missing_verify_cmd";
	}
	if (text.includes("belongs to task")) return "claim_mismatch";
	return "other";
}

export function brokerEnrollmentMessage(): string {
	return (
		"/op:supervisor-review is unavailable under broker enrollment: " +
		"review-delegate is only implemented for local file-backed ledgers."
	);
}

// --- output parsing ----------------------------------------------------------

export interface CommandResult {
	stdout: string;
	stderr: string;
	code: number;
}

export interface DoctorSummary {
	ok: boolean;
	code: number;
	errors: string[];
	warnings: string[];
	infos: string[];
	/** The "Total consistency issues found: N" figure, when doctor printed one. */
	total: number | null;
	headline: string;
	lines: string[];
}

/**
 * Summarize `./operator doctor`. doctor fails closed with exit 1, so the exit
 * code is the verdict; the counts are there to say why.
 */
export function summarizeDoctor(result: CommandResult): DoctorSummary {
	const lines = splitLines(`${result.stdout}${result.stderr}`);
	const errors: string[] = [];
	const warnings: string[] = [];
	const infos: string[] = [];
	let total: number | null = null;
	for (const line of lines) {
		if (line.startsWith("[Error]")) errors.push(line.slice("[Error]".length).trim());
		else if (line.startsWith("[Warning]")) warnings.push(line.slice("[Warning]".length).trim());
		else if (line.startsWith("[Info]")) infos.push(line.slice("[Info]".length).trim());
		const m = /^Total consistency issues found:\s*(\d+)/.exec(line);
		if (m) total = Number(m[1]);
	}
	const ok = result.code === 0;
	// Counts of printed message lines. doctor also prints its own
	// "Total consistency issues found" figure, which does not always equal
	// them; both are reported rather than reconciled here.
	const counts = `${errors.length} error / ${warnings.length} warning line${warnings.length === 1 ? "" : "s"}`;
	const headline = ok ? `doctor PASS (exit 0; ${counts})` : `doctor FAIL (exit ${result.code}; ${counts})`;
	return { ok, code: result.code, errors, warnings, infos, total, headline, lines };
}

/** Header cells seen in the first column of operator's tables. */
const TABLE_HEADER_CELLS = new Set(["TASK ID", "CLAIM ID", "USAGE ID", "SESSION ID"]);

export interface TaskRow {
	id: string;
	status: string;
	assigned: string;
	reviewer: string;
	claims: string;
	nextAction: string;
}

/** Parse the pipe-delimited table printed by `./operator task-list`. */
export function parseTaskList(stdout: string): TaskRow[] {
	const rows: TaskRow[] = [];
	for (const line of splitLines(stdout)) {
		if (!line.includes("|")) continue;
		if (/^[=-]+$/.test(line.trim())) continue;
		const parts = line.split("|");
		if (parts.length < 6) continue;
		const id = parts[0].trim();
		if (!id || TABLE_HEADER_CELLS.has(id)) continue;
		rows.push({
			id,
			status: parts[1].trim(),
			assigned: parts[2].trim(),
			reviewer: parts[3].trim(),
			claims: parts[4].trim(),
			nextAction: parts.slice(5).join("|").trim(),
		});
	}
	return rows;
}

const TASK_SHOW_LABELS = [
	"Task ID",
	"Objective",
	"Status",
	"Repo",
	"Assigned Harness",
	"Review Harness",
	"Created At",
	"Updated At",
	"Operator Dec",
	"Next Action",
] as const;

export interface TaskShowSummary {
	fields: Record<string, string>;
	assumptions: number;
	claims: number;
	evidence: number;
	handoffs: number;
}

/** Parse the `Label: value` header and the four bullet sections of task-show. */
export function parseTaskShow(stdout: string): TaskShowSummary {
	const fields: Record<string, string> = {};
	const sections: Record<string, number> = {
		"Open Assumptions": 0,
		Claims: 0,
		Evidence: 0,
		Handoffs: 0,
	};
	let section: string | null = null;
	for (const line of splitLines(stdout)) {
		const heading = /^(Open Assumptions|Claims|Evidence|Handoffs):\s*$/.exec(line);
		if (heading) {
			section = heading[1];
			continue;
		}
		if (/^[=-]{10,}$/.test(line.trim())) {
			section = null;
			continue;
		}
		if (section) {
			if (line.startsWith("  - ")) sections[section] += 1;
			continue;
		}
		for (const label of TASK_SHOW_LABELS) {
			if (line.startsWith(`${label}:`)) {
				fields[label] = line.slice(label.length + 1).trim();
				break;
			}
		}
	}
	return {
		fields,
		assumptions: sections["Open Assumptions"],
		claims: sections.Claims,
		evidence: sections.Evidence,
		handoffs: sections.Handoffs,
	};
}

export interface ClaimRow {
	id: string;
	taskId: string;
	type: string;
	status: string;
	text: string;
}

/** Parse the pipe-delimited table printed by `./operator claim-list`. */
export function parseClaimList(stdout: string): ClaimRow[] {
	const rows: ClaimRow[] = [];
	for (const line of splitLines(stdout)) {
		if (!line.includes("|")) continue;
		if (/^[=-]+$/.test(line.trim())) continue;
		const parts = line.split("|");
		if (parts.length < 5) continue;
		const id = parts[0].trim();
		if (!id || TABLE_HEADER_CELLS.has(id)) continue;
		rows.push({
			id,
			taskId: parts[1].trim(),
			type: parts[2].trim(),
			status: parts[3].trim(),
			text: parts.slice(4).join("|").trim(),
		});
	}
	return rows;
}

/** Count data rows in the table printed by `./operator session-list`. */
export function countSessionRows(stdout: string): number {
	let count = 0;
	for (const line of splitLines(stdout)) {
		if (!line.includes("|")) continue;
		if (/^[=-]+$/.test(line.trim())) continue;
		const first = line.split("|")[0].trim();
		if (!first || TABLE_HEADER_CELLS.has(first)) continue;
		count += 1;
	}
	return count;
}

/**
 * Pull the record id out of a write command's success line.
 *
 * claim-add prints "Registered claim 'claim-0007' on task 'x'.",
 * evidence-attach "Attached evidence 'evidence-0003' to task 'x'.",
 * handoff-add "Successfully recorded handoff 'handoff-0002' for task 'x'.".
 * Returns null when the line is absent, which is how a failed write is
 * distinguished from a silent one.
 */
export function parseRecordId(stdout: string, prefix: "claim" | "evidence" | "handoff"): string | null {
	const re = new RegExp(`'(${prefix}-[0-9]+)'`);
	for (const line of splitLines(stdout)) {
		const m = re.exec(line);
		if (m) return m[1];
	}
	return null;
}

// --- report shaping ----------------------------------------------------------

export type ReportLevel = "info" | "warning" | "error";

/** customType used for the report entries this extension appends to the session. */
export const REPORT_ENTRY_TYPE = "operator-report";

/**
 * The payload persisted with pi.appendEntry and drawn by the entry renderer.
 * It is display state only; see POE-RUL-105 (output is not evidence).
 */
export interface Report {
	command: string;
	title: string;
	headline: string;
	level: ReportLevel;
	lines: string[];
	/** The exact `./operator ...` invocations behind this report, for audit. */
	invocations: string[];
}

/** Where the task under discussion came from. Never silently inferred. */
export type TaskOrigin = "session" | "ledger" | "none";

export function describeOrigin(origin: TaskOrigin): string {
	switch (origin) {
		case "session":
			return "pi session selection (/op:use)";
		case "ledger":
			return "ledger current_task (.operator/operator.yaml)";
		case "none":
			return "not set";
	}
}

export function buildDoctorReport(summary: DoctorSummary): Report {
	const lines: string[] = [summary.headline];
	if (summary.total !== null) {
		lines.push(`doctor's own count: Total consistency issues found: ${summary.total}`);
		if (summary.total !== summary.errors.length + summary.warnings.length) {
			lines.push(
				`(that figure differs from the ${summary.errors.length + summary.warnings.length} [Error]/[Warning] lines doctor printed; both are reported as-is)`,
			);
		}
	}
	if (summary.errors.length > 0) {
		lines.push("", "Errors:");
		for (const e of summary.errors) lines.push(`  - ${truncate(e, 220)}`);
	}
	if (summary.warnings.length > 0) {
		lines.push("", `Warnings (${summary.warnings.length}, first 5):`);
		for (const w of summary.warnings.slice(0, 5)) lines.push(`  - ${truncate(w, 220)}`);
	}
	lines.push("", "Read-only check. Nothing here is ledger evidence until attached (POE-RUL-105).");
	return {
		command: "/op:doctor",
		title: "Operator doctor",
		headline: summary.headline,
		level: summary.ok ? (summary.warnings.length > 0 ? "warning" : "info") : "error",
		lines,
		invocations: ["./operator doctor"],
	};
}

export interface StatusInput {
	ledgerRoot: string;
	sessionTask: string | null;
	ledgerCurrentTask: string | null;
	activeTask: string | null;
	activeOrigin: TaskOrigin;
	taskShow: TaskShowSummary | null;
	claims: ClaimRow[];
	sessionCount: number | null;
	doctor: DoctorSummary | null;
	taskCount: number | null;
	invocations: string[];
	notes: string[];
}

export function buildStatusReport(input: StatusInput): Report {
	const lines: string[] = [];
	lines.push(`Ledger:            ${input.ledgerRoot}/${LEDGER_DIR}`);
	lines.push(`Session selection: ${input.sessionTask ?? "(none)"}`);
	lines.push(`Ledger current_task: ${input.ledgerCurrentTask ?? "(none)"}`);
	lines.push(`Showing:           ${input.activeTask ?? "(no task)"} - from ${describeOrigin(input.activeOrigin)}`);
	if (input.taskCount !== null) lines.push(`Tasks in ledger:   ${input.taskCount} (excluding eval-* cells)`);

	if (input.taskShow) {
		const f = input.taskShow.fields;
		lines.push("", "Task");
		lines.push(`  status:    ${f.Status ?? "?"}`);
		lines.push(`  assigned:  ${f["Assigned Harness"] ?? "?"}`);
		lines.push(`  reviewer:  ${f["Review Harness"] ?? "?"}`);
		lines.push(`  updated:   ${f["Updated At"] ?? "?"}`);
		if (f["Next Action"]) lines.push(`  next:      ${truncate(f["Next Action"], 200)}`);
		lines.push(
			`  records:   ${input.taskShow.claims} claim(s), ${input.taskShow.evidence} evidence, ` +
				`${input.taskShow.handoffs} handoff(s), ${input.taskShow.assumptions} open assumption(s)`,
		);
		if (f.Objective) lines.push(`  objective: ${truncate(f.Objective, 300)}`);
	}

	if (input.claims.length > 0) {
		const byStatus = new Map<string, number>();
		for (const c of input.claims) byStatus.set(c.status, (byStatus.get(c.status) ?? 0) + 1);
		const summary = [...byStatus.entries()].map(([s, n]) => `${s.toLowerCase()}:${n}`).join(" ");
		lines.push("", `Claims (${input.claims.length}) ${summary}`);
		for (const c of input.claims.slice(-5)) {
			lines.push(`  - ${c.id} [${c.status}] ${truncate(c.text, 150)}`);
		}
	} else if (input.activeTask) {
		lines.push("", "Claims: none registered for this task");
	}

	if (input.sessionCount !== null) lines.push("", `Sessions for this task: ${input.sessionCount}`);
	if (input.doctor) lines.push("", `Doctor: ${input.doctor.headline}`);
	for (const note of input.notes) lines.push("", note);
	lines.push("", "Read-only. No authority record was written (POE-RUL-101/112).");

	const headline = input.activeTask
		? `${input.activeTask} - ${input.taskShow?.fields.Status ?? "?"}${input.doctor ? `; ${input.doctor.headline}` : ""}`
		: "no active task selected";
	const level: ReportLevel = input.doctor && !input.doctor.ok ? "error" : input.activeTask ? "info" : "warning";
	return {
		command: "/op:status",
		title: "Operator status",
		headline,
		level,
		lines,
		invocations: input.invocations,
	};
}

export function buildTasksReport(rows: TaskRow[], invocation: string, filterNote: string | null): Report {
	const lines: string[] = [];
	if (filterNote) lines.push(filterNote, "");
	if (rows.length === 0) {
		lines.push("No tasks matched.");
	} else {
		lines.push(`${"TASK ID".padEnd(38)} ${"STATUS".padEnd(12)} ${"ASSIGNED".padEnd(18)} CLAIMS`);
		for (const r of rows) {
			lines.push(`${r.id.padEnd(38)} ${r.status.padEnd(12)} ${r.assigned.padEnd(18)} ${r.claims}`);
		}
	}
	lines.push("", "Use /op:use <task-id> to select one for this pi session.");
	return {
		command: "/op:tasks",
		title: "Operator tasks",
		headline: `${rows.length} task${rows.length === 1 ? "" : "s"}`,
		level: "info",
		lines,
		invocations: [invocation],
	};
}

export interface RoadmapStep {
	step: number;
	name: string;
	gate: string;
}

export interface RoadmapFutureFeature {
	id: string;
	name: string;
	command: string | null;
	description: string;
}

export interface RoadmapIssue {
	id: string;
	summary: string;
	nextStep: string;
}

export interface RoadmapPbc {
	path: string;
	steps: RoadmapStep[];
	futureFeatures: RoadmapFutureFeature[];
	issues: RoadmapIssue[];
}

export function readPiOperatorRoadmap(root: string): RoadmapPbc {
	let path = join(root, "owners-manual", "pbc", "appendix-pi-operator-extension.pbc.md");
	if (!existsSync(path)) path = join(process.cwd(), "owners-manual", "pbc", "appendix-pi-operator-extension.pbc.md");
	const text = readFileSync(path, "utf8");
	const lines = splitLines(text);
	const steps: RoadmapStep[] = [];
	const futureFeatures: RoadmapFutureFeature[] = [];
	const issues: RoadmapIssue[] = [];
	let section = "";
	let step: Partial<RoadmapStep> | null = null;
	let future: Partial<RoadmapFutureFeature> | null = null;
	let issue: Partial<RoadmapIssue> | null = null;
	const flushStep = () => {
		if (step?.step !== undefined && step.name && step.gate) steps.push({ step: step.step, name: step.name, gate: step.gate });
		step = null;
	};
	const flushFuture = () => {
		if (future?.id && future.name && future.description) futureFeatures.push({ id: future.id, name: future.name, command: future.command ?? null, description: future.description });
		future = null;
	};
	const flushIssue = () => {
		if (issue?.id && issue.summary && issue.nextStep) issues.push({ id: issue.id, summary: issue.summary, nextStep: issue.nextStep });
		issue = null;
	};
	for (const raw of lines) {
		const line = raw.trimEnd();
		if (/^## Future Feature Candidates/.test(line)) section = "future";
		else if (/^## Dogfood Issue Backlog/.test(line)) section = "issues";
		else if (/^## Implementation Ladder/.test(line)) section = "ladder";
		else if (/^## /.test(line)) section = "";

		if (section === "ladder") {
			const stepMatch = /^\s*- step:\s*(\d+)/.exec(line);
			if (stepMatch) {
				flushStep();
				step = { step: Number(stepMatch[1]) };
				continue;
			}
			if (step) {
				const m = /^\s+(name|gate):\s*(.*)$/.exec(line);
				if (m) (step as Record<string, unknown>)[m[1]] = m[2];
			}
		} else if (section === "future") {
			const idMatch = /^\s*- id:\s*(\S+)/.exec(line);
			if (idMatch) {
				flushFuture();
				future = { id: idMatch[1] };
				continue;
			}
			if (future) {
				const m = /^\s+(name|command|description):\s*(.*)$/.exec(line);
				if (m) (future as Record<string, unknown>)[m[1]] = m[2];
			}
		} else if (section === "issues") {
			const idMatch = /^\s*- id:\s*(\S+)/.exec(line);
			if (idMatch) {
				flushIssue();
				issue = { id: idMatch[1] };
				continue;
			}
			if (issue) {
				const m = /^\s+(summary|next_step):\s*(.*)$/.exec(line);
				if (m) {
					if (m[1] === "next_step") issue.nextStep = m[2];
					else issue.summary = m[2];
				}
			}
		}
	}
	flushStep();
	flushFuture();
	flushIssue();
	return { path, steps, futureFeatures, issues };
}

export interface RoadmapReportInput {
	roadmap: RoadmapPbc;
	activeTask: string | null;
	activeOrigin: TaskOrigin;
	taskShow: TaskShowSummary | null;
	invocations: string[];
}

export function buildNextStepsReport(input: RoadmapReportInput & { claims: ClaimRow[] }): Report {
	const lines: string[] = [];
	const f = input.taskShow?.fields ?? {};
	const unverified = input.claims.filter((c) => c.status.toUpperCase() !== "VERIFIED");
	lines.push(`Showing task: ${input.activeTask ?? "(none)"} - from ${describeOrigin(input.activeOrigin)}`);
	if (f.Status) lines.push(`Task status: ${f.Status}`);
	lines.push("", "Recommended next steps");
	let n = 1;
	if (f["Next Action"]) lines.push(`${n++}. Current ledger next_action: ${truncate(f["Next Action"], 240)}`);
	if (unverified.length > 0) {
		lines.push(`${n++}. Review or intentionally leave unverified claim(s): ${unverified.map((c) => c.id).join(", ")}.`);
		const latest = unverified[unverified.length - 1];
		if (latest) lines.push(`   Suggested: /op:supervisor-review ${latest.id}`);
	}
	if (input.activeTask && input.taskShow && unverified.length === 0 && f.Status !== "verified") {
		lines.push(`${n++}. Task has no unverified claims shown here; consider final /op:handoff and task transition/verification closeout.`);
	}
	const recentIssue = input.roadmap.issues[input.roadmap.issues.length - 1];
	if (recentIssue) lines.push(`${n++}. Latest dogfood issue: ${recentIssue.id} — ${truncate(recentIssue.nextStep, 220)}`);
	const recentFeatures = input.roadmap.futureFeatures.slice(-3);
	if (recentFeatures.length > 0) {
		lines.push(`${n++}. Candidate feature slices: ${recentFeatures.map((x) => x.command ?? x.id).join(", ")}.`);
	}
	if (n === 1) lines.push("1. No active task context found. Run /op:tasks then /op:use <task-id>.");
	lines.push("", "This is guidance only. It does not execute commands or write the ledger.");
	return {
		command: "/op:next-steps",
		title: "Operator next steps",
		headline: input.activeTask ? `next steps for ${input.activeTask}` : "no active task selected",
		level: input.activeTask ? "info" : "warning",
		lines,
		invocations: input.invocations,
	};
}

export function buildRoadmapReport(input: RoadmapReportInput): Report {
	const lines: string[] = [];
	const currentStep = input.activeTask ? /step(\d+)/.exec(input.activeTask)?.[1] ?? null : null;
	lines.push(`Source: ${input.roadmap.path}`);
	lines.push(`Showing task: ${input.activeTask ?? "(none)"} - from ${describeOrigin(input.activeOrigin)}`);
	if (input.taskShow) {
		const f = input.taskShow.fields;
		lines.push(`Task status: ${f.Status ?? "?"}`);
		if (f["Next Action"]) lines.push(`Next action: ${truncate(f["Next Action"], 220)}`);
	}
	lines.push("", "Implementation ladder");
	for (const s of input.roadmap.steps) {
		const marker = currentStep === String(s.step) ? "→" : " ";
		lines.push(`${marker} ${s.step}. ${s.name}`);
		lines.push(`     gate: ${truncate(s.gate, 180)}`);
	}
	lines.push("", "Recommended next feature slices");
	for (const f of input.roadmap.futureFeatures.slice(-5)) {
		lines.push(`  - ${f.id}${f.command ? ` ${f.command}` : ""}: ${f.name}`);
		lines.push(`    ${truncate(f.description, 180)}`);
	}
	lines.push("", "Recent dogfood issues");
	for (const i of input.roadmap.issues.slice(-5)) {
		lines.push(`  - ${i.id}: ${truncate(i.summary, 180)}`);
	}
	lines.push("", "Read-only roadmap. Future features are not part of the current acceptance gate unless promoted explicitly.");
	return {
		command: "/op:roadmap",
		title: "Operator roadmap",
		headline: currentStep ? `step ${currentStep} context; ${input.roadmap.futureFeatures.length} future feature(s)` : `${input.roadmap.steps.length} ladder step(s)` ,
		level: "info",
		lines,
		invocations: input.invocations,
	};
}

export function truncate(text: string, max: number): string {
	const flat = text.replace(/\s+/g, " ").trim();
	return flat.length <= max ? flat : `${flat.slice(0, max - 1)}…`;
}

export function splitLines(text: string): string[] {
	return text.split(/\r?\n/);
}

/** Render an argv as the `./operator ...` string shown to the user. */
export function formatInvocation(argv: string[]): string {
	return `./operator ${argv.join(" ")}`;
}

// --- step 2 write reports ----------------------------------------------------

/** The two sentences every authoring write ends with, so the boundary is never implied away. */
export const WRITE_BOUNDARY_NOTES = [
	"--by is provenance text only: it is not a harness id and not a verifier identity (POE-RUL-003).",
	"Nothing here verifies anything. --status, --verified-by and --verdict are not extension inputs (POE-RUL-113).",
] as const;

export interface WriteOutcome {
	/** Slash command that produced this, e.g. "/op:claim". */
	command: string;
	title: string;
	/** Noun for the record: "claim", "evidence", "handoff". */
	noun: string;
	taskId: string;
	by: string;
	argv: string[];
	result: CommandResult;
	recordId: string | null;
	/** Command-specific detail lines placed above the boundary notes. */
	detail: string[];
}

/**
 * Report for a completed (or failed) authoring write.
 *
 * A non-zero exit is reported as an error with operator's own stderr, not
 * smoothed over: the ledger is the source of truth about whether the record
 * exists (POE-RUL-101).
 */
export function buildWriteReport(outcome: WriteOutcome): Report {
	const ok = outcome.result.code === 0 && outcome.recordId !== null;
	const lines: string[] = [];
	if (ok) {
		lines.push(`Recorded ${outcome.recordId} on task ${outcome.taskId}, by ${outcome.by}.`);
	} else if (outcome.result.code === 0) {
		lines.push(
			`./operator exited 0 but printed no ${outcome.noun} id. Treat the ledger, not this report, as the record:`,
			`  ${truncate(outcome.result.stdout || outcome.result.stderr, 300)}`,
		);
	} else {
		lines.push(
			`./operator exited ${outcome.result.code}; no ${outcome.noun} was recorded.`,
			`  ${truncate(outcome.result.stderr || outcome.result.stdout, 300)}`,
		);
	}
	if (outcome.detail.length > 0) lines.push("", ...outcome.detail);
	lines.push("", ...WRITE_BOUNDARY_NOTES);
	const headline = ok
		? `${outcome.recordId} on ${outcome.taskId}`
		: `failed on ${outcome.taskId} (exit ${outcome.result.code})`;
	return {
		command: outcome.command,
		title: outcome.title,
		headline,
		level: ok ? "info" : "error",
		lines,
		invocations: [formatInvocation(outcome.argv)],
	};
}

/**
 * Report for a write the user declined at the confirmation dialog, or that was
 * refused before spawning. Recorded in the transcript so a decline is as
 * visible as a write.
 */
export function buildDeclinedReport(command: string, title: string, reason: string, argv: string[] | null): Report {
	return {
		command,
		title,
		headline: "nothing written",
		level: "warning",
		lines: [reason, "", "The ledger was not touched."],
		invocations: argv ? [`${formatInvocation(argv)}   (not run)`] : [],
	};
}

/** Lines describing what a claim write is about to do, for the confirmation dialog. */
export function describeClaimPlan(opts: ClaimAddOptions): string[] {
	const lines = [
		`task:       ${opts.taskId}`,
		`type:       ${opts.type}`,
		`by:         ${opts.by}   (session-derived provenance)`,
		`gate:       ${opts.gate?.trim() || "(none)"}`,
		`verify-cmd: ${opts.verifyCmd?.trim() || "(none)"}`,
	];
	if (opts.layer) lines.push(`layer:      ${opts.layer}`);
	lines.push(`text:       ${truncate(opts.text, 300)}`);
	lines.push("", "The claim is recorded unverified. This extension cannot verify it.");
	return lines;
}

/** Lines describing an evidence write, for the confirmation dialog. */
export function describeEvidencePlan(opts: EvidenceAttachOptions, remote: boolean): string[] {
	const lines = [
		`task:       ${opts.taskId}`,
		`claim:      ${opts.claimId ?? "(none - task-level evidence)"}`,
		`type:       ${opts.type}`,
		`locator:    ${opts.locator}`,
		`by:         ${opts.by}   (session-derived provenance)`,
		`verify-cmd: ${opts.verifyCmd?.trim() || "(none)"}`,
		`notes:      ${truncate(opts.notes ?? "", 200) || "(none)"}`,
	];
	if (opts.hash) lines.push(`hash:       ${opts.hash}`);
	if (remote) {
		lines.push(
			"",
			"Remote locator: operator keeps no local snapshot, so doctor reports this evidence as uncheckable.",
		);
	}
	if (!opts.claimId) {
		lines.push("", "No --claim: this attaches to the task only, and no claim gains evidence from it.");
	}
	if (!opts.verifyCmd?.trim()) {
		lines.push("", "No --verify-cmd: evidence prefers a re-runnable command over a static blob.");
	}
	return lines;
}

/** Lines describing a handoff write, for the confirmation dialog. */
export function describeHandoffPlan(taskId: string, by: string, draft: HandoffDraft): string[] {
	const lines = [`task:       ${taskId}`, `by:         ${by}   (session-derived provenance)`, ""];
	for (const section of HANDOFF_SECTIONS) {
		const body = (draft[section.flag] ?? "").trim();
		lines.push(`${section.heading}: ${body ? truncate(body, 160) : "(omitted)"}`);
	}
	if (draft["--next-action"]) {
		lines.push("", "A next action also overwrites the task's next_action field.");
	}
	return lines;
}

// --- step 3 supervisor-review reports ----------------------------------------

export const SUPERVISOR_REVIEW_BOUNDARY_NOTES = [
	"The review target is a model/persona label recorded as --reviewer. Pi is only a carrier/runtime; --reviewer is never taken from --by or the session (POE-RUL-003/102).",
	"The task's review_harness may suggest a default review target, but it is routing/economics metadata, not Unix verifier authority.",
	"This command writes a review bundle only. It does not verify, does not attach evidence, and does not emit --status, --verified-by or --verdict (POE-RUL-113).",
	"Trusted verification still requires a distinct registered verifier UID such as operator-verifier. Same-UID review is advisory (POE-ISS-007).",
	"A verifier-only identity cannot attach draft/no-status evidence; this command does not offer that path (POE-ISS-008).",
] as const;

export const EVIDENCE_KIND_NOTES = [
	"Three evidence kinds, not interchangeable:",
	"  1. Advisory review notes (advisory-agent): same-UID commentary. Not trusted verification.",
	"  2. Builder-owned draft artifacts: /op:evidence from a builder identity, no lifecycle flags.",
	"  3. Verifier-owned status-setting evidence: only a registered verifier UID, with lifecycle flags, after a human-authorized UID run. Verifier-only identities cannot attach draft/no-status evidence.",
] as const;

export interface SupervisorReviewPlanInput extends ReviewDelegateOptions {
	assignedHarness?: string | null;
	reviewHarness?: string | null;
	sessionAuthor?: string | null;
	authorUid?: number | null;
	identity?: IdentityPolicy | null;
}

export function describeSupervisorReviewPlan(opts: SupervisorReviewPlanInput): string[] {
	const lines = [
		`task:       ${opts.taskId}`,
		`claim:      ${opts.claimId}   (one named claim; not a session or claim-set)`,
		`reviewer:   ${opts.reviewer}   (review model/persona label; not the Unix verifier user)`,
		`mode:       ${opts.mode}`,
	];
	if (opts.mode === "uid-isolated") {
		lines.push(
			`review-user: ${opts.reviewUser}   (human-authorized Unix user; this session will not run sudo)`,
		);
	} else {
		lines.push("review-user: (none — advisory path does not escalate UID)");
	}
	lines.push(`verify-cmd: ${opts.verifyCmd}`);
	if (opts.sessionAuthor) {
		lines.push(`session --by: ${opts.sessionAuthor}   (provenance only; not used as --reviewer)`);
	}
	if (opts.assignedHarness) {
		lines.push(`assigned:   ${opts.assignedHarness}   (implementer routing; not reviewer authority)`);
	}
	if (opts.reviewHarness) {
		lines.push(`review_harness: ${opts.reviewHarness}   (review target routing hint; separate from verifier UID)`);
	}
	if (opts.authorUid !== null && opts.authorUid !== undefined) {
		lines.push(`claim author UID: ${opts.authorUid}`);
	}
	lines.push("");
	if (opts.mode === "uid-isolated") {
		lines.push("Trusted path: writes a sudo -u <review-user> script. Authorize that script yourself.");
		lines.push("This session cannot set verification status. Silent fallback to same-UID advisory is not offered.");
		lines.push(...describeVerifierAuthPrompt(opts.identity ?? null, opts.authorUid ?? null));
	} else {
		lines.push("Advisory path: same-UID review notes only. Expected authority is advisory, not uid_isolated.");
		lines.push("This is not trusted verification and does not attach verifier-owned status-setting evidence.");
	}
	lines.push(
		"The generated reviewer script currently includes --approve (operator-side POE-ISS-005); this extension does not rewrite it.",
	);
	lines.push("", ...EVIDENCE_KIND_NOTES);
	return lines;
}

export function parseReviewModeChoice(picked: string): ReviewMode | null {
	const mode = picked.trim().split(/\s+/)[0];
	if ((REVIEW_MODES as readonly string[]).includes(mode)) return mode as ReviewMode;
	return null;
}

export interface SupervisorReviewOutcome {
	taskId: string;
	opts: ReviewDelegateOptions;
	argv: string[];
	result: CommandResult;
}

export function buildSupervisorReviewReport(outcome: SupervisorReviewOutcome): Report {
	const failure =
		outcome.result.code === 0
			? null
			: classifyReviewDelegateError(outcome.result.stderr, outcome.result.stdout);
	if (failure === "broker_enrolled") {
		return {
			command: "/op:supervisor-review",
			title: "Operator supervisor-review",
			headline: "unavailable under broker enrollment",
			level: "error",
			lines: [
				brokerEnrollmentMessage(),
				`  ${truncate(outcome.result.stderr || outcome.result.stdout, 300)}`,
				"",
				...SUPERVISOR_REVIEW_BOUNDARY_NOTES,
			],
			invocations: [formatInvocation(outcome.argv)],
		};
	}
	const parsed = parseReviewDelegate(outcome.result);
	const ok = outcome.result.code === 0 && parsed.bundlePath !== null;
	const lines: string[] = [];
	if (ok) {
		lines.push(`Wrote review bundle ${parsed.bundlePath}`);
		if (parsed.scriptPath) lines.push(`Wrote launch script ${parsed.scriptPath}`);
		lines.push(`Mode: ${outcome.opts.mode}. Claim: ${outcome.opts.claimId}. Reviewer: ${outcome.opts.reviewer}.`);
		if (parsed.warnings.length > 0) {
			lines.push("", "Warnings from review-delegate:");
			for (const warning of parsed.warnings) lines.push(`  - ${truncate(warning, 220)}`);
		}
		if (parsed.runCommand) {
			lines.push("", "Run command (not executed by this extension):", `  ${truncate(parsed.runCommand, 300)}`);
		}
		if (parsed.neverVerifies) {
			lines.push("", "review-delegate notes that it never verifies by itself.");
		}
		lines.push("", ...EVIDENCE_KIND_NOTES);
		if (outcome.opts.mode === "uid-isolated") {
			lines.push(
				"",
				"Human-auth next step: run the launch script as the named Unix user. This session did not verify.",
			);
		} else {
			lines.push(
				"",
				"Advisory next step: a distinct verifier UID still has to attach status-setting evidence. Same-UID notes do not verify.",
			);
		}
	} else {
		lines.push(`./operator exited ${outcome.result.code}; no review bundle was recorded.`);
		lines.push(`  ${truncate(outcome.result.stderr || outcome.result.stdout, 300)}`);
	}
	lines.push("", ...SUPERVISOR_REVIEW_BOUNDARY_NOTES);
	const headline = ok
		? `bundle for ${outcome.opts.claimId} (${outcome.opts.mode})`
		: `failed on ${outcome.taskId} (exit ${outcome.result.code})`;
	return {
		command: "/op:supervisor-review",
		title: "Operator supervisor-review",
		headline,
		level: ok ? (parsed.warnings.length > 0 ? "warning" : "info") : "error",
		lines,
		invocations: [formatInvocation(outcome.argv)],
	};
}

// --- step 4 delegate ---------------------------------------------------------
// Chooser-first wrap of task-create --assign (unrouted implementer), then
// session-start / brief / export-brief, then harness_adapter invocation.
// Parent assigned_harness / review_harness are never mutated. Dual
// implementer+reviewer targets fail closed (POE-RUL-005). Paste/export is a
// labeled fallback, not the default (POE-RUL-110).

/** Carrier ids that have a harness_adapter.PROFILES entry. Not ledger harness ids. */
export const ADAPTER_CARRIER_IDS = ["claude", "agy", "codex", "grok", "pi", "opencode"] as const;
export type AdapterCarrierId = (typeof ADAPTER_CARRIER_IDS)[number];

export const DELEGATE_ISOLATION_MODES = ["in-repo", "worktree"] as const;
export type DelegateIsolation = (typeof DELEGATE_ISOLATION_MODES)[number];

export const DELEGATE_BRIEF_FORMATS = ["export", "brief"] as const;
export type DelegateBriefFormat = (typeof DELEGATE_BRIEF_FORMATS)[number];

export const DELEGATE_DISPATCH_PATHS = ["adapter", "paste-fallback"] as const;
export type DelegateDispatchPath = (typeof DELEGATE_DISPATCH_PATHS)[number];

/** Model identifiers the adapter will accept. Must not be flag-shaped. */
const MODEL_RE = /^[A-Za-z0-9][A-Za-z0-9._/:+-]*$/;

export interface DelegateTarget {
	alias: string;
	harnessId: string;
	carrierId: string;
	/** Null means "read model from the harness yaml". Never invented. */
	model: string | null;
	isolation: DelegateIsolation;
	briefFormat: DelegateBriefFormat;
	/** Display-only launch hint. Never executed. */
	commandTemplate: string | null;
}

export const DEFAULT_DELEGATE_TARGETS: readonly DelegateTarget[] = [
	{ alias: "claude", harnessId: "claude", carrierId: "claude", model: null, isolation: "in-repo", briefFormat: "export", commandTemplate: null },
	{ alias: "codex", harnessId: "codex", carrierId: "codex", model: null, isolation: "in-repo", briefFormat: "export", commandTemplate: null },
	{ alias: "grok", harnessId: "grok", carrierId: "grok", model: null, isolation: "in-repo", briefFormat: "export", commandTemplate: null },
	{ alias: "opencode", harnessId: "opencode", carrierId: "opencode", model: null, isolation: "in-repo", briefFormat: "export", commandTemplate: null },
	{ alias: "gemini-agy", harnessId: "gemini-agy", carrierId: "agy", model: null, isolation: "in-repo", briefFormat: "export", commandTemplate: null },
];

export function isAdapterCarrierId(id: string): id is AdapterCarrierId {
	return (ADAPTER_CARRIER_IDS as readonly string[]).includes(id);
}

export function delegateTargetsPath(ledger: Ledger): string {
	return join(ledger.root, ".pi", "extensions", "operator", "targets.json");
}

function requireHarnessId(id: string, forCommand: string): string {
	const trimmed = (id ?? "").trim();
	if (!trimmed) throw new Error(`refusing ${forCommand} without a harness id`);
	if (!isValidHarnessId(trimmed)) {
		throw new Error(`refusing ${forCommand} harness id '${trimmed}': expected [A-Za-z0-9][A-Za-z0-9._-]*`);
	}
	return trimmed;
}

function requireAlias(alias: string): string {
	const trimmed = (alias ?? "").trim();
	if (!isValidHarnessId(trimmed)) {
		throw new Error(`refusing delegate alias '${trimmed}': expected [A-Za-z0-9][A-Za-z0-9._-]*`);
	}
	return trimmed;
}

function requireCarrierId(id: string): AdapterCarrierId {
	const trimmed = (id ?? "").trim();
	if (!isAdapterCarrierId(trimmed)) {
		throw new Error(
			`refusing carrier id '${trimmed}': no harness_adapter profile (expected one of ${ADAPTER_CARRIER_IDS.join(", ")})`,
		);
	}
	return trimmed;
}

function requireModelId(model: string, forCommand: string): string {
	const trimmed = (model ?? "").trim();
	if (!trimmed) throw new Error(`refusing ${forCommand} without a model identifier`);
	if (trimmed.startsWith("-")) {
		throw new Error(`refusing ${forCommand} model '${trimmed}': a model starting with '-' would be read as a flag`);
	}
	if (!MODEL_RE.test(trimmed)) {
		throw new Error(`refusing ${forCommand} model '${trimmed}': expected a model id like configured-grok-model`);
	}
	return trimmed;
}

function asIsolation(value: string): DelegateIsolation {
	if ((DELEGATE_ISOLATION_MODES as readonly string[]).includes(value)) return value as DelegateIsolation;
	throw new Error(`refusing isolation '${value}': expected one of ${DELEGATE_ISOLATION_MODES.join(", ")}`);
}

function asBriefFormat(value: string): DelegateBriefFormat {
	if ((DELEGATE_BRIEF_FORMATS as readonly string[]).includes(value)) return value as DelegateBriefFormat;
	throw new Error(`refusing brief format '${value}': expected one of ${DELEGATE_BRIEF_FORMATS.join(", ")}`);
}

export function validateDelegateTarget(raw: DelegateTarget): DelegateTarget {
	const alias = requireAlias(raw.alias);
	const harnessId = requireHarnessId(raw.harnessId, "delegate target");
	const carrierId = requireCarrierId(raw.carrierId);
	const isolation = asIsolation(raw.isolation);
	const briefFormat = asBriefFormat(raw.briefFormat);
	const model = raw.model === null || raw.model === undefined || raw.model === "" ? null : requireModelId(raw.model, "delegate target");
	const commandTemplate =
		raw.commandTemplate === null || raw.commandTemplate === undefined || raw.commandTemplate === ""
			? null
			: String(raw.commandTemplate);
	if (commandTemplate && commandTemplate.startsWith("-")) {
		throw new Error(`refusing command template '${commandTemplate}': a template starting with '-' would be read as a flag`);
	}
	return { alias, harnessId, carrierId, model, isolation, briefFormat, commandTemplate };
}

/**
 * Parse project-local delegate target config.
 *
 * Aliases must resolve to an existing harness yaml at classification time.
 * The config may add model, isolation, brief format, and a display-only
 * command template. It may not invent harness ids or override assigned_harness
 * / review_harness (POE-RUL-108, F13).
 */
export function parseDelegateTargetsJson(text: string): DelegateTarget[] {
	let parsed: unknown;
	try {
		parsed = JSON.parse(text);
	} catch (err) {
		throw new Error(`refusing delegate targets.json: invalid JSON (${err instanceof Error ? err.message : String(err)})`);
	}
	if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
		throw new Error("refusing delegate targets.json: expected an object with a targets array");
	}
	const obj = parsed as Record<string, unknown>;
	if ("assigned_harness" in obj || "review_harness" in obj) {
		throw new Error("refusing delegate targets.json: config may not override assigned_harness or review_harness");
	}
	if (!Array.isArray(obj.targets)) {
		throw new Error("refusing delegate targets.json: expected a targets array");
	}
	const seen = new Set<string>();
	const out: DelegateTarget[] = [];
	for (const item of obj.targets) {
		if (!item || typeof item !== "object" || Array.isArray(item)) {
			throw new Error("refusing delegate targets.json: each target must be an object");
		}
		const row = item as Record<string, unknown>;
		if ("assigned_harness" in row || "review_harness" in row) {
			throw new Error("refusing delegate targets.json: a target may not override assigned_harness or review_harness");
		}
		const target = validateDelegateTarget({
			alias: String(row.alias ?? ""),
			harnessId: String(row.harness_id ?? row.harnessId ?? ""),
			carrierId: String(row.carrier_id ?? row.carrierId ?? ""),
			model: row.model === null || row.model === undefined ? null : String(row.model),
			isolation: String(row.isolation ?? "in-repo"),
			briefFormat: String(row.brief_format ?? row.briefFormat ?? "export"),
			commandTemplate:
				row.command_template === null || row.command_template === undefined
					? row.commandTemplate === null || row.commandTemplate === undefined
						? null
						: String(row.commandTemplate)
					: String(row.command_template),
		});
		if (seen.has(target.alias)) {
			throw new Error(`refusing delegate targets.json: duplicate alias '${target.alias}'`);
		}
		seen.add(target.alias);
		out.push(target);
	}
	if (out.length === 0) throw new Error("refusing delegate targets.json: targets array is empty");
	return out;
}

export function loadDelegateTargets(ledger: Ledger): DelegateTarget[] {
	const path = delegateTargetsPath(ledger);
	if (!existsSync(path)) return DEFAULT_DELEGATE_TARGETS.map((t) => validateDelegateTarget(t));
	let text: string;
	try {
		text = readFileSync(path, "utf8");
	} catch (err) {
		throw new Error(`refusing delegate targets.json: cannot read ${path} (${err instanceof Error ? err.message : String(err)})`);
	}
	return parseDelegateTargetsJson(text);
}

export interface HarnessRecord {
	harnessId: string;
	displayName: string | null;
	kind: string | null;
	command: string | null;
	model: string | null;
}

function yamlScalar(value: string): string | null {
	const raw = value.trim();
	if (!raw || raw === "null" || raw === "~" || raw === "None") return null;
	return raw.replace(/^['"]|['"]$/g, "");
}

/** Parse the small harness yaml shape this repo uses. Unknown keys are ignored. */
export function parseHarnessRecord(text: string): HarnessRecord {
	const fields: Record<string, string | null> = {};
	for (const line of splitLines(text)) {
		const m = /^(harness_id|display_name|kind|command|model):\s*(.*)$/.exec(line);
		if (m) fields[m[1]] = yamlScalar(m[2]);
	}
	return {
		harnessId: fields.harness_id ?? "",
		displayName: fields.display_name ?? null,
		kind: fields.kind ?? null,
		command: fields.command ?? null,
		model: fields.model ?? null,
	};
}

export function readHarnessRecord(ledger: Ledger, harnessId: string): HarnessRecord | null {
	if (!isValidHarnessId(harnessId)) return null;
	try {
		return parseHarnessRecord(readFileSync(join(ledger.ledgerDir, "harnesses", `${harnessId}.yaml`), "utf8"));
	} catch {
		return null;
	}
}

export interface ResolvedDelegateTarget extends DelegateTarget {
	model: string;
	harness: HarnessRecord;
}

export function resolveDelegateTarget(ledger: Ledger, target: DelegateTarget): ResolvedDelegateTarget {
	const valid = validateDelegateTarget(target);
	if (!harnessRecordExists(ledger, valid.harnessId)) {
		throw new Error(
			`refusing delegate target '${valid.alias}': no harness record at ${LEDGER_DIR}/harnesses/${valid.harnessId}.yaml (config may not invent harness ids)`,
		);
	}
	const harness = readHarnessRecord(ledger, valid.harnessId);
	if (!harness) {
		throw new Error(`refusing delegate target '${valid.alias}': could not read harness record '${valid.harnessId}'`);
	}
	const model = valid.model ?? harness.model;
	if (!model) {
		throw new Error(
			`refusing delegate target '${valid.alias}': no model on the target or in ${LEDGER_DIR}/harnesses/${valid.harnessId}.yaml`,
		);
	}
	return { ...valid, model: requireModelId(model, "delegate target"), harness };
}

/** task-show prints `None` when assigned_harness / review_harness is empty. */
export function normalizeHarnessField(value: string | null | undefined): string | null {
	const v = (value ?? "").trim();
	if (!v || v === "None" || v === "N/A" || v === "null" || v === "~") return null;
	return v;
}

export type DelegateRouteAction = "parent-routed" | "child-task" | "refuse";

export interface DelegateRoute {
	action: DelegateRouteAction;
	reason: string;
}

/**
 * Decide how /op:delegate may reach a target for implementation work.
 *
 * parent-routed: target is assigned_harness and is not also review_harness, so
 * brief / session-start will emit a builder brief on the parent.
 * child-task: target is not an implementer on the parent; the user must confirm
 * a scoped child with explicit --assign rather than mutating parent routing.
 * refuse: the selection would make one harness both implementer and reviewer,
 * reuse this session as the implementer, or is otherwise unsafe.
 */
export function classifyDelegateTarget(input: {
	target: Pick<DelegateTarget, "alias" | "harnessId" | "carrierId">;
	assignedHarness: string | null;
	reviewHarness: string | null;
	sessionAuthor?: string | null;
}): DelegateRoute {
	const harnessId = requireHarnessId(input.target.harnessId, "delegate target");
	requireCarrierId(input.target.carrierId);
	const assigned = (input.assignedHarness ?? "").trim() || null;
	const review = (input.reviewHarness ?? "").trim() || null;
	const sessionAuthor = (input.sessionAuthor ?? "").trim() || null;

	if (sessionAuthor && harnessId === sessionAuthor) {
		return {
			action: "refuse",
			reason: `refusing target '${input.target.alias}' (${harnessId}): that is this session's author label; delegate never reuses the current agent as implementer (POE-RUL-102)`,
		};
	}
	if (assigned && review && assigned === review && harnessId === assigned) {
		return {
			action: "refuse",
			reason: `refusing target '${input.target.alias}' (${harnessId}): it is both assigned_harness and review_harness on this task; one harness cannot be implementer and reviewer (POE-RUL-005)`,
		};
	}
	if (assigned && harnessId === assigned) {
		return {
			action: "parent-routed",
			reason: `${harnessId} is assigned_harness, so brief/session-start can emit a builder brief on this task`,
		};
	}
	if (review && harnessId === review) {
		return {
			action: "child-task",
			reason: `${harnessId} is review_harness only; a parent brief would be a reviewer brief. Implementation needs a scoped child task with --assign ${harnessId}, not parent routing`,
		};
	}
	return {
		action: "child-task",
		reason: `${harnessId} is not assigned_harness on this task; create a scoped child with --assign ${harnessId} rather than mutating parent routing (POE-RUL-001)`,
	};
}

export function refuseSelfDelegate(harnessId: string, sessionAuthor: string | null | undefined): void {
	const who = (sessionAuthor ?? "").trim();
	if (who && harnessId === who) {
		throw new Error(
			`refusing implementer '${harnessId}': that is this session's author label; delegate never reuses the current agent (POE-RUL-102)`,
		);
	}
}

export function refuseDualRole(assign: string, review: string | null | undefined, forCommand: string): void {
	const a = requireHarnessId(assign, forCommand);
	const r = (review ?? "").trim();
	if (r && a === r) {
		throw new Error(
			`refusing ${forCommand}: --assign and --review are both '${a}'; one harness cannot be implementer and reviewer (POE-RUL-005)`,
		);
	}
}

export function defaultChildTaskId(parentTaskId: string, alias: string): string {
	requireTaskId(parentTaskId, "delegate child task");
	const id = `${parentTaskId}-via-${requireAlias(alias)}`;
	if (!isValidTaskId(id)) {
		throw new Error(`refusing generated child task id '${id}': expected [A-Za-z0-9][A-Za-z0-9._-]*`);
	}
	return id;
}

export interface DelegateArgs {
	taskId?: string;
	alias?: string;
	token?: string;
}

export function parseDelegateArgs(args: string): DelegateArgs {
	const tokens = args.trim().split(/\s+/).filter(Boolean);
	if (tokens.length > 2) {
		throw new Error("refusing /op:delegate: expected [task-id] [target-alias]");
	}
	if (tokens.length === 2) return { taskId: tokens[0], alias: tokens[1] };
	if (tokens.length === 1) return { token: tokens[0] };
	return {};
}

export function resolveDelegateToken(
	ledger: Ledger,
	token: string,
	targets: readonly DelegateTarget[],
): { taskId?: string; alias?: string } {
	if (!token) return {};
	const isTask = isValidTaskId(token) && taskRecordExists(ledger, token);
	const isAlias = targets.some((t) => t.alias === token);
	if (isTask && isAlias) {
		throw new Error(
			`refusing /op:delegate token '${token}': it is both a task id and a target alias; pass '/op:delegate <task-id> <alias>'`,
		);
	}
	if (isTask) return { taskId: token };
	if (isAlias) return { alias: token };
	throw new Error(
		`refusing /op:delegate token '${token}': not a task record under ${LEDGER_DIR}/tasks/ and not a configured target alias`,
	);
}

export interface TaskCreateOptions {
	taskId: string;
	objective: string;
	assign: string;
	review?: string;
}

export function taskCreateArgv(opts: TaskCreateOptions): string[] {
	requireTaskId(opts.taskId, "task-create");
	const objective = (opts.objective ?? "").trim();
	if (!objective) throw new Error("refusing task-create with an empty objective");
	const assign = requireHarnessId(opts.assign, "task-create --assign");
	const argv = ["task-create", "--id", opts.taskId, textFlag("--objective", objective), "--assign", assign];
	const review = (opts.review ?? "").trim();
	if (review) {
		refuseDualRole(assign, review, "task-create");
		argv.push("--review", requireHarnessId(review, "task-create --review"));
	}
	return assertSafeArgv(argv);
}

export function sessionStartArgv(taskId: string, harnessId: string): string[] {
	requireTaskId(taskId, "session-start");
	return assertSafeArgv(["session-start", "--task", taskId, "--harness", requireHarnessId(harnessId, "session-start --harness")]);
}

export function briefArgv(taskId: string, harnessId: string): string[] {
	requireTaskId(taskId, "brief");
	return assertSafeArgv(["brief", "--for", requireHarnessId(harnessId, "brief --for"), "--task", taskId]);
}

export function exportBriefArgv(taskId: string, harnessId: string): string[] {
	requireTaskId(taskId, "export-brief");
	return assertSafeArgv(["export-brief", "--for", requireHarnessId(harnessId, "export-brief --for"), "--task", taskId]);
}

export function exportBriefPath(ledger: Ledger, taskId: string, harnessId: string): string {
	return join(ledger.ledgerDir, "briefs", `${taskId}.${harnessId}.export.md`);
}

export function briefPath(ledger: Ledger, taskId: string, harnessId: string): string {
	return join(ledger.ledgerDir, "briefs", `${taskId}.${harnessId}.md`);
}

export function adapterPromptPath(
	ledger: Ledger,
	taskId: string,
	harnessId: string,
	format: DelegateBriefFormat,
): string {
	return format === "brief" ? briefPath(ledger, taskId, harnessId) : exportBriefPath(ledger, taskId, harnessId);
}

/** Directory containing harness_adapter.py, next to the real operator binary. */
export function adapterModuleRoot(ledger: Ledger): string {
	try {
		return dirname(realpathSync(ledger.operatorBin));
	} catch {
		return ledger.root;
	}
}

/**
 * Fixed python -c script that calls harness_adapter.invoke.
 *
 * User values travel as separate argv tokens after the script, never
 * interpolated into the -c string. IMPLEMENTER role only (POE-RUL-113).
 */
export const ADAPTER_INVOKE_SCRIPT = [
	"import sys",
	"from pathlib import Path",
	"sys.path.insert(0, sys.argv[1])",
	"import harness_adapter as ha",
	"carrier, model, brief_path, workspace = sys.argv[2:6]",
	"prompt = Path(brief_path).read_text(encoding='utf-8')",
	"result = ha.invoke(carrier, ha.Role.IMPLEMENTER, model, prompt, Path(workspace))",
	"print('adapter_exit_state=' + result.exit_state.value)",
	"print('adapter_returncode=' + ('' if result.returncode is None else str(result.returncode)))",
	"if result.stderr:",
	"    sys.stderr.write(result.stderr)",
	"    if not str(result.stderr).endswith('\\n'):",
	"        sys.stderr.write('\\n')",
].join("\n");

export interface AdapterInvokeOptions {
	moduleRoot: string;
	carrierId: string;
	model: string;
	briefPath: string;
	workspace: string;
}

export function adapterInvokeArgv(opts: AdapterInvokeOptions): string[] {
	const carrier = requireCarrierId(opts.carrierId);
	const model = requireModelId(opts.model, "adapter invoke");
	const moduleRoot = (opts.moduleRoot ?? "").trim();
	const brief = (opts.briefPath ?? "").trim();
	const workspace = (opts.workspace ?? "").trim();
	if (!moduleRoot) throw new Error("refusing adapter invoke without a module root");
	if (!brief) throw new Error("refusing adapter invoke without a brief path");
	if (!workspace) throw new Error("refusing adapter invoke without a workspace");
	for (const [name, value] of [
		["module root", moduleRoot],
		["brief path", brief],
		["workspace", workspace],
	] as const) {
		if (value.startsWith("-")) {
			throw new Error(`refusing adapter invoke ${name} '${value}': a path starting with '-' would be read as a flag`);
		}
	}
	return assertSafeAdapterArgv(["python3", "-c", ADAPTER_INVOKE_SCRIPT, moduleRoot, carrier, model, brief, workspace]);
}

export function assertSafeAdapterArgv(argv: string[]): string[] {
	if (argv[0] !== "python3" || argv[1] !== "-c" || argv[2] !== ADAPTER_INVOKE_SCRIPT) {
		throw new Error("refusing adapter invoke: argv is not the fixed harness_adapter IMPLEMENTER launcher");
	}
	if (argv.length !== 8) {
		throw new Error(`refusing adapter invoke: expected 8 argv tokens, got ${argv.length}`);
	}
	requireCarrierId(argv[4]);
	requireModelId(argv[5], "adapter invoke");
	for (const forbidden of FORBIDDEN_FLAGS) {
		for (const arg of argv) {
			if (arg === forbidden || arg.startsWith(`${forbidden}=`)) {
				throw new Error(`refusing to pass ${forbidden}: lifecycle authority is not an extension input`);
			}
		}
	}
	return argv;
}

export function formatAdapterInvocation(argv: string[]): string {
	if (argv[0] === "python3" && argv[1] === "-c") {
		return `python3 -c <harness_adapter IMPLEMENTER> ${argv.slice(3).join(" ")}`;
	}
	return argv.join(" ");
}

export type SessionStartFailure = "already_running" | "unrouted" | "missing_harness" | "other";

export function classifySessionStartError(stderr: string, stdout = ""): SessionStartFailure {
	const text = `${stderr}\n${stdout}`;
	if (/already running/i.test(text)) return "already_running";
	if (/neither assigned_harness nor review_harness/i.test(text) || /Brief generation failed/i.test(text)) {
		return "unrouted";
	}
	if (/Harness '.+' not found in harnesses/i.test(text)) return "missing_harness";
	return "other";
}

export function parseTaskCreate(stdout: string): string | null {
	const m = /Task '([^']+)' created successfully/.exec(stdout);
	return m ? m[1] : null;
}

export interface SessionStartSummary {
	taskId: string | null;
	briefPath: string | null;
	usageId: string | null;
}

export function parseSessionStart(stdout: string): SessionStartSummary {
	let taskId: string | null = null;
	let briefPath: string | null = null;
	let usageId: string | null = null;
	for (const line of splitLines(stdout)) {
		const session = /^SESSION INITIALIZED:\s+(\S+)/.exec(line);
		if (session) taskId = session[1];
		const brief = /^1\. Export brief written to:\s+(.+)$/.exec(line);
		if (brief) briefPath = brief[1].trim();
		const usage = /^2\. Usage placeholder recorded:\s+(usage-[0-9]+)/.exec(line);
		if (usage) usageId = usage[1];
	}
	return { taskId, briefPath, usageId };
}

export function parseAdapterInvoke(result: CommandResult): { exitState: string | null; returncode: string | null } {
	let exitState: string | null = null;
	let returncode: string | null = null;
	for (const line of splitLines(result.stdout)) {
		const st = /^adapter_exit_state=(.*)$/.exec(line);
		if (st) exitState = st[1].trim();
		const rc = /^adapter_returncode=(.*)$/.exec(line);
		if (rc) returncode = rc[1].trim() || null;
	}
	return { exitState, returncode };
}

export function chooserLabelForTarget(
	target: ResolvedDelegateTarget,
	route: DelegateRoute,
	assignedHarness: string | null,
	reviewHarness: string | null,
): string {
	const axes = [
		`harness=${target.harnessId}`,
		`carrier=${target.carrierId}`,
		`model=${target.model}`,
		`isolation=${target.isolation}`,
		`brief=${target.briefFormat}`,
	];
	if (target.harness.kind && target.harness.kind !== target.carrierId) {
		axes.push(`kind=${target.harness.kind}`);
	}
	if (target.harnessId === assignedHarness) axes.push("assigned_harness");
	if (target.harnessId === reviewHarness) axes.push("review_harness");
	const routeTag =
		route.action === "parent-routed"
			? "routed implementer — session-start on this task"
			: route.action === "child-task"
				? "not implementer-routed — child task with --assign"
				: "NOT SELECTABLE";
	return `${target.alias}  ${axes.join("  ")}  [${routeTag}]`;
}

export const DELEGATE_BOUNDARY_NOTES = [
	"Delegate sends bounded implementation work while this Pi session remains in the loop (POE-RUL-107).",
	"Ledger harness id, carrier/adapter id, model, isolation, and brief format are distinct axes (POE-RUL-004/108).",
	"Unrouted implementers require a scoped child task with explicit --assign. Parent assigned_harness and review_harness are not mutated (POE-RUL-001).",
	"A target that would be both implementer and reviewer is refused (POE-RUL-005).",
	"Primary path invokes harness_adapter in IMPLEMENTER role. Paste/export-only is a labeled fallback (POE-RUL-110).",
	"Nothing here verifies anything. --status, --verified-by and --verdict are not extension inputs (POE-RUL-113).",
] as const;

export const DELEGATE_DISPATCH_OPTIONS = [
	"adapter  Primary: invoke through harness_adapter IMPLEMENTER (brief on the command line)",
	"paste-fallback  Labeled fallback: export the brief for a human to paste (not the default)",
] as const;

export function parseDispatchChoice(picked: string): DelegateDispatchPath | null {
	const path = picked.trim().split(/\s+/)[0];
	if ((DELEGATE_DISPATCH_PATHS as readonly string[]).includes(path)) return path as DelegateDispatchPath;
	return null;
}

export interface DelegatePlanInput {
	parentTaskId: string;
	workTaskId: string;
	target: ResolvedDelegateTarget;
	route: DelegateRoute;
	childObjective?: string;
	childReview?: string | null;
	sessionAuthor?: string | null;
	assignedHarness?: string | null;
	reviewHarness?: string | null;
	dispatch: DelegateDispatchPath;
	dispatchReason: string;
}

export function describeDelegatePlan(opts: DelegatePlanInput): string[] {
	const lines = [
		`parent task:     ${opts.parentTaskId}`,
		`work task:       ${opts.workTaskId}${opts.workTaskId === opts.parentTaskId ? "  (parent; already implementer-routed)" : "  (scoped child; parent routing unchanged)"}`,
		`alias:           ${opts.target.alias}`,
		`ledger harness:  ${opts.target.harnessId}   (routing id under ${LEDGER_DIR}/harnesses/)`,
		`carrier/adapter: ${opts.target.carrierId}   (harness_adapter.PROFILES key; not the ledger id)`,
		`model:           ${opts.target.model}`,
		`isolation:       ${opts.target.isolation}${opts.target.isolation === "in-repo" ? "  (workspace = repository root)" : "  (auto worktree is not implemented)"}`,
		`brief format:    ${opts.target.briefFormat}`,
		`route:           ${opts.route.action} — ${opts.route.reason}`,
	];
	if (opts.target.commandTemplate) {
		lines.push(`command template: ${opts.target.commandTemplate}   (display only; never executed)`);
	}
	if (opts.target.harness.kind) {
		lines.push(`harness kind:    ${opts.target.harness.kind}   (record field; dispatch uses carrier id)`);
	}
	if (opts.sessionAuthor) {
		lines.push(`session --by:    ${opts.sessionAuthor}   (provenance only; not used as --harness/--assign)`);
	}
	if (opts.assignedHarness) lines.push(`parent assigned: ${opts.assignedHarness}`);
	if (opts.reviewHarness) {
		lines.push(`parent review:   ${opts.reviewHarness}   (routing metadata; not the implementer default)`);
	}
	if (opts.route.action === "child-task") {
		lines.push(`child --assign:  ${opts.target.harnessId}`);
		lines.push(`child --review:  ${opts.childReview?.trim() || "(none — not copied from the parent)"}`);
		if (opts.childObjective) lines.push(`child objective: ${truncate(opts.childObjective, 240)}`);
	}
	lines.push(`dispatch:        ${opts.dispatch} — ${opts.dispatchReason}`);
	if (opts.dispatch === "paste-fallback") {
		lines.push("", "LABELED FALLBACK: paste/export-only. This is not the primary adapter invocation path.");
	} else {
		lines.push("", "PRIMARY PATH: harness_adapter.invoke(carrier, IMPLEMENTER, model, brief, workspace).");
	}
	if (opts.target.isolation !== "in-repo") {
		lines.push("Isolation is not in-repo; adapter invoke will not silently run in the repository root.");
	}
	return lines;
}

export interface DelegateOutcome {
	parentTaskId: string;
	workTaskId: string;
	target: ResolvedDelegateTarget;
	route: DelegateRoute;
	dispatch: DelegateDispatchPath;
	dispatchReason: string;
	childCreated: boolean;
	parentAssignedHarness: string | null;
	parentReviewHarness: string | null;
	briefFile: string | null;
	usageId: string | null;
	adapterState: string | null;
	invocations: string[];
	results: CommandResult[];
}

export function buildDelegateReport(outcome: DelegateOutcome): Report {
	const operatorFailed = outcome.results.some((r) => r.code !== 0);
	const wroteLedger = outcome.childCreated || outcome.briefFile !== null || outcome.usageId !== null;
	const lines: string[] = [];
	if (outcome.childCreated) {
		lines.push(`Created scoped child task ${outcome.workTaskId} with --assign ${outcome.target.harnessId}.`);
		lines.push(
			`Parent ${outcome.parentTaskId} routing is unchanged (assigned=${outcome.parentAssignedHarness ?? "none"}, review=${outcome.parentReviewHarness ?? "none"}).`,
		);
	} else if (outcome.route.action === "parent-routed") {
		lines.push(`Used parent task ${outcome.parentTaskId}; ${outcome.target.harnessId} is already assigned_harness.`);
	}
	if (outcome.briefFile) lines.push(`Brief file: ${outcome.briefFile}`);
	if (outcome.usageId) lines.push(`Usage placeholder: ${outcome.usageId}`);
	if (outcome.dispatch === "adapter" && outcome.adapterState === "success") {
		lines.push("Dispatch path taken: adapter (primary). Paste/export was not used.");
	} else if (outcome.dispatch === "paste-fallback") {
		lines.push(`Dispatch path taken: LABELED FALLBACK (paste/export-only). ${outcome.dispatchReason}`);
		if (outcome.briefFile) {
			lines.push(
				`Paste the content of ${outcome.briefFile} into the ${outcome.target.harnessId} session if you proceed by hand.`,
			);
		}
	} else if (outcome.adapterState && outcome.adapterState !== "success") {
		lines.push(`Adapter reported ${outcome.adapterState}. ${outcome.dispatchReason}`);
	}
	for (const result of outcome.results) {
		if (result.code !== 0) {
			lines.push(`A wrapped command exited ${result.code}: ${truncate(result.stderr || result.stdout, 240)}`);
		}
	}
	lines.push("", ...DELEGATE_BOUNDARY_NOTES);
	const headline =
		outcome.dispatch === "adapter" && outcome.adapterState === "success"
			? `adapter → ${outcome.target.alias} on ${outcome.workTaskId}`
			: outcome.dispatch === "paste-fallback"
				? `fallback (paste) → ${outcome.target.alias} on ${outcome.workTaskId}`
				: operatorFailed
					? `failed on ${outcome.parentTaskId}`
					: `${outcome.route.action} → ${outcome.target.alias} on ${outcome.workTaskId}`;
	const level: ReportLevel =
		!wroteLedger && operatorFailed
			? "error"
			: outcome.dispatch === "paste-fallback"
				? "warning"
				: outcome.adapterState === "success"
					? "info"
					: operatorFailed
						? "error"
						: "info";
	return {
		command: "/op:delegate",
		title: "Operator delegate",
		headline,
		level,
		lines,
		invocations: outcome.invocations,
	};
}

export function decideDispatchPath(input: {
	requested: DelegateDispatchPath;
	isolation: DelegateIsolation;
	briefExists: boolean;
}): { path: DelegateDispatchPath; reason: string } {
	if (input.requested === "paste-fallback") {
		return { path: "paste-fallback", reason: "user chose the labeled paste/export fallback" };
	}
	if (input.isolation !== "in-repo") {
		return {
			path: "paste-fallback",
			reason: `isolation=${input.isolation} is not auto-created; refusing to silently run in-repo. Paste/export is the labeled fallback.`,
		};
	}
	if (!input.briefExists) {
		return { path: "paste-fallback", reason: "no brief file was written, so adapter invoke has nothing to dispatch" };
	}
	return { path: "adapter", reason: "in-repo isolation and a written brief; invoking harness_adapter IMPLEMENTER" };
}

