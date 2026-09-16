// Pure /yank logic. No pi imports. PYY-RUL-101..105.

export interface YankParse {
	number?: number;
	start?: string;
	end?: string;
}

export type YankSliceResult =
	| { ok: true; slice: string }
	| { ok: false; reason: string };

export interface Copyable {
	role: string;
	text: string;
}

export function textFromMessage(message: Record<string, unknown>): string {
	if (message.role === "bashExecution") {
		const command = typeof message.command === "string" ? message.command : "";
		const output = typeof message.output === "string" ? message.output : "";
		return command ? `$ ${command}\n${output}`.trimEnd() : output;
	}
	if (message.role === "branchSummary" || message.role === "compactionSummary") {
		return typeof message.summary === "string" ? message.summary : "";
	}
	const content = message.content;
	if (typeof content === "string") return content;
	if (Array.isArray(content)) {
		return content
			.filter(
				(part): part is { type: string; text: string } =>
					typeof part === "object" &&
					part !== null &&
					(part as { type?: unknown }).type === "text" &&
					typeof (part as { text?: unknown }).text === "string",
			)
			.map((part) => part.text)
			.join("\n\n");
	}
	return "";
}

export function parseYankArgs(args: string | undefined): YankParse {
	const parse: YankParse = {};
	const input = (args ?? "").trim();
	const tokens: string[] = [];
	let current = "";
	let quote: string | undefined;
	let hasCurrent = false;
	for (const ch of input) {
		if (quote) {
			if (ch === quote) {
				quote = undefined;
			} else {
				current += ch;
			}
			continue;
		}
		if (ch === '"' || ch === "'") {
			quote = ch;
			hasCurrent = true;
			continue;
		}
		if (ch === " " || ch === "\t" || ch === "\n") {
			if (hasCurrent) {
				tokens.push(current);
				current = "";
				hasCurrent = false;
			}
			continue;
		}
		current += ch;
		hasCurrent = true;
	}
	if (hasCurrent) tokens.push(current);

	const anchors: string[] = [];
	for (const token of tokens) {
		const tilde = /^~(\d+)$/.exec(token);
		if (tilde) {
			parse.number = Number.parseInt(tilde[1], 10);
			continue;
		}
		anchors.push(token);
	}
	if (anchors[0] !== undefined) parse.start = anchors[0];
	if (anchors.length > 1) parse.end = anchors[1];
	if (anchors.length > 2) {
		throw new Error("too many anchors: use at most one start and one end");
	}
	return parse;
}

export function sliceMessage(text: string, start?: string, end?: string): YankSliceResult {
	const sliceStart = start !== undefined ? text.indexOf(start) : 0;
	if (start !== undefined && sliceStart === -1) {
		return { ok: false, reason: `start anchor not found: "${start}"` };
	}
	const endIdx = end !== undefined ? text.indexOf(end, sliceStart + 1) : undefined;
	if (end !== undefined && endIdx === -1) {
		return { ok: false, reason: `end anchor not found after start: "${end}"` };
	}
	const slice = end !== undefined ? text.slice(sliceStart, endIdx) : text.slice(sliceStart);
	if (slice.length === 0) {
		return { ok: false, reason: "message has no text to yank" };
	}
	return { ok: true, slice };
}

export function selectMessage(
	messages: Copyable[],
	number?: number,
): { ok: true; target: Copyable; label: string } | { ok: false; reason: string } {
	if (messages.length === 0) {
		return { ok: false, reason: "No copyable messages found in the current branch" };
	}
	if (number !== undefined) {
		if (!Number.isInteger(number) || number < 1) {
			return { ok: false, reason: "message number must be a positive integer (~N)" };
		}
		const target = messages[messages.length - number];
		if (!target) {
			return { ok: false, reason: `No message #${number} (found ${messages.length})` };
		}
		return { ok: true, target, label: `message #${number} (${target.role})` };
	}
	for (let i = messages.length - 1; i >= 0; i--) {
		if (messages[i].role === "assistant" && messages[i].text.trim()) {
			return { ok: true, target: messages[i], label: "latest assistant message" };
		}
	}
	return { ok: false, reason: "No assistant message with text found" };
}
