"""Conservation Pipeline orchestration module for ForestSentinel.

Coordinates Part 3 end-to-end execution:
1. Recomputes Part 2 grid priority zones from validated fire detections in Supabase
2. Queries GBIF Occurrence Search API for Medium and High priority fire grid cells
3. Normalizes and deduplicates animal records into privacy-safe species summaries
4. Enriches with IUCN Red List categories (when IUCN_API_TOKEN is configured)
5. Computes explainable Conservation Exposure Priority Scores
6. Persists aggregated summaries and audit metrics to Supabase
7. Renders privacy-safe charts and Folium map artifact
8. Generates comprehensive JSON and Markdown audit reports
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from forestsentinel.analytics_repository import AnalyticsRepository
from forestsentinel.analyzer import FireActivityAnalyzer
from forestsentinel.config import Config, load_config
from forestsentinel.conservation_analyzer import ConservationAnalyzer
from forestsentinel.conservation_reporter import generate_conservation_report
from forestsentinel.pdf_report import build_conservation_pdf, load_json, try_build
from forestsentinel.conservation_repository import ConservationRepository
from forestsentinel.conservation_visualizer import ConservationVisualizer
from forestsentinel.supabase_client import SupabaseClient
from forestsentinel.gbif_client import GBIFClient
from forestsentinel.iucn_client import IUCNClient
from forestsentinel.priority_scoring import PriorityScorer

logger = logging.getLogger("forestsentinel.conservation")


class ConservationPipeline:
    """Orchestrates Part 3 Conservation Exposure Analysis pipeline."""

    def __init__(
        self,
        config: Config,
        db_client: Optional[SupabaseClient] = None,
        gbif_client: Optional[GBIFClient] = None,
        iucn_client: Optional[IUCNClient] = None,
    ) -> None:
        """Initialize pipeline with configuration and optional injected clients.

        Args:
            config: Validated Config instance.
            db_client: Optional SupabaseClient instance.
            gbif_client: Optional GBIFClient instance.
            iucn_client: Optional IUCNClient instance.
        """
        self.config = config
        self.db = db_client or SupabaseClient(
            url=config.supabase_url,
            service_role_key=config.supabase_service_role_key,
        )
        self.analytics_repo = AnalyticsRepository(db_client=self.db)
        self.cons_repo = ConservationRepository(db_client=self.db)

        self.gbif_client = gbif_client or GBIFClient(
            max_records_per_grid=config.gbif_max_records_per_grid,
            request_timeout_seconds=config.gbif_request_timeout_seconds,
        )

        self.iucn_client = iucn_client or IUCNClient(
            api_token=config.iucn_api_token,
            base_url=config.iucn_api_base_url,
            repository=self.cons_repo,
        )

        self.scorer = PriorityScorer(grid_size_degrees=config.grid_size_degrees)
        self.analyzer = ConservationAnalyzer(
            gbif_client=self.gbif_client,
            iucn_client=self.iucn_client,
        )

    def run(self) -> Dict[str, Any]:
        """Execute the complete Part 3 Conservation Exposure Analysis pipeline.

        Returns:
            Dictionary containing audit metrics, report paths, and artifact locations.
        """
        logger.info("Initializing ForestSentinel Part 3 Conservation Analysis...")
        start_time = datetime.now(timezone.utc)
        timestamp_str = start_time.strftime("%Y%m%d_%H%M%S")

        # 1. Recompute Part 2 grid priority metrics from Supabase fire_detections
        logger.info("Step 1/6: Recomputing fire-activity priority zones from Supabase...")
        raw_detections = self.analytics_repo.load_fire_detections()
        # Same study window as Part 2, so GBIF is queried for the cells the analysis ranked.
        analyzer = FireActivityAnalyzer(raw_detections, window_days=self.config.day_range)
        enriched_detections = self.scorer.assign_grid_cells(analyzer.df)
        grid_df, grid_metadata = self.scorer.compute_grid_metrics(enriched_detections)

        priority_cells_df = self.analyzer.filter_priority_cells(grid_df)
        priority_cell_count = len(priority_cells_df)

        # 2. Create Conservation Run Record in Supabase
        run_id = self.cons_repo.create_run({
            "source_fire_analysis_run": "recomputed_from_fire_detections",
            "grid_size_degrees": self.config.grid_size_degrees,
            "priority_cells_considered": priority_cell_count,
        })

        try:
            # 3. Execute Biodiversity Occurrence Extraction & Conservation Scoring
            logger.info("Step 2/6: Querying GBIF & performing conservation exposure analysis...")
            analysis_results = self.analyzer.run_analysis(
                grid_df=grid_df,
                grid_size_degrees=self.config.grid_size_degrees,
            )

            # 4. Save Privacy-Safe Aggregated Summaries to Supabase
            logger.info("Step 3/6: Persisting aggregated species summaries to Supabase...")
            summaries_to_save = analysis_results.get("species_grid_summaries", [])
            saved_count = self.cons_repo.save_species_grid_summaries(
                run_id=run_id,
                summaries=summaries_to_save,
            )

            # 5. Generate Privacy-Safe Charts and Folium Map Artifact
            logger.info("Step 4/6: Rendering static charts and Folium map artifact...")
            run_output_dir = self.config.reports_dir / "conservation" / timestamp_str
            run_output_dir.mkdir(parents=True, exist_ok=True)

            visualizer = ConservationVisualizer(output_dir=run_output_dir)
            artifact_paths = visualizer.render_all(
                grid_cells_df=grid_df,
                analysis_results=analysis_results,
                grid_size_degrees=self.config.grid_size_degrees,
            )

            # 6. Generate JSON and Markdown Conservation Reports
            logger.info("Step 5/6: Generating comprehensive conservation audit reports...")
            json_report, md_report = generate_conservation_report(
                analysis_results=analysis_results,
                artifact_paths=artifact_paths,
                output_dir=run_output_dir,
                database_project=self.config.database_project,
                run_id=run_id,
                iucn_configured=self.iucn_client.is_configured,
            )
            artifact_paths["conservation_report_json"] = json_report
            artifact_paths["conservation_report_md"] = md_report
            pdf_report = try_build(build_conservation_pdf, load_json(json_report), run_output_dir,
                                   run_output_dir / "conservation_report.pdf")
            if pdf_report:
                artifact_paths["conservation_report_pdf"] = pdf_report

            # 7. Finalize Run Record in Supabase
            finish_time = datetime.now(timezone.utc)
            self.cons_repo.update_run(run_id, {
                "finished_at": finish_time.isoformat(),
                "status": "completed",
                "gbif_requests_made": analysis_results.get("gbif_requests_made", 0),
                "gbif_occurrence_records_received": analysis_results.get("gbif_occurrence_records_received", 0),
                "unique_animal_species_found": analysis_results.get("unique_animal_species_found", 0),
                "species_with_verified_iucn_status": analysis_results.get("species_with_verified_iucn_status", 0),
                "threatened_species_found": analysis_results.get("threatened_species_found", 0),
                "aggregated_grid_species_records_saved": saved_count,
            })

            duration = round((finish_time - start_time).total_seconds(), 2)
            logger.info("ForestSentinel Part 3 Conservation Analysis completed in %.2fs!", duration)

            return {
                "run_id": run_id,
                "duration_seconds": duration,
                "priority_cells_considered": priority_cell_count,
                "gbif_occurrence_records_received": analysis_results.get("gbif_occurrence_records_received", 0),
                "unique_animal_species_found": analysis_results.get("unique_animal_species_found", 0),
                "species_with_verified_iucn_status": analysis_results.get("species_with_verified_iucn_status", 0),
                "threatened_species_found": analysis_results.get("threatened_species_found", 0),
                "high_conservation_priority_count": analysis_results.get("high_conservation_priority_count", 0),
                "aggregated_records_saved": saved_count,
                "iucn_configured": self.iucn_client.is_configured,
                "report_md_path": md_report,
                "report_json_path": json_report,
                "map_html_path": artifact_paths.get("conservation_exposure_map"),
                "artifact_paths": artifact_paths,
            }

        except Exception as exc:
            logger.error("Part 3 Conservation Analysis failed: %s", exc)
            try:
                self.cons_repo.update_run(run_id, {
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "status": "failed",
                    "error_message": str(exc),
                })
            except Exception as update_err:
                logger.error("Failed recording failure status in Supabase: %s", update_err)
            raise
