"""Unit tests for GBIF Occurrence API client in ForestSentinel."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from forestsentinel.gbif_client import GBIFAPIError, GBIFClient


@pytest.fixture
def gbif_client() -> GBIFClient:
    """Provide GBIF client instance with small limits for testing."""
    return GBIFClient(max_records_per_grid=50, request_timeout_seconds=5, max_retries=2, rate_limit_delay_seconds=0.0)


def test_normalize_valid_animal_record(gbif_client: GBIFClient):
    """Test normalization of valid animal record removes raw coordinates."""
    raw = {
        "key": 999123456,
        "speciesKey": 5231190,
        "scientificName": "Panthera onca (Linnaeus, 1758)",
        "species": "Panthera onca",
        "vernacularName": "Jaguar",
        "kingdom": "Animalia",
        "phylum": "Chordata",
        "class": "Mammalia",
        "order": "Carnivora",
        "family": "Felidae",
        "year": 2021,
        "decimalLatitude": -8.123456,
        "decimalLongitude": -61.234567,
    }

    normalized = gbif_client._normalize_record(raw, grid_id="grid_-8.00_-61.25")

    assert normalized is not None
    assert normalized["grid_id"] == "grid_-8.00_-61.25"
    assert normalized["taxon_key"] == 5231190
    assert normalized["scientific_name"] == "Panthera onca"
    assert normalized["common_name"] == "Jaguar"
    assert normalized["kingdom"] == "Animalia"
    assert normalized["class"] == "Mammalia"
    assert normalized["observation_year"] == 2021

    # CRITICAL PRIVACY ASSERTIONS: exact coordinates and raw IDs must not be in normalized record
    assert "decimalLatitude" not in normalized
    assert "decimalLongitude" not in normalized
    assert "latitude" not in normalized
    assert "longitude" not in normalized
    assert "key" not in normalized


def test_filter_out_plants_and_fungi(gbif_client: GBIFClient):
    """Test that plant, fungi, and non-animal records are strictly excluded."""
    plant_raw = {
        "speciesKey": 12345,
        "species": "Hevea brasiliensis",
        "kingdom": "Plantae",
        "decimalLatitude": -8.5,
        "decimalLongitude": -61.5,
    }
    fungi_raw = {
        "speciesKey": 67890,
        "species": "Agaricus bisporus",
        "kingdom": "Fungi",
        "decimalLatitude": -8.5,
        "decimalLongitude": -61.5,
    }

    assert gbif_client._normalize_record(plant_raw, "grid_1") is None
    assert gbif_client._normalize_record(fungi_raw, "grid_1") is None


def test_filter_out_missing_or_generic_scientific_name(gbif_client: GBIFClient):
    """Test that records with empty, None, or generic names are excluded."""
    missing_name = {
        "speciesKey": 111,
        "kingdom": "Animalia",
        "class": "Aves",
    }
    placeholder_name = {
        "speciesKey": 222,
        "species": "incertae sedis",
        "kingdom": "Animalia",
    }

    assert gbif_client._normalize_record(missing_name, "grid_1") is None
    assert gbif_client._normalize_record(placeholder_name, "grid_1") is None


def test_pagination_and_query_grid_cell(gbif_client: GBIFClient):
    """Test safe query execution and pagination loop with mocked HTTP response."""
    mock_payload = {
        "count": 2,
        "endOfRecords": True,
        "results": [
            {
                "speciesKey": 100,
                "species": "Harpia harpyja",
                "vernacularName": "Harpy Eagle",
                "kingdom": "Animalia",
                "class": "Aves",
                "year": 2020,
            },
            {
                "speciesKey": 200,
                "species": "Tapirus terrestris",
                "vernacularName": "South American Tapir",
                "kingdom": "Animalia",
                "class": "Mammalia",
                "year": 2019,
            }
        ]
    }

    with patch.object(gbif_client, "_execute_request", return_value=mock_payload) as mock_req:
        records = gbif_client.query_grid_cell(
            grid_id="grid_-8.00_-61.25",
            min_lat=-8.0,
            min_lon=-61.25,
            max_lat=-7.75,
            max_lon=-61.0,
        )

        assert mock_req.called
        assert len(records) == 2
        assert records[0]["scientific_name"] == "Harpia harpyja"
        assert records[1]["scientific_name"] == "Tapirus terrestris"


def test_empty_response_handled_gracefully(gbif_client: GBIFClient):
    """Test that empty results from GBIF return an empty list without error."""
    mock_payload = {"count": 0, "endOfRecords": True, "results": []}

    with patch.object(gbif_client, "_execute_request", return_value=mock_payload):
        records = gbif_client.query_grid_cell(
            grid_id="grid_empty",
            min_lat=-8.0,
            min_lon=-61.25,
            max_lat=-7.75,
            max_lon=-61.0,
        )
        assert records == []


def test_fetch_occurrences_for_multiple_cells(gbif_client: GBIFClient):
    """Test batch querying for a DataFrame of cells."""
    cells_df = pd.DataFrame([
        {"grid_id": "cell_1", "grid_lat": -8.0, "grid_lon": -61.0},
        {"grid_id": "cell_2", "grid_lat": -9.0, "grid_lon": -60.0},
    ])

    sample_rec = {
        "speciesKey": 555,
        "species": "Pteronura brasiliensis",
        "kingdom": "Animalia",
        "class": "Mammalia",
        "year": 2022,
    }

    with patch.object(gbif_client, "_execute_request", return_value={"count": 1, "endOfRecords": True, "results": [sample_rec]}):
        df = gbif_client.fetch_occurrences_for_cells(cells_df, grid_size_degrees=0.25)
        assert len(df) == 2
        assert "cell_1" in df["grid_id"].values
        assert "cell_2" in df["grid_id"].values
        # Verify no coordinate columns
        assert "decimalLatitude" not in df.columns
        assert "decimalLongitude" not in df.columns
