#!/usr/bin/env python3
"""ForestSentinel Part 3: Conservation Exposure Analysis Runner.

Identifies threatened animal species with recorded occurrences in or near
selected Amazon fire-activity priority zones (Medium & High priority cells from Part 2),
enriches conservation categories via IUCN Red List API v4 (where configured),
and produces privacy-safe conservation exposure scores, charts, reports, and a Folium map.

Usage:
    python run_conservation_analysis.py [--env-file PATH]
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
from forestsentinel.conservation_pipeline import ConservationPipeline
from forestsentinel.firebase_client import FirebaseConfigError
from forestsentinel.analytics_repository import NoDataError
from forestsentinel.pipeline import setup_logging


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="ForestSentinel Part 3: Conservation Exposure Analysis."
    )
    parser.add_argument(
        "--env-file",
        type=str,
        default=None,
        help="Optional custom path to .env file (defaults to .env in current directory).",
    )
    return parser.parse_args()


def main() -> int:
    """Main CLI entry point for Part 3 conservation analysis."""
    args = parse_args()

    print("=" * 72)
    print(" ForestSentinel - Conservation Exposure Analysis (Part 3)")
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

    # 3. Check and notify IUCN API token status
    if not config.iucn_api_token:
        print("\n[NOTICE] IUCN enrichment was skipped because IUCN_API_TOKEN is not configured. No species has been classified as threatened in this run.\n")

    # 4. Execute Conservation Pipeline
    try:
        pipeline = ConservationPipeline(config=config)
        results = pipeline.run()

        # Format output paths relative to project root for clean terminal display
        base_dir = config.base_dir
        try:
            rel_report = Path(results["report_md_path"]).relative_to(base_dir).as_posix()
        except ValueError:
            rel_report = str(results["report_md_path"])

        try:
            rel_map = Path(results["map_html_path"]).relative_to(base_dir).as_posix()
        except ValueError:
            rel_map = str(results["map_html_path"])

        print("\nForestSentinel Part 3 conservation analysis completed successfully.")
        print(f"Fire-priority grid cells considered: {results['priority_cells_considered']}")
        print(f"GBIF occurrence records received: {results['gbif_occurrence_records_received']}")
        print(f"Unique animal species found: {results['unique_animal_species_found']}")
        print(f"IUCN statuses verified: {results['species_with_verified_iucn_status']}")
        print(f"Verified threatened species: {results['threatened_species_found']}")
        print(f"High conservation-priority summaries: {results['high_conservation_priority_count']}")
        print(f"Report: {rel_report}")
        print(f"Map: {rel_map}\n")
        return 0

    except FirebaseConfigError as fb_err:
        print(f"\n[FIREBASE ERROR] Credentials issue: {fb_err}\n")
        return 1
    except NoDataError as nd_err:
        print(f"\n[DATA ERROR] No fire detections found: {nd_err}\n")
        return 1
    except KeyboardInterrupt:
        print("\n[ABORTED] Pipeline execution cancelled by user.")
        return 130
    except Exception as exc:
        print(f"\n[PIPELINE ERROR] Conservation analysis failed: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
