#!/usr/bin/env python3
"""Downloads the official NYC DOHMH MenuStat (historical) CSV once and
records retrieval provenance -- URL, retrieval date, byte count, SHA-256.
No nutrition parsing happens here; see build_substrate.py for that.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Confirmed live via a partial range fetch during planning: real columns
# include Menu_Item_ID, Year, restaurant, Item_Name, Food_Category, Calories,
# Protein, Sodium, Kids_Meal, Shareable (plus many unused columns).
MENUSTAT_CSV_URL = (
    "https://data.cityofnewyork.us/api/v3/views/qgc5-ecnb/export.csv?accessType=DOWNLOAD"
)


def fetch(output_dir: Path, url: str = MENUSTAT_CSV_URL) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "menustat_raw.csv"
    retrieved_at = datetime.now(timezone.utc).isoformat()

    with urllib.request.urlopen(url, timeout=120) as response:
        data = response.read()

    csv_path.write_bytes(data)
    manifest = {
        "source_url": url,
        "retrieved_at": retrieved_at,
        "byte_count": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "csv_path": str(csv_path),
    }
    (output_dir / "fetch_manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch the NYC DOHMH MenuStat CSV once.")
    parser.add_argument(
        "--output-dir",
        default="fastfoodagent/data",
        help="Directory to write the raw CSV and fetch manifest.",
    )
    parser.add_argument(
        "--url", default=MENUSTAT_CSV_URL, help="Override the source URL (mainly for tests)."
    )
    args = parser.parse_args()
    manifest = fetch(Path(args.output_dir), args.url)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
