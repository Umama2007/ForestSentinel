#!/usr/bin/env python3
"""ForestSentinel ETL Pipeline Runner.

Part 1: Active-fire / thermal-anomaly data pipeline from NASA FIRMS API
to Supabase (Postgres).

Usage:
    python run_pipeline.py [--env-file PATH]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add src/ to sys.path to allow execution without prior pip install -e .
SRC_PATH = (Path(__file__).parent / "src").resolve()
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from forestsentinel.config import load_config
from forestsentinel.extractor import ExtractionError
from forestsentinel.supabase_client import SupabaseConfigError
from forestsentinel.pipeline import ForestSentinelETL, setup_logging


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="ForestSentinel ETL: Ingest NASA FIRMS fire detections into Supabase (Postgres)."
    )
    parser.add_argument(
        "--env-file",
        type=str,
        default=None,
        help="Optional custom path to .env file (defaults to .env in current directory).",
    )
    return parser.parse_args()


def main() -> int:
    """Main execution function."""
    args = parse_args()

    print("=" * 70)
    print(" ForestSentinel - NASA FIRMS Fire Detection ETL Pipeline (Part 1)")
    print("=" * 70)

    # 1. Load and validate configuration
    try:
        config = load_config(env_path=args.env_file)
    except ValueError as val_err:
        print("\n[CONFIG ERROR] Configuration validation failed:")
        print(f"  {val_err}\n")
        print("Action required:")
        print("  1. Copy .env.example to .env: copy .env.example .env (Windows) or cp .env.example .env (macOS/Linux)")
        print("  2. Open .env and insert your real NASA_FIRMS_MAP_KEY, SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
        print("  3. Create the database tables by running supabase/schema.sql in the Supabase SQL Editor.\n")
        return 1

    # 2. Configure logging
    log_file = setup_logging(config)
    print(f"[*] Logging active. Structured log saved to: {log_file}")

    # 3. Execute ETL Pipeline
    try:
        pipeline = ForestSentinelETL(config=config)
        summary = pipeline.run()
    except SupabaseConfigError as db_err:
        print(f"\n[SUPABASE ERROR] Could not connect to Supabase (Postgres):")
        print(f"  {db_err}\n")
        return 1
    except ExtractionError as ext_err:
        print(f"\n[EXTRACTION ERROR] NASA FIRMS API extraction halted:")
        print(f"  {ext_err}\n")
        return 1
    except Exception as exc:
        print(f"\n[PIPELINE ERROR] Unexpected failure during ETL execution:")
        print(f"  {type(exc).__name__}: {exc}\n")
        return 1

    counts = summary.get("counts", {})
    run_id = summary.get("run_id", "N/A")
    extracted = counts.get("raw_rows_extracted", 0)
    valid = counts.get("valid_records", 0)
    inserted = counts.get("inserted_records", 0)
    rejected = counts.get("cleaning_rejections", 0) + counts.get("pydantic_rejections", 0)
    skipped = counts.get("skipped_existing_records", 0)
    md_report = summary.get("md_report_path", "N/A")

    print("\n" + "=" * 70)
    print("ForestSentinel ETL completed successfully.")
    print(f"Run ID: {run_id}")
    print(f"Extracted: {extracted}")
    print(f"Valid: {valid}")
    print(f"Inserted: {inserted}")
    print(f"Rejected: {rejected}")
    print(f"Skipped existing: {skipped}")
    print("Database: Supabase (Postgres)")
    print(f"Tables: fire_detections, rejected_records, etl_runs")
    print(f"Report: {md_report}")
    print("=" * 70 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
