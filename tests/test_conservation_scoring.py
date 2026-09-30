"""Unit tests for Conservation Exposure Priority Scoring in ForestSentinel."""

from __future__ import annotations

import pytest

from forestsentinel.conservation_scoring import ConservationScorer


def test_severity_weights_mapping():
    """Verify exact IUCN threat severity mappings: CR=1.00, EN=0.75, VU=0.50."""
    assert ConservationScorer.IUCN_SEVERITY_WEIGHTS["CR"] == 1.00
    assert ConservationScorer.IUCN_SEVERITY_WEIGHTS["EN"] == 0.75
    assert ConservationScorer.IUCN_SEVERITY_WEIGHTS["VU"] == 0.50


def test_unverified_species_not_scored_as_threatened():
    """Verify that unverified species are Pending IUCN Verification and LC are Verified Not Threatened."""
    # LC (Least Concern)
    score, label, exp = ConservationScorer.calculate_score(
        fire_priority_score=85.0,
        iucn_category="LC",
        iucn_verified=True,
        occurrence_count=5,
    )
    assert score is None
    assert label == ConservationScorer.LABEL_VERIFIED_NOT_THREATENED
    assert "Verified Not Threatened" in exp

    # Unverified status (even if string passed is CR)
    score_unver, label_unver, exp_unver = ConservationScorer.calculate_score(
        fire_priority_score=85.0,
        iucn_category="CR",
        iucn_verified=False,
        occurrence_count=5,
    )
    assert score_unver is None
    assert label_unver == ConservationScorer.LABEL_PENDING_IUCN
    assert "Pending IUCN Verification" in exp_unver


def test_conservation_score_calculation_exact():
    """Verify exact formula: (0.45 * norm_fire + 0.35 * severity + 0.20 * norm_occ) * 100."""
    # Fire score = 80.0 -> norm_fire = 0.80
    # Category = EN -> severity = 0.75
    # Occurrence count = 10, max_occ = 10 -> norm_occ = 1.0
    # Expected: (0.45 * 0.80 + 0.35 * 0.75 + 0.20 * 1.0) * 100
    # = (0.36 + 0.2625 + 0.20) * 100 = 0.8225 * 100 = 82.25
    score, label, explanation = ConservationScorer.calculate_score(
        fire_priority_score=80.0,
        iucn_category="EN",
        iucn_verified=True,
        occurrence_count=10,
        max_occurrence_count=10,
    )
    assert score == 82.25
    assert label == ConservationScorer.LABEL_HIGH
    assert "High Conservation Priority" in explanation


def test_priority_label_boundaries():
    """Test label classification boundaries: High (>=70), Medium (40-69.9), Lower (<40)."""
    # High: Fire 70, CR (1.0), Occ 1/1 -> (0.45*0.7 + 0.35*1.0 + 0.20*1.0) * 100 = (0.315 + 0.35 + 0.20)*100 = 86.5
    s_high, l_high, _ = ConservationScorer.calculate_score(70.0, "CR", True, 1, 1)
    assert s_high >= 70.0
    assert l_high == ConservationScorer.LABEL_HIGH

    # Medium: Fire 40, VU (0.50), Occ 1/1 -> (0.45*0.4 + 0.35*0.5 + 0.20*1.0)*100 = (0.18 + 0.175 + 0.20)*100 = 55.5
    s_med, l_med, _ = ConservationScorer.calculate_score(40.0, "VU", True, 1, 1)
    assert 40.0 <= s_med < 70.0
    assert l_med == ConservationScorer.LABEL_MEDIUM

    # Lower: Fire 10, VU (0.50), Occ 1/10 -> (0.45*0.1 + 0.35*0.5 + 0.20*0.1)*100 = (0.045 + 0.175 + 0.02)*100 = 24.0
    s_low, l_low, _ = ConservationScorer.calculate_score(10.0, "VU", True, 1, 10)
    assert s_low < 40.0
    assert l_low == ConservationScorer.LABEL_LOWER


def test_no_divide_by_zero_errors():
    """Test resilience against zero counts or missing values."""
    score, label, _ = ConservationScorer.calculate_score(
        fire_priority_score=0.0,
        iucn_category="VU",
        iucn_verified=True,
        occurrence_count=0,
        max_occurrence_count=0,
    )
    assert score is not None
    assert 0.0 <= score <= 100.0


def test_cell_conservation_aggregation():
    """Test cell-level summary aggregation."""
    species_list = [
        {
            "grid_id": "cell_1",
            "scientific_name": "Species A",
            "iucn_category": "CR",
            "iucn_verified": True,
            "conservation_exposure_score": 85.0,
        },
        {
            "grid_id": "cell_1",
            "scientific_name": "Species B",
            "iucn_category": "VU",
            "iucn_verified": True,
            "conservation_exposure_score": 55.0,
        },
        {
            "grid_id": "cell_1",
            "scientific_name": "Species C",
            "iucn_category": "LC",
            "iucn_verified": True,
            "conservation_exposure_score": None,
        }
    ]

    cell_agg = ConservationScorer.aggregate_cell_conservation(
        grid_id="cell_1",
        fire_priority_score=75.0,
        fire_priority_label="High Priority",
        species_in_cell=species_list,
    )

    assert cell_agg["grid_id"] == "cell_1"
    assert cell_agg["total_species_recorded"] == 3
    assert cell_agg["threatened_species_count"] == 2
    assert cell_agg["highest_iucn_category"] == "CR"
    assert cell_agg["max_conservation_exposure_score"] == 85.0
    assert cell_agg["conservation_priority_label"] == ConservationScorer.LABEL_HIGH
