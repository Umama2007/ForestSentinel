"""Unit tests for the FireActivityAnalyzer module."""

from __future__ import annotations

import pandas as pd
import pytest

from forestsentinel.analyzer import FireActivityAnalyzer


@pytest.fixture
def sample_fire_df() -> pd.DataFrame:
    """Fixture providing a realistic test DataFrame of active-fire detections."""
    return pd.DataFrame([
        {
            "detection_key": "k1",
            "latitude": -8.5,
            "longitude": -60.2,
            "acq_datetime": "2026-09-26T14:30:00Z",
            "acq_date": "2026-09-26",
            "acq_time": "1430",
            "satellite": "NOAA-21",
            "instrument": "VIIRS",
            "confidence": "nominal",
            "frp": 10.0,
            "daynight": "D",
        },
        {
            "detection_key": "k2",
            "latitude": -8.4,
            "longitude": -60.1,
            "acq_datetime": "2026-09-26T15:00:00Z",
            "acq_date": "2026-09-26",
            "acq_time": "1500",
            "satellite": "NOAA-21",
            "instrument": "VIIRS",
            "confidence": "high",
            "frp": 30.0,
            "daynight": "D",
        },
        {
            "detection_key": "k3",
            "latitude": -7.2,
            "longitude": -59.5,
            "acq_datetime": "2026-09-27T02:00:00Z",
            "acq_date": "2026-09-27",
            "acq_time": "0200",
            "satellite": "NOAA-21",
            "instrument": "VIIRS",
            "confidence": "low",
            "frp": 20.0,
            "daynight": "N",
        },
    ])


def test_date_derived_columns(sample_fire_df: pd.DataFrame):
    """Verify that temporal features are correctly extracted from datetime strings."""
    analyzer = FireActivityAnalyzer(sample_fire_df)
    df = analyzer.df

    assert "detection_date" in df.columns
    assert "detection_hour" in df.columns
    assert "day_of_week" in df.columns
    assert "month" in df.columns
    assert "year" in df.columns
    assert "week" in df.columns

    assert df.iloc[0]["detection_date"] == "2026-09-26"
    assert df.iloc[0]["detection_hour"] == 14
    assert df.iloc[0]["year"] == 2026
    assert df.iloc[0]["month"] == 9


def test_dataset_overview_metrics(sample_fire_df: pd.DataFrame):
    """Verify aggregate counts in dataset overview."""
    analyzer = FireActivityAnalyzer(sample_fire_df)
    ov = analyzer.get_dataset_overview()

    assert ov["total_records"] == 3
    assert ov["unique_detection_dates_count"] == 2
    assert ov["day_detections"] == 2
    assert ov["night_detections"] == 1
    assert ov["records_with_frp_count"] == 3
    assert ov["records_with_frp_percentage"] == 100.0
    assert ov["confidence_counts"]["nominal"] == 1
    assert ov["confidence_counts"]["high"] == 1
    assert ov["confidence_counts"]["low"] == 1


def test_temporal_daily_and_hourly(sample_fire_df: pd.DataFrame):
    """Verify daily and hourly detection aggregation."""
    analyzer = FireActivityAnalyzer(sample_fire_df)
    temp = analyzer.analyze_temporal()

    assert temp["daily_detections"]["2026-09-26"] == 2
    assert temp["daily_detections"]["2026-09-27"] == 1
    assert temp["hourly_detections"][14] == 1
    assert temp["hourly_detections"][15] == 1
    assert temp["hourly_detections"][2] == 1
    assert temp["hourly_detections"][0] == 0


def test_insufficient_data_trend():
    """Verify that single-date datasets are classified as insufficient data."""
    single_date_df = pd.DataFrame([{
        "detection_key": "k1",
        "latitude": -8.5,
        "longitude": -60.2,
        "acq_datetime": "2026-09-26T14:30:00Z",
        "acq_date": "2026-09-26",
        "acq_time": "1430",
        "frp": 10.0,
        "confidence": "nominal",
        "satellite": "NOAA-21",
        "instrument": "VIIRS",
        "daynight": "D",
    }])

    analyzer = FireActivityAnalyzer(single_date_df)
    temp = analyzer.analyze_temporal()
    assert temp["trend_summary"] == "insufficient data"


def test_fire_intensity_calculations(sample_fire_df: pd.DataFrame):
    """Verify statistical calculations for Fire Radiative Power."""
    analyzer = FireActivityAnalyzer(sample_fire_df)
    intensity = analyzer.analyze_fire_intensity()

    assert intensity["frp_available"] is True
    assert intensity["count"] == 3
    assert intensity["min_frp"] == 10.0
    assert intensity["max_frp"] == 30.0
    assert intensity["mean_frp"] == 20.0
    assert intensity["median_frp"] == 20.0
    assert len(intensity["top_10_detections"]) == 3
    assert intensity["top_10_detections"][0]["frp"] == 30.0  # highest first


def test_missing_frp_handled_honestly():
    """Verify analyzer preserves missing FRP without fabricating numbers."""
    df_no_frp = pd.DataFrame([{
        "detection_key": "k1",
        "latitude": -8.5,
        "longitude": -60.2,
        "acq_datetime": "2026-09-26T14:30:00Z",
        "acq_date": "2026-09-26",
        "acq_time": "1430",
        "confidence": "nominal",
        "satellite": "NOAA-21",
        "instrument": "VIIRS",
        "daynight": "D",
    }])
    analyzer = FireActivityAnalyzer(df_no_frp)
    intensity = analyzer.analyze_fire_intensity()
    assert intensity["frp_available"] is False
    assert any("FRP" in note for note in analyzer.data_quality_notes)
