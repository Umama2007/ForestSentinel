"""Unit tests for the analytics repository module.

Verifies conversion of Firestore document streams into structured Pandas DataFrames
and proper handling of empty collections using mocks.
"""

from __future__ import annotations

from unittest.mock import MagicMock
import pandas as pd
import pytest

from forestsentinel.analytics_repository import AnalyticsRepository, NoDataError


def test_load_fire_detections_success():
    """Verify that mocked Firestore documents are converted into a correctly typed DataFrame."""
    mock_doc1 = MagicMock()
    mock_doc1.to_dict.return_value = {
        "detection_key": "key_1",
        "latitude": -8.5,
        "longitude": -60.2,
        "acq_datetime": "2026-09-28T14:30:00Z",
        "acq_date": "2026-09-28",
        "acq_time": "1430",
        "satellite": "NOAA-21",
        "instrument": "VIIRS",
        "confidence": "nominal",
        "frp": 15.5,
        "bright_ti4": 325.0,
        "bright_ti5": 295.0,
        "daynight": "D",
        "ingested_at": "2026-09-30T10:00:00Z",
        "etl_run_id": "run_001",
    }

    mock_doc2 = MagicMock()
    mock_doc2.to_dict.return_value = {
        "detection_key": "key_2",
        "latitude": -7.2,
        "longitude": -59.8,
        "acq_datetime": "2026-09-29T02:15:00Z",
        "acq_date": "2026-09-29",
        "acq_time": "0215",
        "satellite": "NOAA-21",
        "instrument": "VIIRS",
        "confidence": "high",
        "frp": 45.0,
        "daynight": "N",
    }

    mock_fb_client = MagicMock()
    mock_fb_client.db.collection().stream.return_value = [mock_doc1, mock_doc2]

    repo = AnalyticsRepository(firebase_client=mock_fb_client)
    df = repo.load_fire_detections()

    assert len(df) == 2
    assert "detection_key" in df.columns
    assert df.iloc[0]["detection_key"] == "key_1"
    assert df.iloc[0]["frp"] == 15.5
    assert df.iloc[1]["confidence"] == "high"
    # Verify missing optional fields are safely set to None / NaN
    assert df.iloc[1]["bright_ti4"] is None or pd.isna(df.iloc[1]["bright_ti4"])


def test_load_fire_detections_empty_collection_raises_error():
    """Verify that an empty fire_detections collection raises a friendly NoDataError."""
    mock_fb_client = MagicMock()
    mock_fb_client.db.collection().stream.return_value = []

    repo = AnalyticsRepository(firebase_client=mock_fb_client)
    with pytest.raises(NoDataError) as exc_info:
        repo.load_fire_detections()

    assert "No Firestore fire_detections were found" in str(exc_info.value)
    assert "python run_pipeline.py" in str(exc_info.value)
