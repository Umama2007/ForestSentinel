"""Pipeline orchestration module for ForestSentinel.

Coordinates the end-to-end ETL flow:
Config -> Supabase Run Init -> NASA FIRMS Extraction -> Pandas Transformation
-> Pydantic v2 Schema Validation -> Supabase Persistence -> Reporting.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from forestsentinel.config import Config, load_config
from forestsentinel.extractor import ExtractionError, FirmsExtractor
from forestsentinel.supabase_client import SupabaseClient, SupabaseConfigError
from forestsentinel.pdf_report import build_etl_pdf, try_build
from forestsentinel.reporter import generate_etl_report
from forestsentinel.schemas import validate_fire_records
from forestsentinel.transformer import FirmsTransformer

logger = logging.getLogger("forestsentinel")


def setup_logging(config: Config) -> Path:
    """Configure structured logging to both console and a timestamped file in logs/.

    Secrets are kept out of logging strings.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_file = config.logs_dir / f"forestsentinel_{timestamp}.log"

    log_level = getattr(logging, config.log_level.upper(), logging.INFO)

    # Root logger configuration for forestsentinel
    root_logger = logging.getLogger("forestsentinel")
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console Handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(log_level)
    ch.setFormatter(formatter)
    root_logger.addHandler(ch)

    # File Handler
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(log_level)
    fh.setFormatter(formatter)
    root_logger.addHandler(fh)

    return log_file


class ForestSentinelETL:
    """Main ETL pipeline orchestrator for active-fire / thermal-anomaly detections."""

    def __init__(
        self,
        config: Config,
        db_client: Optional[SupabaseClient] = None,
    ) -> None:
        """Initialize the pipeline with configuration and optional Supabase client."""
        self.config = config
        self.db = db_client or SupabaseClient(
            url=config.supabase_url,
            service_role_key=config.supabase_service_role_key,
        )
        self.extractor = FirmsExtractor(config=config)
        self.transformer = FirmsTransformer()

    def run(self) -> Dict[str, Any]:
        """Execute the complete ETL pipeline.

        Returns:
            Dictionary containing run summary and report paths.
        """
        logger.info("Initializing ForestSentinel ETL pipeline...")
        logger.info("Configuration: %s", self.config.redacted_repr())

        started_at = datetime.now(timezone.utc)
        run_metadata = {
            "api_source": self.config.firms_source,
            "study_bbox": self.config.amazon_bbox,
            "day_range": self.config.day_range,
        }

        # Step 1: Create ETL Run in Supabase
        run_id = self.db.create_etl_run(run_metadata)
        logger.info("Pipeline run initiated with Run ID: %s", run_id)

        try:
            # Step 2: Extract active-fire detections from NASA FIRMS API
            logger.info("Step 1/5: Extracting active-fire data from NASA FIRMS API...")
            raw_csv_path, raw_df = self.extractor.extract()

            # Step 3: Clean & Transform with Pandas
            logger.info("Step 2/5: Cleaning and transforming raw detections...")
            candidate_records, cleaning_rejections, stats = self.transformer.transform(raw_df)

            # Step 4: Validate with Pydantic v2
            logger.info("Step 3/5: Validating candidate records against Pydantic schema...")
            valid_records, pydantic_rejections = validate_fire_records(
                candidates=candidate_records,
                etl_run_id=run_id,
            )

            # Combine all rejected records for storage and auditing
            all_rejections = cleaning_rejections + pydantic_rejections

            # Step 5: Save to Supabase (Postgres)
            logger.info("Step 4/5: Persisting valid detections and audit logs into Supabase...")
            inserted_count, skipped_count = self.db.save_fire_detections(
                run_id=run_id,
                valid_records=valid_records,
            )
            saved_rejections_count = self.db.save_rejected_records(
                run_id=run_id,
                rejected_records=all_rejections,
            )

            finished_at = datetime.now(timezone.utc)
            duration_seconds = round((finished_at - started_at).total_seconds(), 2)

            counts = {
                "raw_rows_extracted": stats["total_raw_rows"],
                "exact_duplicates_removed": stats["exact_duplicates_removed"],
                "cleaning_rejections": len(cleaning_rejections),
                "pydantic_rejections": len(pydantic_rejections),
                "valid_records": len(valid_records),
                "inserted_records": inserted_count,
                "skipped_existing_records": skipped_count,
                "saved_rejections": saved_rejections_count,
            }

            # Finalize ETL Run in Supabase
            self.db.update_etl_run(
                run_id=run_id,
                updates={
                    "finished_at": finished_at.isoformat(),
                    "status": "completed",
                    **counts,
                    "error_message": None,
                },
            )

            # Step 6: Generate JSON & Markdown Reports
            logger.info("Step 5/5: Generating comprehensive ETL quality audit reports...")
            summary_payload = {
                "run_id": run_id,
                "status": "completed",
                "started_at": started_at.isoformat(),
                "finished_at": finished_at.isoformat(),
                "duration_seconds": duration_seconds,
                "api_source": self.config.firms_source,
                "study_bbox": self.config.amazon_bbox,
                "day_range": self.config.day_range,
                "database_project": self.config.database_project,
                "raw_csv_saved_at": str(raw_csv_path),
                "counts": counts,
                "rejected_sample": all_rejections[:5],
            }

            json_report, md_report = generate_etl_report(
                summary_data=summary_payload,
                reports_dir=self.config.reports_dir,
            )

            summary_payload["json_report_path"] = str(json_report)
            summary_payload["md_report_path"] = str(md_report)
            pdf_report = try_build(build_etl_pdf, summary_payload, json_report.with_suffix(".pdf"))
            summary_payload["pdf_report_path"] = str(pdf_report) if pdf_report else None

            logger.info("ForestSentinel ETL finished successfully in %.2fs!", duration_seconds)
            return summary_payload

        except Exception as exc:
            finished_at = datetime.now(timezone.utc)
            safe_error_msg = f"{type(exc).__name__}: {str(exc)}"
            logger.exception("Pipeline run %s failed: %s", run_id, safe_error_msg)

            # Attempt to update run doc in Supabase to failed
            try:
                self.db.update_etl_run(
                    run_id=run_id,
                    updates={
                        "finished_at": finished_at.isoformat(),
                        "status": "failed",
                        "error_message": safe_error_msg,
                    },
                )
            except Exception as db_err:
                logger.error("Failed to mark run as failed in Supabase: %s", db_err)

            raise
