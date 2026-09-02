/**
 * TUI rendering for Operator reports.
 *
 * Split out from index.ts so that index.ts can load (and be tested) without
 * @earendil-works/pi-tui resolvable. pi aliases that package for extensions;
 * a bare node harness does not.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Box, Text } from "@earendil-works/pi-tui";
import { REPORT_ENTRY_TYPE, type Report, type ReportLevel } from "./core.ts";

function levelColor(level: ReportLevel): "success" | "warning" | "error" {
	if (level === "error") return "error";
	if (level === "warning") return "warning";
	return "success";
}

export function registerReportRenderer(pi: ExtensionAPI): void {
	pi.registerEntryRenderer<Report>(REPORT_ENTRY_TYPE, (entry, { expanded }, theme) => {
		const report = entry.data;
		if (!report) return undefined;
		const box = new Box(1, 0);
		box.addChild(
			new Text(
				`${theme.bold(report.title)} ${theme.fg("dim", report.command)}  ${theme.fg(levelColor(report.level), report.headline)}`,
			),
		);
		if (expanded) {
			box.addChild(new Text(report.lines.join("\n")));
			if (report.invocations.length > 0) {
				box.addChild(new Text(theme.fg("dim", report.invocations.map((i) => `$ ${i}`).join("\n"))));
			}
		} else {
			box.addChild(new Text(theme.fg("dim", "ctrl+o to expand")));
		}
		return box;
	});
}
