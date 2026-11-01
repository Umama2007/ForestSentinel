"""Unit tests for the visualizer module and analysis reporter."""

from __future__ import annotations

from pathlib import Path
import pandas as pd
import pytest

from forestsentinel.analysis_reporter import LIMITATION_STATEMENT, generate_analysis_report
from forestsentinel.priority_scoring import PriorityScorer
from forestsentinel.visualizer import Visualizer


@pytest.fixture
def sample_analysis_data():
    """Create a populated dataset for testing visualization and reporting."""
    scorer = PriorityScorer(grid_size_degrees=0.25)
    detections = pd.DataFrame([
        {
            "detection_key": "k1",
            "latitude": -8.1,
            "longitude": -60.1,
            "acq_datetime": pd.Timestamp("2026-09-28T14:30:00Z"),
            "detection_date": "2026-09-28",
            "detection_hour": 14,
            "frp": 35.0,
            "confidence": "high",
            "satellite": "NOAA-21",
            "instrument": "VIIRS",
            "daynight": "D",
        },
        {
            "detection_key": "k2",
            "latitude": -8.2,
            "longitude": -60.2,
            "acq_datetime": pd.Timestamp("2026-09-29T02:00:00Z"),
            "detection_date": "2026-09-29",
            "detection_hour": 2,
            "frp": 12.0,
            "confidence": "nominal",
            "satellite": "NOAA-21",
            "instrument": "VIIRS",
            "daynight": "N",
        },
    ])
    enriched = scorer.assign_grid_cells(detections)
    grid_df, meta = scorer.compute_grid_metrics(enriched)
    return enriched, grid_df, meta


def test_visualizer_produces_all_expected_files(tmp_path: Path, sample_analysis_data):
    """Verify that Visualizer.render_all produces all 9 PNG charts and the Folium HTML map."""
    enriched, grid_df, _ = sample_analysis_data

    vis = Visualizer(output_dir=tmp_path)
    artifacts = vis.render_all(detections_df=enriched, grid_df=grid_df, grid_size=0.25)

    expected_keys = [
        "daily_fire_activity",
        "hourly_activity",
        "confidence_distribution",
        "brightness_distribution",
        "outlier_boxplots",
        "frp_distribution",
        "day_night_distribution",
        "satellite_sensor_distribution",
        "hotspot_priority_distribution",
        "fire_activity_map",
    ]

    for key in expected_keys:
        assert key in artifacts
        file_path = artifacts[key]
        assert file_path.is_file(), f"File for {key} was not created at {file_path}"
        assert file_path.stat().st_size > 0, f"File {file_path} is empty"

    # Check that HTML map contains basic folium markup
    html_content = artifacts["fire_activity_map"].read_text(encoding="utf-8")
    assert "<html" in html_content.lower()
    assert "ForestSentinel Fire Priority Zones" in html_content


def test_analysis_report_contains_limitation_statement(tmp_path: Path, sample_analysis_data):
    """Verify that generated Markdown and JSON reports contain the required scientific limitation statement."""
    enriched, grid_df, meta = sample_analysis_data

    eda_mock = {
        "overview": {
            "total_records": 2,
            "unique_detection_dates_count": 2,
            "unique_detection_dates": ["2026-09-28", "2026-09-29"],
            "satellites": ["NOAA-21"],
            "instruments": ["VIIRS"],
            "day_detections": 1,
            "night_detections": 1,
            "records_with_frp_count": 2,
            "records_with_frp_percentage": 100.0,
            "earliest_detection_datetime": "2026-09-28T14:30:00Z",
            "latest_detection_datetime": "2026-09-29T02:00:00Z",
        },
        "temporal": {
            "trend_summary": "stable",
            "trend_explanation": "Test explanation",
            "daily_detections": {"2026-09-28": 1, "2026-09-29": 1},
        },
        "intensity": {
            "mean_frp": 23.5,
            "median_frp": 23.5,
            "min_frp": 12.0,
            "max_frp": 35.0,
            "q25_frp": 17.75,
            "q75_frp": 29.25,
            "std_frp": 16.26,
            "count": 2,
            "top_10_detections": [],
        },
        "sensors": {
            "confidence_counts": {"high": 1, "nominal": 1},
            "confidence_percentages": {"high": 50.0, "nominal": 50.0},
        },
        "spatial_bounds": {
            "min_latitude": -8.2,
            "max_latitude": -8.1,
            "min_longitude": -60.2,
            "max_longitude": -60.1,
        },
        "data_quality_notes": [],
    }

    dummy_artifacts = {
        "daily_fire_activity": tmp_path / "daily.png",
        "fire_activity_map": tmp_path / "map.html",
    }

    json_path, md_path = generate_analysis_report(
        eda_results=eda_mock,
        grid_df=grid_df,
        grid_metadata=meta,
        artifact_paths=dummy_artifacts,
        reports_dir=tmp_path,
        database_project="test-proj",
    )

    assert json_path.is_file()
    assert md_path.is_file()

    md_text = md_path.read_text(encoding="utf-8")
    assert LIMITATION_STATEMENT in md_text
    assert "Priority Score" in md_text
    assert "Hotspot Analysis" in md_text
