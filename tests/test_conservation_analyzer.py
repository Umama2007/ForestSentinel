"""Unit tests for ConservationAnalyzer in ForestSentinel."""

from __future__ import annotations

from unittest.mock import MagicMock
import pandas as pd
import pytest

from forestsentinel.conservation_analyzer import ConservationAnalyzer
from forestsentinel.gbif_client import GBIFClient
from forestsentinel.iucn_client import IUCNClient


@pytest.fixture
def mock_clients():
    """Create mock GBIF and IUCN clients."""
    gbif = MagicMock(spec=GBIFClient)
    iucn = MagicMock(spec=IUCNClient)
    return gbif, iucn


def test_filter_priority_cells(mock_clients):
    """Test filtering to keep only High Priority and Medium Priority grid cells."""
    gbif, iucn = mock_clients
    analyzer = ConservationAnalyzer(gbif, iucn)

    grid_df = pd.DataFrame([
        {"grid_id": "cell_1", "priority_label": "High Priority", "priority_score": 85.0},
        {"grid_id": "cell_2", "priority_label": "Medium Priority", "priority_score": 55.0},
        {"grid_id": "cell_3", "priority_label": "Low Priority", "priority_score": 15.0},
    ])

    filtered = analyzer.filter_priority_cells(grid_df)
    assert len(filtered) == 2
    assert "cell_1" in filtered["grid_id"].values
    assert "cell_2" in filtered["grid_id"].values
    assert "cell_3" not in filtered["grid_id"].values


def test_species_deduplication_by_taxon_key(mock_clients):
    """Test grouping multiple raw occurrence records into a single species-grid summary."""
    gbif, iucn = mock_clients
    analyzer = ConservationAnalyzer(gbif, iucn)

    # 3 occurrences of same species in cell_1, 1 in cell_2
    occurrences_df = pd.DataFrame([
        {
            "grid_id": "cell_1",
            "taxon_key": 5231190,
            "scientific_name": "Panthera onca",
            "common_name": "Jaguar",
            "observation_year": 2018,
            "class": "Mammalia",
            "family": "Felidae",
        },
        {
            "grid_id": "cell_1",
            "taxon_key": 5231190,
            "scientific_name": "Panthera onca",
            "common_name": "Jaguar",
            "observation_year": 2022,
            "class": "Mammalia",
            "family": "Felidae",
        },
        {
            "grid_id": "cell_1",
            "taxon_key": 5231190,
            "scientific_name": "Panthera onca",
            "common_name": None,
            "observation_year": 2020,
            "class": "Mammalia",
            "family": "Felidae",
        },
    ])

    grid_cells_df = pd.DataFrame([
        {"grid_id": "cell_1", "priority_label": "High Priority", "priority_score": 80.0},
    ])

    summaries = analyzer.deduplicate_occurrences(occurrences_df, grid_cells_df)

    assert len(summaries) == 1
    s = summaries[0]
    assert s["grid_id"] == "cell_1"
    assert s["taxon_key"] == 5231190
    assert s["scientific_name"] == "Panthera onca"
    assert s["common_name"] == "Jaguar"
    assert s["recorded_occurrence_count"] == 3
    assert s["observation_year_min"] == 2018
    assert s["observation_year_max"] == 2022
    assert s["grid_priority_score"] == 80.0


def test_fallback_deduplication_by_scientific_name_when_taxon_key_missing(mock_clients):
    """Test deduplication falls back to normalized scientific name when taxon_key is None."""
    gbif, iucn = mock_clients
    analyzer = ConservationAnalyzer(gbif, iucn)

    occurrences_df = pd.DataFrame([
        {
            "grid_id": "cell_1",
            "taxon_key": None,
            "scientific_name": "Puma concolor",
            "common_name": "Cougar",
            "observation_year": 2015,
            "class": "Mammalia",
            "family": "Felidae",
        },
        {
            "grid_id": "cell_1",
            "taxon_key": None,
            "scientific_name": "Puma concolor",
            "common_name": "Mountain Lion",
            "observation_year": 2021,
            "class": "Mammalia",
            "family": "Felidae",
        },
    ])

    grid_cells_df = pd.DataFrame([
        {"grid_id": "cell_1", "priority_label": "Medium Priority", "priority_score": 50.0},
    ])

    summaries = analyzer.deduplicate_occurrences(occurrences_df, grid_cells_df)
    assert len(summaries) == 1
    assert summaries[0]["scientific_name"] == "Puma concolor"
    assert summaries[0]["recorded_occurrence_count"] == 2
    assert summaries[0]["observation_year_min"] == 2015
    assert summaries[0]["observation_year_max"] == 2021


def test_end_to_end_analysis_run(mock_clients):
    """Test full analysis run workflow with mocked GBIF and IUCN responses."""
    gbif, iucn = mock_clients
    analyzer = ConservationAnalyzer(gbif, iucn)

    grid_df = pd.DataFrame([
        {
            "grid_id": "cell_high",
            "priority_label": "High Priority",
            "priority_score": 85.0,
            "grid_lat": -8.0,
            "grid_lon": -61.0,
            "center_lat": -7.875,
            "center_lon": -60.875,
            "detection_count": 50,
        }
    ])

    # GBIF returns 2 records
    gbif.fetch_occurrences_for_cells.return_value = pd.DataFrame([
        {
            "grid_id": "cell_high",
            "taxon_key": 101,
            "scientific_name": "Harpia harpyja",
            "common_name": "Harpy Eagle",
            "kingdom": "Animalia",
            "class": "Aves",
            "family": "Accipitridae",
            "observation_year": 2020,
        },
        {
            "grid_id": "cell_high",
            "taxon_key": 202,
            "scientific_name": "Tapirus terrestris",
            "common_name": "Lowland Tapir",
            "kingdom": "Animalia",
            "class": "Mammalia",
            "family": "Tapiridae",
            "observation_year": 2021,
        }
    ])

    # IUCN enrichment
    def mock_get_assessment(scientific_name, taxon_key=None):
        if scientific_name == "Harpia harpyja":
            return {
                "scientific_name": "Harpia harpyja",
                "iucn_category": "VU",
                "iucn_assessment_date": "2021-08-01",
                "iucn_verified": True,
                "iucn_source": "iucn_api_v4",
            }
        else:
            return {
                "scientific_name": "Tapirus terrestris",
                "iucn_category": "VU",
                "iucn_assessment_date": "2019-01-01",
                "iucn_verified": True,
                "iucn_source": "iucn_api_v4",
            }

    iucn.get_species_assessment.side_effect = mock_get_assessment

    results = analyzer.run_analysis(grid_df=grid_df, grid_size_degrees=0.25)

    assert results["priority_cells_considered"] == 1
    assert results["gbif_occurrence_records_received"] == 2
    assert results["unique_animal_species_found"] == 2
    assert results["species_with_verified_iucn_status"] == 2
    assert results["threatened_species_found"] == 2
    assert len(results["species_grid_summaries"]) == 2
    assert len(results["cell_conservation_summaries"]) == 1

    # Check that privacy is maintained: no coordinates
    for s in results["species_grid_summaries"]:
        assert "latitude" not in s
        assert "longitude" not in s
        assert "decimalLatitude" not in s
        assert "decimalLongitude" not in s
