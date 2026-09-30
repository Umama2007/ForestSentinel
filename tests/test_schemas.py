"""Unit tests for the Pydantic v2 schemas and validation logic.

Verifies model constraints, error trapping, and candidate-to-rejection routing.
"""

from __future__ import annotations

from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from forestsentinel.schemas import FireDetection, validate_fire_records


def test_valid_fire_detection_schema():
    """Verify that a compliant dictionary validates successfully."""
    data = {
        "detection_key": "abc123sha256fakekey",
        "latitude": -7.5,
        "longitude": -60.2,
        "acq_datetime": datetime(2026, 9, 28, 14, 30, tzinfo=timezone.utc),
        "acq_date": "2026-09-28",
        "acq_time": "1430",
        "satellite": "NOAA-21",
        "instrument": "VIIRS",
        "confidence": "nominal",
        "frp": 25.5,
        "bright_ti4": 330.2,
        "bright_ti5": 298.1,
        "daynight": "D",
        "source_row_number": 1,
    }

    model = FireDetection.model_validate(data)
    assert model.detection_key == "abc123sha256fakekey"
    assert model.latitude == -7.5
    assert model.frp == 25.5
    assert model.daynight == "D"

    storage_dict = model.to_storage_dict()
    assert isinstance(storage_dict["acq_datetime"], str)
    assert isinstance(storage_dict["ingested_at"], str)


def test_invalid_latitude_raises_validation_error():
    """Verify that latitude > 90 fails validation."""
    data = {
        "detection_key": "key1",
        "latitude": 91.0,
        "longitude": -60.0,
        "acq_datetime": datetime(2026, 9, 28, 14, 30, tzinfo=timezone.utc),
        "acq_date": "2026-09-28",
        "acq_time": "1430",
        "source_row_number": 1,
    }
    with pytest.raises(ValidationError) as exc_info:
        FireDetection.model_validate(data)

    errors = exc_info.value.errors()
    assert any("latitude" in str(e["loc"]) for e in errors)


def test_negative_frp_raises_validation_error():
    """Verify that negative Fire Radiative Power is rejected."""
    data = {
        "detection_key": "key1",
        "latitude": -8.0,
        "longitude": -60.0,
        "acq_datetime": datetime(2026, 9, 28, 14, 30, tzinfo=timezone.utc),
        "acq_date": "2026-09-28",
        "acq_time": "1430",
        "frp": -5.0,  # Invalid: cannot be negative
        "source_row_number": 1,
    }
    with pytest.raises(ValidationError):
        FireDetection.model_validate(data)


def test_validate_fire_records_isolates_bad_rows():
    """Verify that validate_fire_records routes bad rows to rejections without crashing."""
    candidates = [
        {
            "detection_key": "valid_key",
            "latitude": -7.5,
            "longitude": -60.2,
            "acq_datetime": datetime(2026, 9, 28, 14, 30, tzinfo=timezone.utc),
            "acq_date": "2026-09-28",
            "acq_time": "1430",
            "source_row_number": 1,
        },
        {
            "detection_key": "bad_key",
            "latitude": 105.0,  # Invalid latitude
            "longitude": -60.2,
            "acq_datetime": datetime(2026, 9, 28, 14, 30, tzinfo=timezone.utc),
            "acq_date": "2026-09-28",
            "acq_time": "1430",
            "source_row_number": 2,
        },
    ]

    valid, rejected = validate_fire_records(candidates, etl_run_id="run_test_123")

    assert len(valid) == 1
    assert len(rejected) == 1
    assert valid[0]["detection_key"] == "valid_key"
    assert rejected[0]["source_row_number"] == 2
    assert "Pydantic validation failed" in rejected[0]["rejection_reason"]
    assert "latitude" in rejected[0]["rejection_reason"]
