"""Unit tests for the PriorityScorer module.

Tests deterministic grid allocation, score formula normalization,
weight redistribution under missing telemetry, and label boundaries.
"""

from __future__ import annotations

import pandas as pd
import pytest

from forestsentinel.priority_scoring import PriorityScorer


def test_grid_assignment_and_id_creation():
    """Verify deterministic floor-based grid assignment."""
    scorer = PriorityScorer(grid_size_degrees=0.25)
    df = pd.DataFrame([
        {"latitude": -8.12, "longitude": -60.18},
        {"latitude": -8.05, "longitude": -60.05},
        {"latitude": -7.95, "longitude": -59.85},
    ])

    enriched = scorer.assign_grid_cells(df)

    assert "grid_id" in enriched.columns
    assert "center_lat" in enriched.columns
    assert "center_lon" in enriched.columns

    # -8.12 with grid 0.25: floor(-8.12/0.25)*0.25 = floor(-32.48)*0.25 = -33 * 0.25 = -8.25
    # -60.18 with grid 0.25: floor(-60.18/0.25)*0.25 = floor(-240.72)*0.25 = -241 * 0.25 = -60.25
    assert enriched.iloc[0]["grid_lat"] == -8.25
    assert enriched.iloc[0]["grid_lon"] == -60.25
    assert enriched.iloc[0]["grid_id"] == "grid_-8.25_-60.25"
    assert enriched.iloc[0]["center_lat"] == round(-8.25 + 0.125, 4)


def test_safe_normalization_all_equal():
    """Verify that min-max scaling avoids divide-by-zero when all values are identical."""
    s = pd.Series([10.0, 10.0, 10.0])
    scaled = PriorityScorer._min_max_scale(s)
    assert (scaled == 0.5).all()

    s_zero = pd.Series([0.0, 0.0])
    scaled_zero = PriorityScorer._min_max_scale(s_zero)
    assert (scaled_zero == 0.0).all()


def test_priority_label_boundaries():
    """Verify explicit boundary conditions: <35 Low, 35-69.99 Medium, >=70 High."""
    scorer = PriorityScorer()

    # Create synthetic grid cells with pre-calculated scores to test label mapping
    df_raw = pd.DataFrame([
        # High activity cell
        {"latitude": -8.0, "longitude": -60.0, "acq_datetime": pd.Timestamp("2026-09-28T14:00:00Z"), "frp": 100.0, "confidence": "high"},
        {"latitude": -8.0, "longitude": -60.0, "acq_datetime": pd.Timestamp("2026-09-28T14:10:00Z"), "frp": 90.0, "confidence": "high"},
        {"latitude": -8.0, "longitude": -60.0, "acq_datetime": pd.Timestamp("2026-09-28T14:20:00Z"), "frp": 80.0, "confidence": "high"},
        # Low activity cell
        {"latitude": -9.0, "longitude": -61.0, "acq_datetime": pd.Timestamp("2026-09-20T10:00:00Z"), "frp": 5.0, "confidence": "low"},
    ])

    enriched = scorer.assign_grid_cells(df_raw)
    grid_df, meta = scorer.compute_grid_metrics(enriched)

    assert len(grid_df) == 2
    # The cell with 3 detections, 100 FRP, high confidence and recent timestamp should be top ranked
    assert grid_df.iloc[0]["grid_id"] == "grid_-8.00_-60.00"
    assert grid_df.iloc[0]["priority_score"] >= 70.0
    assert grid_df.iloc[0]["priority_label"] == "High Priority"

    assert grid_df.iloc[1]["grid_id"] == "grid_-9.00_-61.00"
    assert grid_df.iloc[1]["priority_score"] < 35.0
    assert grid_df.iloc[1]["priority_label"] == "Low Priority"


def test_frp_weight_redistribution_when_missing():
    """Verify that when FRP is completely absent, its 20% weight is redistributed proportionally."""
    scorer = PriorityScorer()
    df_no_frp = pd.DataFrame([
        {"latitude": -8.0, "longitude": -60.0, "acq_datetime": pd.Timestamp("2026-09-28T14:00:00Z"), "frp": None, "confidence": "high"},
        {"latitude": -9.0, "longitude": -61.0, "acq_datetime": pd.Timestamp("2026-09-27T10:00:00Z"), "frp": None, "confidence": "nominal"},
    ])

    enriched = scorer.assign_grid_cells(df_no_frp)
    grid_df, meta = scorer.compute_grid_metrics(enriched)

    active_weights = meta["active_weights"]
    assert "frp" not in active_weights
    # Sum of active weights should equal 1.0
    assert pytest.approx(sum(active_weights.values()), 0.001) == 1.0
    # Original ratio 45 : 25 : 10 -> Frequency should be 45/80 = 0.5625
    assert pytest.approx(active_weights["frequency"], 0.001) == 0.5625
    assert any("FRP data was unavailable" in note for note in meta["redistribution_notes"])


def test_confidence_weight_redistribution_when_missing():
    """Verify that when confidence is absent, its 10% weight is redistributed proportionally."""
    scorer = PriorityScorer()
    df_no_conf = pd.DataFrame([
        {"latitude": -8.0, "longitude": -60.0, "acq_datetime": pd.Timestamp("2026-09-28T14:00:00Z"), "frp": 25.0, "confidence": None},
        {"latitude": -9.0, "longitude": -61.0, "acq_datetime": pd.Timestamp("2026-09-27T10:00:00Z"), "frp": 15.0, "confidence": None},
    ])

    enriched = scorer.assign_grid_cells(df_no_conf)
    grid_df, meta = scorer.compute_grid_metrics(enriched)

    active_weights = meta["active_weights"]
    assert "confidence" not in active_weights
    assert pytest.approx(sum(active_weights.values()), 0.001) == 1.0
    assert any("Confidence data was unavailable" in note for note in meta["redistribution_notes"])
