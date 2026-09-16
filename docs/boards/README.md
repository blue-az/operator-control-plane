# Operator boards

Very small static HTML snapshots of an Operator task-id prefix.

This is **not** Graphify. Graphify maps a repo into a knowledge graph.
These boards are one page: ladder, task cards, claim ratios, stale
`next_action`, recent PBC issues, and future features.

Regenerate from the local ledger:

```bash
python3 scripts/operator_project_board.py
python3 scripts/operator_project_board.py --view issues
python3 scripts/operator_project_board.py --view resolution --task pi-operator-extension-step5-dogfood
python3 scripts/operator_project_board.py --view obsidian
python3 scripts/operator_project_board.py --prefix pi-operator-extension -o docs/boards/pi-operator-extension.html
```

Then open the HTML in a browser. The file is a snapshot, not a live
server. `/op:project <prefix>` remains the in-Pi text dashboard.
