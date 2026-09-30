"""Analysis Pipeline orchestration module for ForestSentinel.

Coordinates the end-to-end Part 2 analysis flow:
1. Load configuration
2. Securely initialize Firebase Client
3. Load fire detections from Firestore via AnalyticsRepository
4. Execute EDA with FireActivityAnalyzer
5. Perform grid-cell spatial tessellation & explainable priority scoring
6. Render static charts & interactive Folium map artifact with Visualizer
7. Generate JSON & Markdown audit reports with AnalysisReporter
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from forestsentinel.analysis_reporter import generate_analysis_report
from forestsentinel.analytics_repository import AnalyticsRepository, NoDataError
from forestsentinel.analyzer import FireActivityAnalyzer
from forestsentinel.config import Config, load_config
from forestsentinel.firebase_client import FirebaseClient, FirebaseConfigError
from forestsentinel.priority_scoring import PriorityScorer
from forestsentinel.visualizer import Visualizer

logger = logging.getLogger("forestsentinel.analysis")


class ForestSentinelAnalysis:
    """Orchestrates Part 2: Fire Activity EDA, Hotspot Aggregation, and Priority Scoring."""

    def __init__(
        self,
        config: Config,
        firebase_client: Optional[FirebaseClient] = None,
    ) -> None:
        """Initialize analysis pipeline with configuration and optional injected FirebaseClient."""
        self.config = config
        self.fb_client = firebase_client or FirebaseClient(
            service_account_path=config.firebase_service_account_path,
            project_id=config.firebase_project_id,
        )
        self.repository = AnalyticsRepository(firebase_client=self.fb_client)
        self.scorer = PriorityScorer(grid_size_degrees=config.grid_size_degrees)

    def run(self) -> Dict[str, Any]:
        """Execute the complete Part 2 analysis pipeline.

        Returns:
            Dictionary containing analysis metrics, report paths, and artifact locations.
        """
        logger.info("Initializing ForestSentinel Part 2 Analysis Pipeline...")
        start_time = datetime.now(timezone.utc)

        # 1. Read fire detections from Firestore
        logger.info("Step 1/5: Loading fire detections from Cloud Firestore...")
        df = self.repository.load_fire_detections()

        # 2. Run Exploratory Data Analysis
        logger.info("Step 2/5: Performing Exploratory Data Analysis...")
        analyzer = FireActivityAnalyzer(df)
        eda_results = analyzer.run_full_eda()

        # 3. Grid-Cell Hotspot Construction & Priority Scoring
        logger.info("Step 3/5: Computing grid cells and explainable priority scores...")
        enriched_df = self.scorer.assign_grid_cells(analyzer.df)
        grid_df, grid_metadata = self.scorer.compute_grid_metrics(enriched_df)

        # 4. Generate Visualizations & Interactive Map Artifact
        timestamp_str = start_time.strftime("%Y%m%d_%H%M%S")
        charts_dir = self.config.reports_dir / "charts" / timestamp_str
        logger.info("Step 4/5: Rendering static charts and Folium map artifact in '%s'...", charts_dir)
        visualizer = Visualizer(output_dir=charts_dir)
        artifacts = visualizer.render_all(
            detections_df=enriched_df,
            grid_df=grid_df,
            grid_size=self.config.grid_size_degrees,
        )

        # 5. Generate JSON and Markdown Analysis Reports
        logger.info("Step 5/5: Generating comprehensive analysis audit reports...")
        json_report, md_report = generate_analysis_report(
            eda_results=eda_results,
            grid_df=grid_df,
            grid_metadata=grid_metadata,
            artifact_paths=artifacts,
            reports_dir=self.config.reports_dir,
            firebase_project_id=self.config.firebase_project_id,
        )

        duration = round((datetime.now(timezone.utc) - start_time).total_seconds(), 2)
        logger.info("ForestSentinel Part 2 Analysis successfully completed in %.2fs!", duration)

        return {
            "records_analyzed": len(df),
            "unique_dates_count": eda_results["overview"]["unique_detection_dates_count"],
            "grid_cells_analyzed": len(grid_df),
            "high_priority_cells": grid_metadata["high_priority_count"],
            "medium_priority_cells": grid_metadata["medium_priority_count"],
            "low_priority_cells": grid_metadata["low_priority_count"],
            "charts_directory": str(charts_dir),
            "map_path": str(artifacts["fire_activity_map"]),
            "json_report_path": str(json_report),
            "md_report_path": str(md_report),
            "duration_seconds": duration,
        }
