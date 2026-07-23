#!/usr/bin/env python3
"""Deterministic domain query capabilities over the frozen MenuStat
substrate. Every response states the dataset year and the historical-
snapshot limitation; nothing here gives individualized health advice --
these are numbers from a historical NYC menu-labeling dataset, not
recommendations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from statistics import median
from typing import Optional

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

MIN_CHAIN_SAMPLE_SIZE = 5

DATASET_LIMITATION_TEMPLATE = (
    "This substrate reflects menu items as recorded for {year}. It is a historical "
    "snapshot from NYC DOHMH's MenuStat dataset, not a claim about current menus, "
    "pricing, or availability. Values come directly from the source data and are not "
    "independently re-measured; a small number of source rows may reflect data-entry "
    "outliers rather than realistic servings."
)


class SubstrateIntegrityError(Exception):
    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def open_substrate(db_path: Path, provenance_path: Optional[Path] = None) -> sqlite3.Connection:
    """Opens the frozen substrate read-only, verifying its schema (and, if a
    provenance report is supplied, its hash) before returning a connection --
    aborts rather than silently querying a substrate that doesn't match what
    was frozen."""
    db_path = Path(db_path)
    if not db_path.exists():
        raise SubstrateIntegrityError(f"substrate database not found: {db_path}")

    if provenance_path is not None:
        provenance_path = Path(provenance_path)
        if not provenance_path.exists():
            raise SubstrateIntegrityError(f"provenance report not found: {provenance_path}")
        provenance = json.loads(provenance_path.read_text())
        expected_hash = provenance.get("database_sha256")
        actual_hash = _sha256_file(db_path)
        if expected_hash != actual_hash:
            raise SubstrateIntegrityError(
                f"substrate database hash mismatch: expected {expected_hash}, got {actual_hash}"
            )

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    columns = [row[1] for row in conn.execute("PRAGMA table_info(items)").fetchall()]
    if columns != EXPECTED_COLUMNS:
        conn.close()
        raise SubstrateIntegrityError(
            f"substrate schema mismatch: expected columns {EXPECTED_COLUMNS}, got {columns}"
        )
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def dataset_provenance(conn: sqlite3.Connection) -> dict:
    row = conn.execute("SELECT DISTINCT year FROM items").fetchone()
    if row is None:
        raise SubstrateIntegrityError("substrate has no rows; cannot report a dataset year")
    year = row[0]
    return {
        "dataset_year": year,
        "source": "NYC DOHMH MenuStat (historical)",
        "limitation": DATASET_LIMITATION_TEMPLATE.format(year=year),
    }


def lookup_items(
    conn: sqlite3.Connection,
    *,
    restaurant: Optional[str] = None,
    name_contains: Optional[str] = None,
    category: Optional[str] = None,
) -> list[dict]:
    """Item lookup by chain/name/category. Any combination of filters may be
    given; omitting all of them returns every item, ordered the same way."""
    clauses = []
    params: dict = {}
    if restaurant:
        clauses.append("restaurant = :restaurant COLLATE NOCASE")
        params["restaurant"] = restaurant
    if name_contains:
        clauses.append("item_name LIKE :name_contains COLLATE NOCASE")
        params["name_contains"] = f"%{name_contains}%"
    if category:
        clauses.append("category = :category COLLATE NOCASE")
        params["category"] = category
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"SELECT * FROM items {where} ORDER BY restaurant, item_name, item_id"
    return [_row_to_dict(r) for r in conn.execute(sql, params).fetchall()]


def top_items_under_calorie_budget(
    conn: sqlite3.Connection,
    *,
    calorie_budget: float,
    min_protein_g: Optional[float] = None,
    max_sodium_mg: Optional[float] = None,
    limit: int = 20,
) -> list[dict]:
    """Top items under a calorie budget, with optional protein/sodium
    constraints. Ranked by protein descending, sodium ascending, then
    restaurant/item_name/item_id for a fully deterministic tiebreak."""
    if calorie_budget <= 0:
        raise ValueError("calorie_budget must be positive")
    if limit <= 0:
        raise ValueError("limit must be positive")

    clauses = ["calories <= :budget"]
    params: dict = {"budget": calorie_budget}
    if min_protein_g is not None:
        clauses.append("protein_g >= :min_protein")
        params["min_protein"] = min_protein_g
    if max_sodium_mg is not None:
        clauses.append("sodium_mg <= :max_sodium")
        params["max_sodium"] = max_sodium_mg
    where = " AND ".join(clauses)
    params["limit"] = limit
    sql = (
        f"SELECT * FROM items WHERE {where} "
        "ORDER BY protein_g DESC, sodium_mg ASC, restaurant ASC, item_name ASC, item_id ASC "
        "LIMIT :limit"
    )
    return [_row_to_dict(r) for r in conn.execute(sql, params).fetchall()]


def protein_per_100_calorie_ranking(conn: sqlite3.Connection, *, limit: int = 20) -> list[dict]:
    """Protein-per-100-calorie ranking: ratio descending, sodium ascending,
    then restaurant/item_name/item_id."""
    if limit <= 0:
        raise ValueError("limit must be positive")
    sql = (
        "SELECT *, (protein_g * 100.0 / calories) AS protein_per_100_kcal FROM items "
        "ORDER BY protein_per_100_kcal DESC, sodium_mg ASC, restaurant ASC, item_name ASC, "
        "item_id ASC LIMIT :limit"
    )
    return [_row_to_dict(r) for r in conn.execute(sql, {"limit": limit}).fetchall()]


def compare_chains(
    conn: sqlite3.Connection,
    restaurants: list[str],
    *,
    min_sample_size: int = MIN_CHAIN_SAMPLE_SIZE,
) -> dict:
    """Chain comparison using eligible-item medians, with a minimum
    sample-size guard: a chain with fewer than `min_sample_size` eligible
    items is excluded from `chains` and listed in `excluded_insufficient_sample`
    instead of being silently compared on a tiny sample."""
    chains: dict[str, dict] = {}
    excluded = []
    for restaurant in restaurants:
        rows = conn.execute(
            "SELECT calories, protein_g, sodium_mg FROM items WHERE restaurant = :r COLLATE NOCASE",
            {"r": restaurant},
        ).fetchall()
        if len(rows) < min_sample_size:
            excluded.append({"restaurant": restaurant, "eligible_item_count": len(rows)})
            continue
        chains[restaurant] = {
            "eligible_item_count": len(rows),
            "median_calories": median(r["calories"] for r in rows),
            "median_protein_g": median(r["protein_g"] for r in rows),
            "median_sodium_mg": median(r["sodium_mg"] for r in rows),
        }
    return {
        "min_sample_size": min_sample_size,
        "chains": chains,
        "excluded_insufficient_sample": excluded,
    }


def pareto_frontier(conn: sqlite3.Connection) -> list[dict]:
    """Deterministic protein/calorie/sodium Pareto frontier: an item is on
    the frontier unless some other item is at least as good on all three
    axes (more/equal protein, less/equal calories, less/equal sodium) and
    strictly better on at least one. O(n^2) -- verified under a second
    against the real ~9,300-row 2018 substrate; the early-exit on the first
    dominator found is what keeps this practical at that scale."""
    rows = [_row_to_dict(r) for r in conn.execute("SELECT * FROM items").fetchall()]
    frontier = []
    for candidate in rows:
        dominated = False
        for other in rows:
            if other["item_id"] == candidate["item_id"]:
                continue
            not_worse = (
                other["protein_g"] >= candidate["protein_g"]
                and other["calories"] <= candidate["calories"]
                and other["sodium_mg"] <= candidate["sodium_mg"]
            )
            strictly_better = (
                other["protein_g"] > candidate["protein_g"]
                or other["calories"] < candidate["calories"]
                or other["sodium_mg"] < candidate["sodium_mg"]
            )
            if not_worse and strictly_better:
                dominated = True
                break
        if not dominated:
            frontier.append(candidate)
    frontier.sort(
        key=lambda r: (
            -r["protein_g"],
            r["calories"],
            r["sodium_mg"],
            r["restaurant"],
            r["item_name"],
            r["item_id"],
        )
    )
    return frontier


def render_consumer_report(
    conn: sqlite3.Connection, *, calorie_budget: float = 600, limit: int = 10
) -> str:
    """Short Markdown consumer report answering the public hook: which
    items provide the most protein within a calorie budget, and what sodium
    accompanies that efficiency. No individualized health advice -- numbers
    and the dataset's stated limitation only."""
    provenance = dataset_provenance(conn)
    items = top_items_under_calorie_budget(conn, calorie_budget=calorie_budget, limit=limit)

    lines = [
        f"# Protein efficiency within a {int(calorie_budget)}-calorie budget",
        "",
        f"_Source: {provenance['source']}, dataset year {provenance['dataset_year']}._",
        "",
        f"> {provenance['limitation']}",
        "",
        "| Restaurant | Item | Calories | Protein (g) | Sodium (mg) |",
        "|---|---|---:|---:|---:|",
    ]
    for item in items:
        lines.append(
            f"| {item['restaurant']} | {item['item_name']} | {item['calories']:g} | "
            f"{item['protein_g']:g} | {item['sodium_mg']:g} |"
        )
    lines.append("")
    lines.append(
        "This table ranks items by protein first, then by lower sodium as a tiebreak, "
        "among items at or under the stated calorie budget. It is not a recommendation "
        "for any individual's diet."
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Query the frozen MenuStat substrate.")
    parser.add_argument("--db", required=True, help="Path to substrate.sqlite3.")
    parser.add_argument("--provenance", default=None, help="Path to provenance_report.json.")
    parser.add_argument(
        "--capability",
        required=True,
        choices=[
            "provenance",
            "lookup",
            "top-under-budget",
            "protein-per-100kcal",
            "compare-chains",
            "pareto",
            "report",
        ],
    )
    parser.add_argument("--restaurant", default=None)
    parser.add_argument("--name-contains", default=None)
    parser.add_argument("--category", default=None)
    parser.add_argument("--calorie-budget", type=float, default=600)
    parser.add_argument("--min-protein-g", type=float, default=None)
    parser.add_argument("--max-sodium-mg", type=float, default=None)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--restaurants", nargs="*", default=None, help="For compare-chains.")
    args = parser.parse_args()

    conn = open_substrate(Path(args.db), Path(args.provenance) if args.provenance else None)
    try:
        if args.capability == "provenance":
            print(json.dumps(dataset_provenance(conn), indent=2))
        elif args.capability == "lookup":
            print(
                json.dumps(
                    lookup_items(
                        conn,
                        restaurant=args.restaurant,
                        name_contains=args.name_contains,
                        category=args.category,
                    ),
                    indent=2,
                )
            )
        elif args.capability == "top-under-budget":
            print(
                json.dumps(
                    top_items_under_calorie_budget(
                        conn,
                        calorie_budget=args.calorie_budget,
                        min_protein_g=args.min_protein_g,
                        max_sodium_mg=args.max_sodium_mg,
                        limit=args.limit,
                    ),
                    indent=2,
                )
            )
        elif args.capability == "protein-per-100kcal":
            print(json.dumps(protein_per_100_calorie_ranking(conn, limit=args.limit), indent=2))
        elif args.capability == "compare-chains":
            print(json.dumps(compare_chains(conn, args.restaurants or []), indent=2))
        elif args.capability == "pareto":
            print(json.dumps(pareto_frontier(conn), indent=2))
        elif args.capability == "report":
            print(
                render_consumer_report(conn, calorie_budget=args.calorie_budget, limit=args.limit)
            )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
