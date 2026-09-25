# Operator boards

Very small static HTML snapshots of an Operator task-id prefix.

This is **not** Graphify. Graphify maps a repo into a knowledge graph.
These boards are one page: ladder, task cards, claim ratios, stale
`next_action`, recent PBC issues, and future features.

The Operator-wide hub is `docs/boards/operator.html`; regenerate it with:

```bash
python3 scripts/operator_hub.py
```

Regenerate a prefix board from the local ledger:

```bash
python3 scripts/operator_project_board.py
python3 scripts/operator_project_board.py --view issues
python3 scripts/operator_project_board.py --view resolution --task pi-operator-extension-step5-dogfood
python3 scripts/operator_project_board.py --view obsidian
python3 scripts/operator_project_board.py --prefix pi-operator-extension -o docs/boards/pi-operator-extension.html
```

Then open the HTML in a browser. The file is a snapshot, not a live
server. `/op:project <prefix>` remains the in-Pi text dashboard.

## Where the HTML lives

Only the generators are public. Board HTML carries ledger detail and
local dashboard links, so it is not tracked here: `docs/boards/.gitignore`
ignores `*.html` and `obsidian/`. The generators still write to
`docs/boards/` by default, so a regenerated board is a local, ignored
file. Do not force-add it.

The canonical committed copies live in the private Python repo under
`project-phoenix/magic_bridge/operator_boards/`.

Snapshots committed before 3825655, including the 18 board HTML files in
the `v0.1.0-alpha.1` tag, remain in public history. A Git install from
that tag includes them. The packed frontend's allowlist excludes them,
but it does not filter a clone. The tag is intentionally left unchanged.
