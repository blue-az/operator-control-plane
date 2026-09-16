// pi-yank: yank a slice of a session message to the clipboard.
//
// Canonical source: this directory in operator-control-plane.
// Deployed copy/link: ~/.pi/agent/extensions/pi-yank/
//
// /yank [~N] [start] [end]
// Scoped by owners-manual/pbc/appendix-pi-yank-extension.pbc.md (PYY-RUL-101..107).
// Pinned harness: @earendil-works/pi-coding-agent 0.85.1
//   - session + clipboard APIs only: no CustomEditor, no transcript rendering,
//     no key handlers, no internal pi TUI APIs (the pi-vim-flash freeze class)

import {
	copyToClipboard,
	type ExtensionAPI,
	type ExtensionCommandContext,
} from "@earendil-works/pi-coding-agent";
import {
	parseYankArgs,
	selectMessage,
	sliceMessage,
	textFromMessage,
	type Copyable,
} from "./core.ts";

export { parseYankArgs, selectMessage, sliceMessage, textFromMessage };
export type { Copyable, YankParse, YankSliceResult } from "./core.ts";

function collectMessages(ctx: Pick<ExtensionCommandContext, "sessionManager">): Copyable[] {
	return ctx.sessionManager
		.getBranch()
		.flatMap((entry): Copyable[] => {
			if (entry === null || typeof entry !== "object") return [];
			const record = entry as Record<string, unknown>;
			if (record.type !== "message") return [];
			const message = record.message;
			if (message === null || typeof message !== "object") return [];
			const msg = message as Record<string, unknown>;
			const role = typeof msg.role === "string" ? msg.role : "message";
			const text = textFromMessage(msg);
			return text ? [{ role, text }] : [];
		});
}

function preview(text: string, span = 20): string {
	const flat = text.replace(/\s+/g, " ").trim();
	if (flat.length <= span * 2 + 1) return flat;
	const chars = Array.from(flat);
	const head = chars.slice(0, span).join("");
	const tail = chars.slice(chars.length - span).join("");
	return `${head} … ${tail}`;
}

async function handleYank(args: string | undefined, ctx: ExtensionCommandContext): Promise<void> {
	let parse;
	try {
		parse = parseYankArgs(args);
	} catch (error) {
		ctx.ui.notify(error instanceof Error ? error.message : "bad /yank arguments", "error");
		return;
	}

	const selected = selectMessage(collectMessages(ctx), parse.number);
	if (!selected.ok) {
		const warning =
			selected.reason.startsWith("No message #") ||
			selected.reason.startsWith("No assistant");
		ctx.ui.notify(selected.reason, warning ? "warning" : "error");
		return;
	}

	const result = sliceMessage(selected.target.text, parse.start, parse.end);
	if (!result.ok) {
		ctx.ui.notify(result.reason, "error");
		return;
	}

	try {
		await copyToClipboard(result.slice);
		ctx.ui.notify(
			`Yanked ${result.slice.length} chars from ${selected.label}: "${preview(result.slice)}"`,
			"info",
		);
	} catch (error) {
		ctx.ui.notify(error instanceof Error ? error.message : "Failed to copy to clipboard", "error");
	}
}

export default function piYankExtension(pi: Pick<ExtensionAPI, "registerCommand">): void {
	pi.registerCommand("yank", {
		description: 'Copy a slice of a session message to the clipboard: /yank [~N] ["start"] ["end"]',
		handler: async (args, ctx) => {
			await handleYank(args, ctx);
		},
	});
}
