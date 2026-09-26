import { execFile } from "node:child_process";
import type { ClientRunner } from "../../.pi/extensions/operator/client.ts";

/** Argv execution only. Never use a shell or execute stored verification commands. */
export function createRunner(signal?: AbortSignal): ClientRunner {
	return {
		exec(command, args, options) {
			return new Promise((resolve) => {
				const child = execFile(command, args, {
					cwd: options?.cwd,
					timeout: options?.timeout ?? 120_000,
					maxBuffer: 2 * 1024 * 1024,
					encoding: "utf8",
					signal,
				}, (error, stdout, stderr) => resolve({
					code: error ? (typeof error.code === "number" ? error.code : 1) : 0,
					stdout,
					stderr: [stderr, error?.message].filter(Boolean).join("\n"),
				}));
				// session-end consumes non-TTY stdin; send EOF rather than hanging.
				child.stdin?.end();
			});
		},
	};
}
