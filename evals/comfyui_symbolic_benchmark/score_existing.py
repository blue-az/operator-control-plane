#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
scores = json.loads((ROOT / "runs" / "20260825-existing" / "scores.json").read_text())
print("# ComfyUI symbolic constraint scores")
print()
print("| label | artifact/region | score | notes |")
print("|---|---|---:|---|")
for row in scores["scores"]:
    loc = row["artifact"]
    if row.get("region"):
        loc += f"#{row['region']}"
    notes = row["notes"].replace("|", "\\|")
    print(f"| {row['label']} | {loc} | {row['score']}/{row['max_score']} | {notes} |")
print()
print(f"Status: `{scores['status']}`")
