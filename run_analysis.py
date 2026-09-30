#!/usr/bin/env python3
"""ForestSentinel Part 2: Fire Activity EDA, Hotspot & Priority-Zone Analysis Runner.

Reads validated active-fire records from Firebase Cloud Firestore, computes
Exploratory Data Analysis metrics, performs geographic grid-cell hotspot scoring,
and renders static charts, Folium HTML map, and comprehensive audit reports.

Usage:
    python run_analysis.py [--env-file PATH]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add src/ to sys.path to allow execution without prior pip install -e .
SRC_PATH = (Path(__file__).parent / "src").resolve()
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from forestsentinel.analysis_pipeline import ForestSentinelAnalysis
from forestsentinel.analytics_repository import NoDataError
from forestsentinel.config import load_config
from forestsentinel.firebase_client import FirebaseConfigError
from forestsentinel.pipeline import setup_logging


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="ForestSentinel Part 2: Fire Activity EDA, Hotspot Analysis & Priority-Zone Classification."
    )
    parser.add_argument(
        "--env-file",
        type=str,
        default=None,
        help="Optional custom path to .env file (defaults to .env in current directory).",
    )
    return parser.parse_args()


def main() -> int:
    """Main CLI entry point."""
    args = parse_args()

    print("=" * 72)
    print(" ForestSentinel - Fire Activity EDA & Priority-Zone Analysis (Part 2)")
    print("=" * 72)

    # 1. Load Configuration
    try:
        config = load_config(env_path=args.env_file)
    except ValueError as val_err:
        print("\n[CONFIG ERROR] Configuration validation failed:")
        print(f"  {val_err}\n")
        return 1

    # 2. Configure Logging
    log_file = setup_logging(config)
    print(f"[*] Logging active. Structured log saved to: {log_file}")

    # 3. Execute Part 2 Analysis Pipeline
    try:
        pipeline = ForestSentinelAnalysis(config=config)
        results = pipeline.run()
    except FirebaseConfigError as fb_err:
        print(f"\n[FIREBASE ERROR] Could not initialize Firebase Cloud Firestore:")
        print(f"  {fb_err}\n")
        return 1
    except NoDataError as nd_err:
        print(f"\n[NO DATA ERROR] Firestore collection empty:")
        print(f"  {nd_err}\n")
        return 1
    except Exception as exc:
        print(f"\n[ANALYSIS ERROR] Unexpected failure during Part 2 execution:")
        print(f"  {type(exc).__name__}: {exc}\n")
        return 1

    # 4. Print Concise Final Terminal Summary
    print("\n" + "=" * 72)
    print("ForestSentinel Part 2 analysis completed successfully.")
    print(f"Firestore records analyzed: {results['records_analyzed']}")
    print(f"Unique detection dates: {results['unique_dates_count']}")
    print(f"Grid cells analyzed: {results['grid_cells_analyzed']}")
    print(f"High-priority cells: {results['high_priority_cells']}")
    print(f"Medium-priority cells: {results['medium_priority_cells']}")
    print(f"Low-priority cells: {results['low_priority_cells']}")
    print(f"Charts directory: {results['charts_directory']}")
    print(f"Map: {results['map_path']}")
    print(f"Report: {results['md_report_path']}")
    print("=" * 72 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
