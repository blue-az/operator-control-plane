#!/usr/bin/env python3
"""Normalizes the raw MenuStat CSV into a frozen, deterministic SQLite
substrate: item_id, year, restaurant, item_name, category, calories,
protein_g, sodium_mg, kids_item, shareable.

Excludes beverages and any row missing a positive value for calories,
protein, or sodium. Selects the maximum year actually present in the data
(computed, never hardcoded). Emits substrate.sqlite3, schema_manifest.json,
row_counts.json, and provenance_report.json (source URL/date/bytes/SHA-256
plus the final database's own SHA-256).

Deterministic by construction: rows are inserted in a stable sort order and
the database is VACUUMed before hashing, so two independent builds from
byte-identical input CSVs produce byte-identical substrate.sqlite3 files.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Iterable, Optional

SCHEMA = """
CREATE TABLE items (
    item_id TEXT PRIMARY KEY,
    year INTEGER NOT NULL,
    restaurant TEXT NOT NULL,
    item_name TEXT NOT NULL,
    category TEXT NOT NULL,
    calories REAL NOT NULL,
    protein_g REAL NOT NULL,
    sodium_mg REAL NOT NULL,
    kids_item INTEGER NOT NULL,
    shareable INTEGER NOT NULL
);
"""

EXPECTED_COLUMNS = [
    "item_id",
    "year",
    "restaurant",
    "item_name",
    "category",
    "calories",
    "protein_g",
    "sodium_mg",
    "kids_item",
    "shareable",
]

EXCLUDED_CATEGORY = "Beverages"


def _to_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _to_bool01(value: Optional[str]) -> bool:
    return (value or "").strip() == "1"


def load_rows(csv_path: Path) -> Iterable[dict]:
    with open(csv_path, newline="", encoding="utf-8") as handle:
        yield from csv.DictReader(handle)


def normalize_rows(rows: Iterable[dict]) -> tuple[list[dict], int]:
    """Returns (accepted, raw_row_count). `accepted` is deterministically
    sorted by item_id -- callers must not depend on CSV row order."""
    accepted: list[dict] = []
    raw_count = 0
    for row in rows:
        raw_count += 1
        category = (row.get("Food_Category") or "").strip()
        if not category or category == EXCLUDED_CATEGORY:
            continue

        calories = _to_float(row.get("Calories"))
        protein = _to_float(row.get("Protein"))
        sodium = _to_float(row.get("Sodium"))
        if calories is None or calories <= 0:
            continue
        if protein is None or protein <= 0:
            continue
        if sodium is None or sodium <= 0:
            continue

        year_raw = (row.get("Year") or "").strip()
        if not year_raw:
            continue
        try:
            year = int(float(year_raw))
        except ValueError:
            continue

        item_id = (row.get("Menu_Item_ID") or "").strip()
        restaurant = (row.get("restaurant") or "").strip()
        item_name = (row.get("Item_Name") or "").strip()
        if not item_id or not restaurant or not item_name:
            continue

        accepted.append(
            {
                "item_id": item_id,
                "year": year,
                "restaurant": restaurant,
                "item_name": item_name,
                "category": category,
                "calories": calories,
                "protein_g": protein,
                "sodium_mg": sodium,
                "kids_item": 1 if _to_bool01(row.get("Kids_Meal")) else 0,
                "shareable": 1 if _to_bool01(row.get("Shareable")) else 0,
            }
        )

    accepted.sort(key=lambda r: r["item_id"])
    return accepted, raw_count


def select_max_year(rows: list[dict]) -> int:
    years = {r["year"] for r in rows}
    if not years:
        raise ValueError("no rows with a valid year survived filtering; cannot select a year")
    return max(years)


def build_database(db_path: Path, rows: list[dict]) -> None:
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT INTO items (item_id, year, restaurant, item_name, category, calories, "
            "protein_g, sodium_mg, kids_item, shareable) VALUES "
            "(:item_id, :year, :restaurant, :item_name, :category, :calories, :protein_g, "
            ":sodium_mg, :kids_item, :shareable)",
            rows,
        )
        conn.commit()
        # Canonicalizes the on-disk page layout so two independent builds
        # from the same input rows hash identically -- without this, page
        # allocation order alone can make otherwise-identical SQLite files
        # differ byte-for-byte.
        conn.execute("VACUUM")
    finally:
        conn.close()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(csv_path: Path, output_dir: Path, fetch_manifest: Optional[dict] = None) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    all_rows, raw_count = normalize_rows(load_rows(csv_path))
    max_year = select_max_year(all_rows)
    year_rows = sorted((r for r in all_rows if r["year"] == max_year), key=lambda r: r["item_id"])

    db_path = output_dir / "substrate.sqlite3"
    build_database(db_path, year_rows)

    schema_manifest = {
        "table": "items",
        "columns": EXPECTED_COLUMNS,
        "selected_year": max_year,
    }
    (output_dir / "schema_manifest.json").write_text(json.dumps(schema_manifest, indent=2))

    row_counts = {
        "raw_row_count": raw_count,
        "accepted_row_count_all_years": len(all_rows),
        "accepted_row_count_selected_year": len(year_rows),
    }
    (output_dir / "row_counts.json").write_text(json.dumps(row_counts, indent=2))

    provenance = {
        "fetch_manifest": fetch_manifest,
        "database_sha256": sha256_file(db_path),
        "schema_manifest": schema_manifest,
        "row_counts": row_counts,
    }
    (output_dir / "provenance_report.json").write_text(json.dumps(provenance, indent=2))
    return provenance


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the frozen MenuStat SQLite substrate.")
    parser.add_argument("--csv", required=True, help="Path to the raw MenuStat CSV.")
    parser.add_argument(
        "--output-dir",
        default="fastfoodagent/data",
        help="Directory to write substrate.sqlite3 and manifests.",
    )
    parser.add_argument(
        "--fetch-manifest",
        default=None,
        help="Path to fetch_manifest.json to fold into provenance_report.json.",
    )
    args = parser.parse_args()

    fetch_manifest = None
    if args.fetch_manifest:
        fetch_manifest = json.loads(Path(args.fetch_manifest).read_text())

    provenance = build(Path(args.csv), Path(args.output_dir), fetch_manifest)
    print(json.dumps(provenance, indent=2))


if __name__ == "__main__":
    main()
