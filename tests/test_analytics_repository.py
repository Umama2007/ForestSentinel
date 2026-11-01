"""Unit tests for the analytics repository module.

Verifies conversion of Supabase fire_detections rows into structured Pandas DataFrames
and proper handling of an empty table using mocks.
"""

from __future__ import annotations

from unittest.mock import MagicMock
import pandas as pd
import pytest

from forestsentinel.analytics_repository import AnalyticsRepository, NoDataError


def test_load_fire_detections_success():
    """Verify that mocked Supabase rows are converted into a correctly typed DataFrame."""
    row1 = {
        "detection_key": "key_1",
        "latitude": -8.5,
        "longitude": -60.2,
        "acq_datetime": "2026-09-28T14:30:00+00:00",
        "acq_date": "2026-09-28",
        "acq_time": "1430",
        "satellite": "NOAA-21",
        "instrument": "VIIRS",
        "confidence": "nominal",
        "frp": 15.5,
        "bright_ti4": 325.0,
        "bright_ti5": 295.0,
        "daynight": "D",
        "ingested_at": "2026-09-30T10:00:00+00:00",
        "etl_run_id": "run_001",
    }
    row2 = {
        "detection_key": "key_2",
        "latitude": -7.2,
        "longitude": -59.8,
        "acq_datetime": "2026-09-29T02:15:00+00:00",
        "acq_date": "2026-09-29",
        "acq_time": "0215",
        "satellite": "NOAA-21",
        "instrument": "VIIRS",
        "confidence": "high",
        "frp": 45.0,
        "daynight": "N",
    }

    mock_db = MagicMock()
    mock_db.select.return_value = [row1, row2]

    repo = AnalyticsRepository(db_client=mock_db)
    df = repo.load_fire_detections()

    assert mock_db.select.call_args.args[0] == "fire_detections"
    assert len(df) == 2
    assert "detection_key" in df.columns
    assert df.iloc[0]["detection_key"] == "key_1"
    assert df.iloc[0]["frp"] == 15.5
    assert df.iloc[1]["confidence"] == "high"
    # Verify missing optional fields are safely set to None / NaN
    assert df.iloc[1]["bright_ti4"] is None or pd.isna(df.iloc[1]["bright_ti4"])


def test_load_fire_detections_passes_limit():
    """Verify an explicit limit is forwarded to the database read."""
    mock_db = MagicMock()
    mock_db.select.return_value = [{"detection_key": "k", "latitude": -8.0, "longitude": -60.0}]

    AnalyticsRepository(db_client=mock_db).load_fire_detections(limit=50)

    assert mock_db.select.call_args.kwargs["limit"] == 50


def test_load_fire_detections_empty_table_raises_error():
    """Verify that an empty fire_detections table raises a friendly NoDataError."""
    mock_db = MagicMock()
    mock_db.select.return_value = []

    repo = AnalyticsRepository(db_client=mock_db)
    with pytest.raises(NoDataError) as exc_info:
        repo.load_fire_detections()

    assert "No fire_detections were found" in str(exc_info.value)
    assert "python run_pipeline.py" in str(exc_info.value)
