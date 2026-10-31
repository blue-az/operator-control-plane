"""Rebuild or verify the three Pi extension publication pages from pinned sources.

This tool does not read a .operator ledger and never deploys. Use --check for a
read-only comparison; --write intentionally updates only the three page files.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import html
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

OPERATOR_COMMIT = "85379b888a57bf99e3c37c62d8dfc4a0d8be636d"
PUBLISHER_COMMIT = "6c0a9ec6600773b78ee31117411a1ce01113a36c"
PBC_PATH = "owners-manual/pbc/appendix-pi-operator-extension.pbc.md"
BOARD_PARSER_PATH = "scripts/operator_project_board.py"
ORIGINAL_BOARD_PATH = "bulkhead-tau/reflect/operator-boards/pi-operator-extension.html"
OUTPUT_DIR = Path("bulkhead-tau/reflect/operator-boards")
MAIN_NAME = "pi-operator-extension.html"
ARCHIVE_NAME = "pi-operator-extension-historical-2026-09-16.html"
INVENTORY_NAME = "pi-operator-extension-source-inventory.html"
EXPECTED_PBC_SHA256 = "78a31947001d5bab2e456de41490f619200ffb5d34796b826fd637ad907c6941"
LOCAL_PATH = "/home/blueaz/Python/Evaluation/pbc-spec"


def git_show(repo: Path, revision: str, path: str) -> bytes:
    """Read one pinned Git blob without consulting the working tree."""
    return subprocess.check_output(["git", "-C", str(repo), "show", f"{revision}:{path}"])


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"expected one {label} source fragment, found {count}")
    return text.replace(old, new, 1)


def parse_inventory(operator_root: Path) -> tuple[bytes, list[dict[str, Any]]]:
    pbc = git_show(operator_root, OPERATOR_COMMIT, PBC_PATH)
    digest = hashlib.sha256(pbc).hexdigest()
    if digest != EXPECTED_PBC_SHA256:
        raise ValueError(f"pinned PBC hash mismatch: {digest}")

    parser_source = git_show(operator_root, OPERATOR_COMMIT, BOARD_PARSER_PATH)
    namespace: dict[str, Any] = {"__name__": "pi_extension_publication_parser"}
    exec(compile(parser_source, f"{OPERATOR_COMMIT}:{BOARD_PARSER_PATH}", "exec"), namespace)
    with tempfile.TemporaryDirectory() as temporary_directory:
        pbc_file = Path(temporary_directory) / "source.pbc.md"
        pbc_file.write_bytes(pbc)
        _, candidates = namespace["parse_pbc_lists"](pbc_file)
        inventory = namespace["parse_feature_inventory"](pbc_file, candidates)
    if len(inventory) != 17:
        raise ValueError(f"expected 17 PBC inventory rows, found {len(inventory)}")
    return pbc, inventory


def render_inventory_page(pbc: bytes, inventory: list[dict[str, Any]]) -> str:
    def escape(value: Any) -> str:
        return html.escape(str(value), quote=True)

    rows = "\n".join(
        f'<tr><th scope="row">{escape(item["id"])}</th>'
        f'<td>{escape(item.get("status", "Unknown"))}</td>'
        f'<td>{escape(item.get("basis") or item.get("description") or "")}</td></tr>'
        for item in inventory
    )
    pbc_sha256 = hashlib.sha256(pbc).hexdigest()
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pi extension — documented feature inventory</title>
<style>
  :root {{ --bg:#0f1419; --card:#1a222c; --ink:#e8eef4; --muted:#9aa8b4; --warn:#f5c542; --run:#59c2ff; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font:15px/1.45 ui-sans-serif,system-ui,sans-serif; background:var(--bg); color:var(--ink); }}
  header.top {{ padding:28px 32px 12px; }}
  .nav {{ color:var(--muted); margin-bottom:10px; }}
  .nav a, a {{ color:var(--run); text-decoration:none; }}
  .nav a:hover, a:hover {{ text-decoration:underline; }}
  h1 {{ margin:0 0 6px; font-size:28px; font-weight:650; }}
  .sub, .meta {{ color:var(--muted); }}
  main {{ padding:0 32px 48px; }}
  .notice {{ margin:0 0 18px; padding:14px 16px; background:#33280e; color:#ffebbd; border-left:4px solid var(--warn); border-radius:10px; }}
  .source-meta {{ color:var(--muted); overflow-wrap:anywhere; }}
  h2 {{ margin:24px 0 8px; font-size:19px; }}
  p {{ margin:0 0 14px; }}
  code {{ overflow-wrap:anywhere; color:#d5e9fa; }}
  .table-wrap {{ overflow-x:auto; background:var(--card); border-radius:12px; }}
  table {{ border-collapse:collapse; width:100%; min-width:960px; }}
  th, td {{ border-bottom:1px solid #3a4652; padding:12px 14px; text-align:left; vertical-align:top; }}
  thead th {{ background:#111820; color:var(--ink); }}
  tbody th {{ color:var(--run); white-space:nowrap; }}
  th:first-child {{ min-width:150px; }}
  td:nth-child(2) {{ min-width:220px; color:#dbe5ee; }}
  tbody tr:hover {{ background:#202b36; }}
  .history {{ background:var(--card); border-radius:12px; padding:16px; }}
  @media (max-width:700px) {{ header.top {{ padding:20px 16px 10px; }} main {{ padding:0 16px 32px; }} }}
</style></head><body>
<header class="top">
  <nav class="nav"><a href="{MAIN_NAME}">Main board</a></nav>
  <h1>Pi extension: documented feature inventory</h1>
  <p class="sub">Supplementary technical notes · frozen source snapshot · not a status dashboard</p>
</header>
<main>
<p class="notice"><strong>Supplementary, document-based inventory.</strong>
These 17 rows summarize what the pinned PBC says about planned Pi extension features. They do not show live task status. “Implemented” labels describe documentation and do not establish independent acceptance; use the main page for the dated board snapshot.</p>
<p class="source-meta">Frozen source commit: <code>{OPERATOR_COMMIT}</code>.
The source files are read directly from that commit, not from the working tree.</p>
<p class="source-meta">Inventory source: <code>{PBC_PATH}</code>, Candidate Reconciliation.
PBC SHA-256: <code>{pbc_sha256}</code>.</p>
<section class="history"><h2>Board snapshot</h2>
<p>The <a href="{MAIN_NAME}">main project board</a> shows the September 16, 2026 snapshot. Its task statuses and counts are historical, not current status. A separate <a href="{ARCHIVE_NAME}">archive copy</a> is retained for reference.</p></section>
<h2>Documented implementation and acceptance</h2>
<p>Status and basis below are copied from source documentation. “Implemented”, “local task verified”,
and owner-confirmed behavior do not imply independent acceptance. Missing acceptance information is unknown.
Historical feature IDs are not an active-work queue. No runtime tests were run to establish the statements below.</p>
<div class="table-wrap"><table><thead><tr><th>ID</th><th>Documented status</th><th>Documented basis / remaining scope</th></tr></thead>
<tbody>{rows}</tbody></table></div>
<p class="meta">This is supporting documentation, not a replacement for the board or a live project-status feed.</p>
</main>
</body></html>
'''


def render_board_pages(publisher_root: Path) -> tuple[str, str]:
    original_bytes = git_show(publisher_root, PUBLISHER_COMMIT, ORIGINAL_BOARD_PATH)
    if hashlib.sha256(original_bytes).hexdigest() != "4fdf602918b6ebc76101209fc6facdc8cf1ae9242258f01df9246b5eab78039a":
        raise ValueError("pinned historical board hash mismatch")
    original = original_bytes.decode("utf-8")
    original_nav = '<nav class="nav"><a href="pi-operator-extension.html">Project</a> · <a href="pi-operator-extension-issues.html">Issues</a> · <a href="pi-operator-extension-graph.html">Map</a></nav>'
    current_nav = original_nav[:-6] + ' · <a href="pi-operator-extension-source-inventory.html">Source inventory</a></nav>'
    historical_nav = '<nav class="nav"><a href="pi-operator-extension.html">Main board</a> · <a href="pi-operator-extension-issues.html">Historical issues</a> · <a href="pi-operator-extension-graph.html">Historical map</a> · <a href="pi-operator-extension-source-inventory.html">Source inventory</a></nav>'
    dated_subtitle = '<p class="sub">Simple Operator board · snapshot 2026-09-16 23:19 UTC · historical snapshot, not current status · not Graphify, not a knowledge graph</p>'

    redacted = replace_once(original, LOCAL_PATH, "repository", "local path")
    main_page = replace_once(redacted, original_nav, current_nav, "main navigation")
    main_page = replace_once(
        main_page,
        '<p class="sub">Simple Operator board · snapshot 2026-09-16 23:19 UTC · not Graphify, not a knowledge graph</p>',
        dated_subtitle,
        "main subtitle",
    )

    archive = replace_once(
        redacted,
        "<title>Operator board · pi-operator-extension</title>",
        "<title>Historical Operator board · pi-operator-extension · 2026-09-16</title>",
        "archive title",
    )
    archive_css = (
        "  .history-banner { margin:0; padding:9px 32px; background:var(--card); color:var(--muted); "
        "border-bottom:1px solid #445; font-size:13px; }\n"
        "  .history-banner a { color:var(--run); font-weight:650; }\n"
    )
    archive = replace_once(archive, "</style>", archive_css + "</style>", "archive CSS insertion point")
    archive_banner = (
        '<aside class="history-banner" role="note" aria-label="Historical snapshot">Archive copy · '
        '2026-09-16 23:19 UTC. Statuses are historical, not current. Return to the '
        f'<a href="{MAIN_NAME}">main board</a> or read the '
        f'<a href="{INVENTORY_NAME}">source inventory</a>.</aside>\n'
    )
    archive = replace_once(archive, "<body>\n", "<body>\n" + archive_banner, "archive banner insertion point")
    archive = replace_once(archive, original_nav, historical_nav, "archive navigation")
    archive = replace_once(archive, "<h1>pi-operator-extension</h1>", "<h1>pi-operator-extension — historical task snapshot</h1>", "archive heading")
    return main_page, archive


def render_pages(operator_root: Path, publisher_root: Path) -> dict[str, bytes]:
    pbc, inventory = parse_inventory(operator_root)
    main_page, archive_page = render_board_pages(publisher_root)
    inventory_page = render_inventory_page(pbc, inventory)
    if "file://" in main_page + archive_page + inventory_page:
        raise ValueError("generated output contains a file:// URL")
    if LOCAL_PATH in main_page + archive_page + inventory_page:
        raise ValueError("generated output contains a machine-local path")
    if "<script" in inventory_page.lower():
        raise ValueError("generated inventory must not contain scripts")
    return {
        f"{OUTPUT_DIR}/{MAIN_NAME}": main_page.encode("utf-8"),
        f"{OUTPUT_DIR}/{ARCHIVE_NAME}": archive_page.encode("utf-8"),
        f"{OUTPUT_DIR}/{INVENTORY_NAME}": inventory_page.encode("utf-8"),
    }


def check_or_write(publisher_root: Path, outputs: dict[str, bytes], write: bool) -> bool:
    mismatches: list[str] = []
    for relative_path, expected in outputs.items():
        destination = publisher_root / relative_path
        if write:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(expected)
            print(f"WROTE {relative_path} ({hashlib.sha256(expected).hexdigest()})")
            continue
        actual = destination.read_bytes() if destination.is_file() else b""
        if actual == expected:
            print(f"OK {relative_path} ({hashlib.sha256(expected).hexdigest()})")
        else:
            mismatches.append(relative_path)
            print(f"DIFF {relative_path}: expected {len(expected)} bytes, found {len(actual)}")
            if actual:
                diff = difflib.unified_diff(
                    actual.decode("utf-8").splitlines(),
                    expected.decode("utf-8").splitlines(),
                    fromfile=f"current/{relative_path}",
                    tofile=f"generated/{relative_path}",
                    lineterm="",
                )
                for line in list(diff)[:80]:
                    print(line)
    return not mismatches


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publisher-repo", type=Path, required=True, help="Public/Proto Git checkout")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true", help="compare without writing (default)")
    action.add_argument("--write", action="store_true", help="write only the three generated HTML pages")
    args = parser.parse_args()
    operator_root = Path(__file__).resolve().parents[1]
    publisher_root = args.publisher_repo.resolve()
    try:
        outputs = render_pages(operator_root, publisher_root)
        ok = check_or_write(publisher_root, outputs, write=args.write)
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    if args.write:
        print("Generated local HTML files only; no git commit, push, or deployment performed.")
        return 0
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
