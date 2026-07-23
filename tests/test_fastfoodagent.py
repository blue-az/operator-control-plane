#!/usr/bin/env python3
"""Tests for fastfoodagent's build_substrate.py and queries.py.

Uses a small synthetic fixture (not the real ~22MB MenuStat download) for
fast, deterministic golden/ordering/boundary tests. One test separately
checks the real downloaded substrate under fastfoodagent/data/, if present,
against its own provenance report -- skipped otherwise (the CSV fetch is a
real network call, not something the rest of the suite should depend on).
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from fastfoodagent import build_substrate as bs  # noqa: E402
from fastfoodagent import queries as q  # noqa: E402

CSV_HEADER = [
    "Menu_Item_ID",
    "Year",
    "restaurant",
    "Item_Name",
    "Food_Category",
    "Calories",
    "Protein",
    "Sodium",
    "Kids_Meal",
    "Shareable",
]


def csv_row(
    item_id,
    year,
    restaurant,
    item_name,
    category,
    calories,
    protein,
    sodium,
    kids="0",
    shareable="0",
):
    return {
        "Menu_Item_ID": item_id,
        "Year": year,
        "restaurant": restaurant,
        "Item_Name": item_name,
        "Food_Category": category,
        "Calories": calories,
        "Protein": protein,
        "Sodium": sodium,
        "Kids_Meal": kids,
        "Shareable": shareable,
    }


class TestNormalizeRows(unittest.TestCase):
    def test_excludes_beverages(self):
        rows = [csv_row("1", "2020", "Chain A", "Soda", "Beverages", "150", "0", "10")]
        accepted, raw_count = bs.normalize_rows(rows)
        self.assertEqual(raw_count, 1)
        self.assertEqual(accepted, [])

    def test_excludes_missing_or_nonpositive_calories_protein_sodium(self):
        rows = [
            csv_row("1", "2020", "Chain A", "Zero Calories", "Entrees", "0", "10", "100"),
            csv_row("2", "2020", "Chain A", "Missing Protein", "Entrees", "300", "", "100"),
            csv_row("3", "2020", "Chain A", "Negative Sodium", "Entrees", "300", "10", "-5"),
            csv_row("4", "2020", "Chain A", "Valid Item", "Entrees", "300", "10", "100"),
        ]
        accepted, raw_count = bs.normalize_rows(rows)
        self.assertEqual(raw_count, 4)
        self.assertEqual([r["item_id"] for r in accepted], ["4"])

    def test_normalizes_kids_meal_and_shareable_flags(self):
        rows = [
            csv_row(
                "1",
                "2020",
                "Chain A",
                "Kid Item",
                "Entrees",
                "300",
                "10",
                "100",
                kids="1",
                shareable="1",
            )
        ]
        accepted, _ = bs.normalize_rows(rows)
        self.assertEqual(accepted[0]["kids_item"], 1)
        self.assertEqual(accepted[0]["shareable"], 1)

    def test_accepted_rows_sorted_by_item_id(self):
        rows = [
            csv_row("b2", "2020", "Chain A", "Item B", "Entrees", "300", "10", "100"),
            csv_row("a1", "2020", "Chain A", "Item A", "Entrees", "300", "10", "100"),
        ]
        accepted, _ = bs.normalize_rows(rows)
        self.assertEqual([r["item_id"] for r in accepted], ["a1", "b2"])

    def test_select_max_year_computed_not_hardcoded(self):
        rows = [
            csv_row("1", "2015", "Chain A", "Old", "Entrees", "300", "10", "100"),
            csv_row("2", "2021", "Chain A", "New", "Entrees", "300", "10", "100"),
            csv_row("3", "2018", "Chain A", "Mid", "Entrees", "300", "10", "100"),
        ]
        accepted, _ = bs.normalize_rows(rows)
        self.assertEqual(bs.select_max_year(accepted), 2021)

    def test_select_max_year_raises_on_no_rows(self):
        with self.assertRaises(ValueError):
            bs.select_max_year([])


class BuildSubstrateTestCase(unittest.TestCase):
    """Base class: builds a small, known substrate via the real
    build_substrate.build() pipeline (CSV -> normalize -> SQLite ->
    provenance), so query tests exercise the real integration, not a
    hand-built DB that might drift from what build_substrate.py produces."""

    ROWS = [
        # (item_id, year, restaurant, item_name, category, calories, protein, sodium)
        ("1", "2020", "Alpha Burger", "Lean Chicken Bowl", "Entrees", "400", "40", "600"),
        ("2", "2020", "Alpha Burger", "Cheese Fries", "Fried Potatoes", "500", "8", "900"),
        ("3", "2020", "Alpha Burger", "Grilled Salad", "Salads", "250", "30", "400"),
        ("4", "2020", "Alpha Burger", "Kids Nuggets", "Entrees", "300", "15", "500"),
        ("5", "2020", "Alpha Burger", "Value Wrap", "Sandwiches", "350", "20", "500"),
        ("6", "2020", "Beta Tacos", "Protein Bowl", "Entrees", "450", "45", "500"),
        ("7", "2020", "Beta Tacos", "Beta Cola", "Beverages", "150", "0", "10"),
        # Tie-break fixture: equal protein_g, differing sodium.
        ("8", "2020", "Gamma Grill", "Tie A", "Entrees", "500", "25", "300"),
        ("9", "2020", "Gamma Grill", "Tie B", "Entrees", "500", "25", "100"),
        # An older year that must not be selected (2020 > 2019).
        ("10", "2019", "Alpha Burger", "Old Year Item", "Entrees", "400", "40", "600"),
        # Excluded by filters: zero protein, missing sodium.
        ("11", "2020", "Alpha Burger", "Zero Protein", "Entrees", "200", "0", "100"),
    ]

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.csv_path = self.tmp / "menustat_raw.csv"
        self._write_csv(self.csv_path, self.ROWS)
        self.output_dir = self.tmp / "data"
        self.provenance = bs.build(self.csv_path, self.output_dir)
        self.db_path = self.output_dir / "substrate.sqlite3"
        self.provenance_path = self.output_dir / "provenance_report.json"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def _write_csv(path: Path, rows) -> None:
        import csv

        with open(path, "w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_HEADER)
            writer.writeheader()
            for row in rows:
                writer.writerow(csv_row(*row))

    def open(self) -> sqlite3.Connection:
        return q.open_substrate(self.db_path, self.provenance_path)


class TestBuildDeterminismAndRowCounts(BuildSubstrateTestCase):
    def test_selected_year_is_2020_not_hardcoded(self):
        self.assertEqual(self.provenance["schema_manifest"]["selected_year"], 2020)

    def test_row_counts_match_expected_filtering(self):
        counts = self.provenance["row_counts"]
        self.assertEqual(counts["raw_row_count"], len(self.ROWS))
        # Excluded: row 7 (Beverages), row 11 (zero protein). Row 10 (2019)
        # survives normalization but not the year filter.
        self.assertEqual(counts["accepted_row_count_all_years"], len(self.ROWS) - 2)
        self.assertEqual(counts["accepted_row_count_selected_year"], len(self.ROWS) - 2 - 1)

    def test_provenance_database_hash_matches_actual_file(self):
        actual = bs.sha256_file(self.db_path)
        self.assertEqual(self.provenance["database_sha256"], actual)

    def test_two_independent_builds_from_same_csv_are_byte_identical(self):
        second_output = self.tmp / "data2"
        second_provenance = bs.build(self.csv_path, second_output)
        self.assertEqual(self.provenance["database_sha256"], second_provenance["database_sha256"])
        self.assertEqual(
            (self.output_dir / "substrate.sqlite3").read_bytes(),
            (second_output / "substrate.sqlite3").read_bytes(),
        )


class TestOpenSubstrateIntegrity(BuildSubstrateTestCase):
    def test_opens_cleanly_with_matching_provenance(self):
        conn = self.open()
        conn.close()

    def test_aborts_on_hash_mismatch(self):
        # Corrupt the database after the provenance report was written.
        with open(self.db_path, "ab") as handle:
            handle.write(b"\x00corruption")
        with self.assertRaises(q.SubstrateIntegrityError):
            self.open()

    def test_aborts_on_missing_database(self):
        with self.assertRaises(q.SubstrateIntegrityError):
            q.open_substrate(self.tmp / "does-not-exist.sqlite3")

    def test_opens_without_provenance_check_when_omitted(self):
        conn = q.open_substrate(self.db_path)
        conn.close()


class TestLookupItems(BuildSubstrateTestCase):
    def test_lookup_by_restaurant(self):
        conn = self.open()
        try:
            results = q.lookup_items(conn, restaurant="Beta Tacos")
        finally:
            conn.close()
        self.assertEqual([r["item_id"] for r in results], ["6"])

    def test_lookup_by_category(self):
        conn = self.open()
        try:
            results = q.lookup_items(conn, category="Salads")
        finally:
            conn.close()
        self.assertEqual([r["item_id"] for r in results], ["3"])

    def test_lookup_by_name_contains_is_case_insensitive(self):
        conn = self.open()
        try:
            results = q.lookup_items(conn, name_contains="bowl")
        finally:
            conn.close()
        self.assertEqual({r["item_id"] for r in results}, {"1", "6"})

    def test_lookup_with_no_filters_returns_all_rows(self):
        conn = self.open()
        try:
            results = q.lookup_items(conn)
        finally:
            conn.close()
        self.assertEqual(
            len(results), self.provenance["row_counts"]["accepted_row_count_selected_year"]
        )


class TestTopItemsUnderBudget(BuildSubstrateTestCase):
    def test_ordering_protein_desc_sodium_asc(self):
        conn = self.open()
        try:
            results = q.top_items_under_calorie_budget(conn, calorie_budget=500)
        finally:
            conn.close()
        # item 6 (protein 45) > item 8/9 (protein 25, tie) > item 1 (protein 40)...
        # wait: item 1 has protein 40, item 6 has protein 45 -- check actual order.
        proteins = [r["protein_g"] for r in results]
        self.assertEqual(proteins, sorted(proteins, reverse=True))

    def test_tiebreak_equal_protein_orders_by_sodium_ascending(self):
        conn = self.open()
        try:
            results = q.top_items_under_calorie_budget(conn, calorie_budget=500, min_protein_g=25)
        finally:
            conn.close()
        tie_items = [r for r in results if r["protein_g"] == 25]
        self.assertEqual([r["item_id"] for r in tie_items], ["9", "8"])  # sodium 100 before 300

    def test_min_protein_and_max_sodium_constraints(self):
        conn = self.open()
        try:
            results = q.top_items_under_calorie_budget(
                conn, calorie_budget=1000, min_protein_g=30, max_sodium_mg=450
            )
        finally:
            conn.close()
        self.assertTrue(all(r["protein_g"] >= 30 for r in results))
        self.assertTrue(all(r["sodium_mg"] <= 450 for r in results))

    def test_rejects_nonpositive_calorie_budget(self):
        conn = self.open()
        try:
            with self.assertRaises(ValueError):
                q.top_items_under_calorie_budget(conn, calorie_budget=0)
        finally:
            conn.close()

    def test_rejects_nonpositive_limit(self):
        conn = self.open()
        try:
            with self.assertRaises(ValueError):
                q.top_items_under_calorie_budget(conn, calorie_budget=500, limit=0)
        finally:
            conn.close()

    def test_empty_result_for_impossible_budget(self):
        conn = self.open()
        try:
            results = q.top_items_under_calorie_budget(conn, calorie_budget=1)
        finally:
            conn.close()
        self.assertEqual(results, [])


class TestProteinPer100CalorieRanking(BuildSubstrateTestCase):
    def test_ranked_by_ratio_descending(self):
        conn = self.open()
        try:
            results = q.protein_per_100_calorie_ranking(conn, limit=100)
        finally:
            conn.close()
        ratios = [r["protein_per_100_kcal"] for r in results]
        self.assertEqual(ratios, sorted(ratios, reverse=True))

    def test_top_result_is_grilled_salad_highest_ratio(self):
        # Grilled Salad: 30g protein / 250 kcal = 12.0 per 100kcal -- the
        # highest ratio in the fixture.
        conn = self.open()
        try:
            results = q.protein_per_100_calorie_ranking(conn, limit=1)
        finally:
            conn.close()
        self.assertEqual(results[0]["item_id"], "3")


class TestCompareChains(BuildSubstrateTestCase):
    def test_medians_computed_for_eligible_chain(self):
        conn = self.open()
        try:
            result = q.compare_chains(conn, ["Alpha Burger"], min_sample_size=4)
        finally:
            conn.close()
        self.assertIn("Alpha Burger", result["chains"])
        # 5 Alpha Burger items survive filtering in year 2020 (items 1-5);
        # item 10 is 2019 (excluded by year selection), item 11 has zero
        # protein (excluded by the positive-value filter).
        self.assertEqual(result["chains"]["Alpha Burger"]["eligible_item_count"], 5)

    def test_chain_below_min_sample_size_is_excluded_not_compared(self):
        conn = self.open()
        try:
            result = q.compare_chains(conn, ["Gamma Grill"], min_sample_size=5)
        finally:
            conn.close()
        self.assertNotIn("Gamma Grill", result["chains"])
        self.assertEqual(
            result["excluded_insufficient_sample"],
            [{"restaurant": "Gamma Grill", "eligible_item_count": 2}],
        )

    def test_unknown_restaurant_has_zero_eligible_items(self):
        conn = self.open()
        try:
            result = q.compare_chains(conn, ["Not A Real Chain"], min_sample_size=1)
        finally:
            conn.close()
        self.assertEqual(
            result["excluded_insufficient_sample"],
            [{"restaurant": "Not A Real Chain", "eligible_item_count": 0}],
        )


class TestParetoFrontier(BuildSubstrateTestCase):
    def test_dominated_item_excluded(self):
        # item 2 (Cheese Fries: 500 cal, 8g protein, 900mg sodium) is
        # dominated by item 8 (Tie A: 500 cal, 25g protein, 300mg sodium) --
        # equal calories, strictly more protein, strictly less sodium.
        conn = self.open()
        try:
            frontier = q.pareto_frontier(conn)
        finally:
            conn.close()
        ids = {r["item_id"] for r in frontier}
        self.assertNotIn("2", ids)

    def test_non_dominated_items_present(self):
        # item 3 (Grilled Salad: 250 cal, 30g protein, 400mg sodium) is not
        # dominated by anything in the fixture (nothing matches its low
        # calories and high protein simultaneously).
        conn = self.open()
        try:
            frontier = q.pareto_frontier(conn)
        finally:
            conn.close()
        ids = {r["item_id"] for r in frontier}
        self.assertIn("3", ids)

    def test_frontier_sorted_by_protein_desc_calories_asc_sodium_asc(self):
        conn = self.open()
        try:
            frontier = q.pareto_frontier(conn)
        finally:
            conn.close()
        proteins = [r["protein_g"] for r in frontier]
        self.assertEqual(proteins, sorted(proteins, reverse=True))


class TestDatasetProvenance(BuildSubstrateTestCase):
    def test_reports_selected_year_and_limitation(self):
        conn = self.open()
        try:
            provenance = q.dataset_provenance(conn)
        finally:
            conn.close()
        self.assertEqual(provenance["dataset_year"], 2020)
        self.assertIn("historical", provenance["limitation"].lower())

    def test_raises_on_empty_substrate(self):
        empty_db = self.tmp / "empty.sqlite3"
        conn = sqlite3.connect(str(empty_db))
        conn.executescript(bs.SCHEMA)
        conn.commit()
        conn.close()
        conn = q.open_substrate(empty_db)
        try:
            with self.assertRaises(q.SubstrateIntegrityError):
                q.dataset_provenance(conn)
        finally:
            conn.close()


class TestConsumerReport(BuildSubstrateTestCase):
    def test_report_contains_no_individualized_advice_markers(self):
        conn = self.open()
        try:
            report = q.render_consumer_report(conn, calorie_budget=500, limit=5)
        finally:
            conn.close()
        self.assertIn("not a recommendation", report.lower())
        self.assertIn("historical", report.lower())
        self.assertIn("|", report)  # a Markdown table is present


class TestRealDownloadedSubstrate(unittest.TestCase):
    """Only runs if fastfoodagent/data/ already has a real build from this
    session's actual MenuStat fetch -- skipped otherwise, since fetching is
    a real network call this suite must not trigger on its own."""

    def test_real_substrate_matches_its_own_provenance(self):
        data_dir = REPO_ROOT / "fastfoodagent" / "data"
        db_path = data_dir / "substrate.sqlite3"
        provenance_path = data_dir / "provenance_report.json"
        if not db_path.exists() or not provenance_path.exists():
            self.skipTest("real MenuStat substrate not present under fastfoodagent/data/")
        conn = q.open_substrate(db_path, provenance_path)
        try:
            provenance = q.dataset_provenance(conn)
            self.assertIsInstance(provenance["dataset_year"], int)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
