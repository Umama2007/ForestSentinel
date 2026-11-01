"""Unit tests for the reporter module."""

from __future__ import annotations

import json
from pathlib import Path

from forestsentinel.reporter import generate_etl_report


def test_generate_etl_report(tmp_path: Path):
    summary_data = {
        "run_id": "run_test_20260930_120000",
        "status": "completed",
        "started_at": "2026-09-30T12:00:00Z",
        "finished_at": "2026-09-30T12:01:00Z",
        "duration_seconds": 60.0,
        "api_source": "VIIRS_NOAA21_NRT",
        "study_bbox": "-62,-10,-58,-6",
        "day_range": 10,
        "database_project": "test-forestsentinel",
        "counts": {
            "raw_rows_extracted": 100,
            "exact_duplicates_removed": 5,
            "cleaning_rejections": 2,
            "pydantic_rejections": 1,
            "valid_records": 92,
            "inserted_records": 90,
            "skipped_existing_records": 2,
        },
        "rejected_sample": [
            {
                "source_row_number": 42,
                "rejection_reason": "Cleaning error: Latitude 95.0 out of bounds [-90, 90]",
            }
        ],
    }

    json_path, md_path = generate_etl_report(summary_data, reports_dir=tmp_path)

    assert json_path.is_file()
    assert md_path.is_file()

    # Verify JSON content
    with open(json_path, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded["run_id"] == "run_test_20260930_120000"
    assert loaded["counts"]["inserted_records"] == 90

    # Verify Markdown content
    md_text = md_path.read_text(encoding="utf-8")
    assert "ForestSentinel ETL Quality & Audit Report" in md_text
    assert "run_test_20260930_120000" in md_text
    assert "fire_detections" in md_text
    assert "rejected_records" in md_text
    assert "etl_runs" in md_text
    assert "thermal anomalies" in md_text.lower()
    assert "Sample 1 (Source Row #42)" in md_text
