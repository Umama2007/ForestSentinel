"""Unit tests for ConservationReporter, Repository sanitization, and Visualizer in ForestSentinel."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock
import pandas as pd
import pytest

from forestsentinel.conservation_reporter import (
    MANDATORY_LIMITATIONS_STATEMENT,
    generate_conservation_report,
)
from forestsentinel.conservation_repository import ConservationRepository
from forestsentinel.conservation_visualizer import ConservationVisualizer


@pytest.fixture
def sample_analysis_data():
    """Provide realistic sample analysis data for testing."""
    return {
        "priority_cells_considered": 2,
        "gbif_requests_made": 2,
        "gbif_occurrence_records_received": 150,
        "unique_animal_species_found": 25,
        "species_with_verified_iucn_status": 18,
        "threatened_species_found": 3,
        "threatened_by_category": {"CR": 1, "EN": 1, "VU": 1},
        "high_conservation_priority_count": 1,
        "medium_conservation_priority_count": 2,
        "lower_conservation_priority_count": 0,
        "unverified_or_not_threatened_count": 22,
        "cell_conservation_summaries": [
            {
                "grid_id": "grid_-8.00_-61.25",
                "fire_priority_score": 88.5,
                "fire_priority_label": "High Priority",
                "total_species_recorded": 15,
                "threatened_species_count": 2,
                "highest_iucn_category": "CR",
                "max_conservation_exposure_score": 89.2,
                "conservation_priority_label": "High Conservation Priority",
            }
        ],
        "threatened_species_summaries": [
            {
                "scientific_name": "Ateles belzebuth",
                "common_name": "White-bellied Spider Monkey",
                "family": "Atelidae",
                "iucn_category": "CR",
                "iucn_verified": True,
                "grid_id": "grid_-8.00_-61.25",
                "conservation_exposure_score": 89.2,
                "conservation_exposure_label": "High Conservation Priority",
            }
        ],
        "species_grid_summaries": [
            {
                "grid_id": "grid_-8.00_-61.25",
                "grid_priority_label": "High Priority",
                "grid_priority_score": 88.5,
                "taxon_key": 2436653,
                "scientific_name": "Ateles belzebuth",
                "common_name": "White-bellied Spider Monkey",
                "kingdom": "Animalia",
                "phylum": "Chordata",
                "class": "Mammalia",
                "order": "Primates",
                "family": "Atelidae",
                "iucn_category": "CR",
                "iucn_assessment_date": "2020-01-01",
                "iucn_verified": True,
                "recorded_occurrence_count": 4,
                "observation_year_min": 2012,
                "observation_year_max": 2021,
                "conservation_exposure_score": 89.2,
                "conservation_exposure_label": "High Conservation Priority",
            }
        ],
    }


def test_generate_conservation_report(tmp_path: Path, sample_analysis_data):
    """Test generating JSON and Markdown reports and verifying required contents."""
    artifact_paths = {
        "threatened_species_by_category": tmp_path / "threatened_species_by_category.png",
        "conservation_exposure_map": tmp_path / "conservation_exposure_map.html",
    }
    # Create dummy files
    for p in artifact_paths.values():
        p.touch()

    json_path, md_path = generate_conservation_report(
        analysis_results=sample_analysis_data,
        artifact_paths=artifact_paths,
        output_dir=tmp_path,
        database_project="test-project-123",
        run_id="test_run_001",
        iucn_configured=True,
    )

    assert json_path.is_file()
    assert md_path.is_file()

    # Verify JSON structure
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["metadata"]["run_id"] == "test_run_001"
    assert data["summary_metrics"]["threatened_species_found"] == 3
    assert data["limitations_statement"] == MANDATORY_LIMITATIONS_STATEMENT

    # Verify Markdown contains mandatory text and sections
    md_content = md_path.read_text(encoding="utf-8")
    assert MANDATORY_LIMITATIONS_STATEMENT in md_content
    assert "White-bellied Spider Monkey" in md_content
    assert "Ateles belzebuth" in md_content
    assert "grid_-8.00_-61.25" in md_content
    assert "No Exact Coordinates Saved" in md_content


def test_repository_privacy_enforcement_rejects_coordinates():
    """Verify ConservationRepository strictly rejects forbidden coordinate fields."""
    mock_fb = MagicMock()
    repo = ConservationRepository(db_client=mock_fb)

    # Record containing forbidden coordinates
    bad_record = {
        "grid_id": "cell_1",
        "scientific_name": "Panthera onca",
        "latitude": -8.1234,  # FORBIDDEN!
        "longitude": -61.5678,  # FORBIDDEN!
    }

    with pytest.raises(ValueError, match="PRIVACY VIOLATION DETECTED"):
        repo._sanitize_summary_record(bad_record, run_id="run_123")

    # Record with GBIF key
    bad_record_key = {
        "grid_id": "cell_1",
        "scientific_name": "Panthera onca",
        "decimalLatitude": -8.1234,  # FORBIDDEN!
    }

    with pytest.raises(ValueError, match="PRIVACY VIOLATION DETECTED"):
        repo._sanitize_summary_record(bad_record_key, run_id="run_123")


def test_repository_sanitizer_preserves_permitted_aggregated_fields():
    """Verify ConservationRepository keeps permitted aggregated fields."""
    mock_fb = MagicMock()
    repo = ConservationRepository(db_client=mock_fb)

    good_record = {
        "grid_id": "cell_1",
        "grid_priority_label": "High Priority",
        "grid_priority_score": 75.0,
        "taxon_key": 12345,
        "scientific_name": "Panthera onca",
        "common_name": "Jaguar",
        "kingdom": "Animalia",
        "phylum": "Chordata",
        "class": "Mammalia",
        "order": "Carnivora",
        "family": "Felidae",
        "iucn_category": "NT",
        "iucn_assessment_date": "2018-05-18",
        "iucn_verified": True,
        "recorded_occurrence_count": 5,
        "observation_year_min": 2010,
        "observation_year_max": 2022,
        "conservation_exposure_score": None,
        "conservation_exposure_label": "Verified Not Threatened",
    }

    sanitized = repo._sanitize_summary_record(good_record, run_id="run_456")
    assert sanitized["grid_id"] == "cell_1"
    assert sanitized["analysis_run_id"] == "run_456"
    assert sanitized["taxon_key"] == 12345
    assert "latitude" not in sanitized
    assert "longitude" not in sanitized


def test_visualizer_renders_all_expected_artifacts(tmp_path: Path, sample_analysis_data):
    """Test that ConservationVisualizer renders all 4 PNGs and Folium HTML map."""
    visualizer = ConservationVisualizer(output_dir=tmp_path)

    grid_cells_df = pd.DataFrame([
        {
            "grid_id": "grid_-8.00_-61.25",
            "grid_lat": -8.0,
            "grid_lon": -61.25,
            "center_lat": -7.875,
            "center_lon": -61.125,
            "priority_score": 88.5,
            "priority_label": "High Priority",
            "detection_count": 45,
        },
        {
            "grid_id": "grid_-9.00_-61.00",
            "grid_lat": -9.0,
            "grid_lon": -61.0,
            "center_lat": -8.875,
            "center_lon": -60.875,
            "priority_score": 52.0,
            "priority_label": "Medium Priority",
            "detection_count": 20,
        }
    ])

    artifacts = visualizer.render_all(
        grid_cells_df=grid_cells_df,
        analysis_results=sample_analysis_data,
        grid_size_degrees=0.25,
    )

    expected_files = [
        "threatened_species_by_category",
        "species_exposure_by_priority_zone",
        "top_conservation_priority_cells",
        "biodiversity_data_quality",
        "conservation_exposure_map",
    ]

    for key in expected_files:
        assert key in artifacts
        assert artifacts[key].is_file(), f"Expected artifact {artifacts[key]} to exist."
        assert artifacts[key].stat().st_size > 0, f"Artifact {artifacts[key]} should not be empty."

    # Check that the map HTML contains the responsible use disclaimer
    html_content = artifacts["conservation_exposure_map"].read_text(encoding="utf-8")
    assert "Conservation Exposure" in html_content
    assert "Species information is aggregated to 0.25° grid cells for privacy" in html_content
