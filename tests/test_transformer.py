"""Unit tests for the ForestSentinel transformer module.

Verifies cleaning, coordinate filtering, datetime parsing, deduplication,
and deterministic key generation without requiring internet connectivity.
"""

from __future__ import annotations

import pandas as pd
import pytest

from forestsentinel.transformer import FirmsTransformer


@pytest.fixture
def transformer() -> FirmsTransformer:
    return FirmsTransformer()


def test_valid_coordinate_transformation(transformer: FirmsTransformer):
    """Test that valid coordinates are correctly parsed and normalized."""
    df = pd.DataFrame([{
        "latitude": -7.12345,
        "longitude": -60.54321,
        "acq_date": "2026-09-28",
        "acq_time": "1430",
        "satellite": "NOAA-21",
        "instrument": "VIIRS",
        "confidence": "nominal",
        "frp": 15.2,
        "daynight": "D",
    }])

    valid, rejected, stats = transformer.transform(df)

    assert len(valid) == 1
    assert len(rejected) == 0
    assert stats["valid_candidates"] == 1
    assert valid[0]["latitude"] == -7.12345
    assert valid[0]["longitude"] == -60.54321
    assert valid[0]["confidence"] == "nominal"
    assert valid[0]["daynight"] == "D"
    assert valid[0]["frp"] == 15.2
    assert "detection_key" in valid[0]
    assert len(valid[0]["detection_key"]) == 64  # SHA-256 hex


def test_invalid_latitude_rejected(transformer: FirmsTransformer):
    """Test that out-of-bounds latitude values are rejected."""
    df = pd.DataFrame([{
        "latitude": 95.0,  # Invalid (> 90)
        "longitude": -60.0,
        "acq_date": "2026-09-28",
        "acq_time": "1200",
    }])

    valid, rejected, stats = transformer.transform(df)

    assert len(valid) == 0
    assert len(rejected) == 1
    assert stats["cleaning_rejections"] == 1
    assert "Latitude 95.0 out of bounds" in rejected[0]["rejection_reason"]


def test_invalid_longitude_rejected(transformer: FirmsTransformer):
    """Test that out-of-bounds longitude values are rejected."""
    df = pd.DataFrame([{
        "latitude": -8.0,
        "longitude": -195.0,  # Invalid (< -180)
        "acq_date": "2026-09-28",
        "acq_time": "1200",
    }])

    valid, rejected, stats = transformer.transform(df)

    assert len(valid) == 0
    assert len(rejected) == 1
    assert stats["cleaning_rejections"] == 1
    assert "Longitude -195.0 out of bounds" in rejected[0]["rejection_reason"]


def test_missing_or_invalid_datetime_rejected(transformer: FirmsTransformer):
    """Test that missing or unparseable date/time combinations are rejected."""
    df = pd.DataFrame([
        {
            "latitude": -8.0,
            "longitude": -60.0,
            "acq_date": "invalid-date",
            "acq_time": "1200",
        },
        {
            "latitude": -8.0,
            "longitude": -60.0,
            "acq_date": "2026-09-28",
            "acq_time": "2599",  # Invalid hour 25
        },
    ])

    valid, rejected, stats = transformer.transform(df)

    assert len(valid) == 0
    assert len(rejected) == 2
    assert stats["cleaning_rejections"] == 2


def test_time_zero_padding(transformer: FirmsTransformer):
    """Test that times like '930' or 930 are zero-padded to '0930'."""
    df = pd.DataFrame([{
        "latitude": -8.0,
        "longitude": -60.0,
        "acq_date": "2026-09-28",
        "acq_time": 930,  # integer 930
    }])

    valid, rejected, _ = transformer.transform(df)

    assert len(valid) == 1
    assert valid[0]["acq_time"] == "0930"
    assert valid[0]["acq_datetime"].hour == 9
    assert valid[0]["acq_datetime"].minute == 30


def test_duplicate_source_rows_removed(transformer: FirmsTransformer):
    """Test that identical duplicate source records are deduplicated."""
    row = {
        "latitude": -8.5,
        "longitude": -60.5,
        "acq_date": "2026-09-28",
        "acq_time": "1015",
        "satellite": "NOAA-21",
        "instrument": "VIIRS",
        "confidence": "nominal",
        "frp": 12.0,
        "daynight": "D",
    }
    # Create DataFrame with 3 identical rows
    df = pd.DataFrame([row, row, row])

    valid, rejected, stats = transformer.transform(df)

    assert len(valid) == 1
    assert stats["total_raw_rows"] == 3
    assert stats["exact_duplicates_removed"] == 2


def test_deterministic_detection_key(transformer: FirmsTransformer):
    """Test that identical attributes produce identical keys and distinct attributes produce distinct keys."""
    key1 = transformer._generate_detection_key(
        lat=-8.123456,
        lon=-60.123456,
        dt_iso="2026-09-28T14:30:00+00:00",
        satellite="NOAA-21",
        instrument="VIIRS",
        frp=10.5,
    )
    key2 = transformer._generate_detection_key(
        lat=-8.123456,
        lon=-60.123456,
        dt_iso="2026-09-28T14:30:00+00:00",
        satellite="NOAA-21",
        instrument="VIIRS",
        frp=10.5,
    )
    key_different_frp = transformer._generate_detection_key(
        lat=-8.123456,
        lon=-60.123456,
        dt_iso="2026-09-28T14:30:00+00:00",
        satellite="NOAA-21",
        instrument="VIIRS",
        frp=99.9,
    )

    assert key1 == key2
    assert key1 != key_different_frp
