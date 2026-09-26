/** Explicitly installed OpenCode TUI plugin; never a server plugin or model tool. */
import type { TuiPlugin, TuiPluginApi, TuiPluginModule } from "@opencode-ai/plugin/tui";
import { COMMANDS, OperatorController, type Dialogs } from "./controller.ts";
import { createRunner } from "./runner.ts";

/** Bound each native dialog to the terminal. All pages are shown, never ellipsized. */
export function pages(text: string, width = 72, height = 24): string[] {
	const columns = Math.max(8, Math.min(64, width - 12));
	const rows = Math.max(1, Math.min(12, height - 14));
	const safe = text.replace(/[\x00-\x08\x0b-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2066-\u2069]/g,
		(char) => `\\u${char.charCodeAt(0).toString(16).padStart(4, "0")}`);
	const lines = safe.split("\n").flatMap((line) => {
		const chars = Array.from(line.replace(/\t/g, "    "));
		const result: string[] = [];
		// Conservatively budget two terminal cells for non-ASCII text (CJK/emoji).
		const lineWidth = chars.some((char) => char.codePointAt(0)! > 0x7f) ? Math.max(1, Math.floor(columns / 2)) : columns;
		for (let i = 0; i < chars.length; i += lineWidth) result.push(chars.slice(i, i + lineWidth).join(""));
		return result.length ? result : [""];
	});
	const result: string[] = [];
	for (let i = 0; i < lines.length; i += rows) result.push(lines.slice(i, i + rows).join("\n"));
	return result;
}

export function dialogs(api: TuiPluginApi): Dialogs {
	const { ui, lifecycle } = api;
	function wait<T>(fallback: T, render: (finish: (value: T) => void) => ReturnType<typeof ui.DialogAlert>): Promise<T> {
		if (lifecycle.signal.aborted) return Promise.resolve(fallback);
		return new Promise((resolve) => {
			let settled = false;
			const finish = (value: T, clear = true) => {
				if (settled) return;
				settled = true;
				lifecycle.signal.removeEventListener("abort", abort);
				if (clear) ui.dialog.clear();
				resolve(value);
			};
			const abort = () => finish(fallback);
			lifecycle.signal.addEventListener("abort", abort, { once: true });
			ui.dialog.replace(() => render((value) => finish(value)), () => finish(fallback, false));
			ui.dialog.setSize("large");
		});
	}
	const paginate = (message: string) => pages(message, api.renderer.width, api.renderer.height);
	return {
		input(title, value = "") {
			return wait<string | undefined>(undefined, (finish) => ui.DialogPrompt({
				title, value, onConfirm: finish, onCancel: () => finish(undefined),
			}));
		},
		select(title, values) {
			return wait<string | undefined>(undefined, (finish) => ui.DialogSelect({
				title, options: values.map((value) => ({ title: value, value })),
				onSelect: (option) => finish(option.value),
			}));
		},
		async confirm(title, message) {
			if (api.renderer.width < 40 || api.renderer.height < 20) {
				ui.toast({ variant: "warning", message: "Resize the terminal to at least 40×20 before confirming a write." });
				return false;
			}
			const width = api.renderer.width;
			const height = api.renderer.height;
			const chunks = paginate(`${title}\n\n${message}`);
			for (let i = 0; i < chunks.length; i++) {
				const accepted = await wait(false, (finish) => ui.DialogConfirm({
					title: `Write ${i + 1}/${chunks.length}: ${i + 1 === chunks.length ? "execute" : "continue"}`,
					message: chunks[i], onConfirm: () => finish(true), onCancel: () => finish(false),
				}));
				if (!accepted) return false;
				if (api.renderer.width !== width || api.renderer.height !== height) {
					ui.toast({ variant: "warning", message: "Terminal size changed. Run the command again to review its confirmation." });
					return false;
				}
			}
			return true;
		},
		async show(title, message) {
			const chunks = paginate(message);
			for (let i = 0; i < chunks.length; i++) {
				const next = await wait(false, (finish) => ui.DialogAlert({
					title: `${title} — ${i + 1}/${chunks.length}`, message: chunks[i], onConfirm: () => finish(true),
				}));
				if (!next) break;
			}
		},
	};
}

const tui: TuiPlugin = async (api) => {
	if (!api.keymap?.registerLayer || !api.ui?.DialogConfirm || !api.lifecycle?.signal) {
		throw new Error("Operator requires the OpenCode TUI keymap/dialog plugin API (target: 1.18.22).");
	}
	const controller = new OperatorController(() => {
		const route = api.route.current;
		return {
			directory: api.state.path.directory,
			sessionID: route.name === "session" && typeof route.params?.sessionID === "string" ? route.params.sessionID : undefined,
		};
	}, dialogs(api), createRunner(api.lifecycle.signal), api.lifecycle.signal);
	api.keymap.registerLayer({
		commands: COMMANDS.map(([name, title]) => ({
			name: `operator.${name}`, title, category: "Operator", namespace: "palette", slashName: name,
			run: () => controller.run(name),
		})),
	});
};

const plugin: TuiPluginModule = { id: "operator.core", tui };
export default plugin;
