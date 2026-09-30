"""Unit tests for IUCN Red List API v4 client in ForestSentinel."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from forestsentinel.iucn_client import IUCNClient


def test_missing_token_returns_unverified_without_network_call():
    """Test that when IUCN_API_TOKEN is None or empty, unverified status is returned."""
    client = IUCNClient(api_token=None)
    assert not client.is_configured

    with patch.object(client, "_fetch_from_api") as mock_fetch:
        result = client.get_species_assessment("Panthera onca", taxon_key=5231190)
        assert not mock_fetch.called
        assert result["scientific_name"] == "Panthera onca"
        assert result["iucn_category"] is None
        assert result["iucn_verified"] is False
        assert result["iucn_source"] == "unavailable"


def test_parse_valid_v4_assessment_payload():
    """Test parsing category, date, and verification flag from IUCN v4 payload."""
    client = IUCNClient(api_token="valid_test_token")
    mock_payload = {
        "taxon": {"scientific_name": "Panthera onca"},
        "assessments": [
            {
                "assessment_id": 12345,
                "year_published": "2018",
                "assessment_date": "2016-05-18",
                "red_list_category": {"code": "NT", "description": "Near Threatened"},
                "latest": True,
            }
        ]
    }

    result = client._parse_iucn_response(mock_payload, "Panthera onca")
    assert result["scientific_name"] == "Panthera onca"
    assert result["iucn_category"] == "NT"
    assert result["iucn_assessment_date"] == "2016-05-18"
    assert result["iucn_verified"] is True
    assert result["iucn_source"] == "iucn_api_v4"


def test_parse_threatened_v4_assessment():
    """Test parsing a Critically Endangered (CR) assessment."""
    client = IUCNClient(api_token="valid_test_token")
    mock_payload = {
        "assessments": [
            {
                "red_list_category": {"code": "CR"},
                "year_published": "2021",
                "latest": True,
            }
        ]
    }

    result = client._parse_iucn_response(mock_payload, "Ateles belzebuth")
    assert result["iucn_category"] == "CR"
    assert result["iucn_verified"] is True


def test_parse_unrecognized_or_empty_category_never_guesses():
    """Test that if category is missing or invalid, category remains None and unverified."""
    client = IUCNClient(api_token="valid_test_token")
    mock_payload = {
        "assessments": [
            {"red_list_category": {"code": "INVALID_CODE"}}
        ]
    }

    result = client._parse_iucn_response(mock_payload, "Unknown species")
    assert result["iucn_category"] is None
    assert result["iucn_verified"] is False
    assert result["iucn_source"] == "unavailable"


def test_in_memory_caching_avoids_repeated_requests():
    """Test that repeated lookups for the same scientific name use memory cache."""
    client = IUCNClient(api_token="test_token")
    mock_assessment = {
        "scientific_name": "Tapirus terrestris",
        "iucn_category": "VU",
        "iucn_assessment_date": "2019-01-01",
        "iucn_verified": True,
        "iucn_source": "iucn_api_v4",
    }

    with patch.object(client, "_fetch_from_api", return_value=mock_assessment) as mock_fetch:
        res1 = client.get_species_assessment("Tapirus terrestris")
        res2 = client.get_species_assessment("Tapirus terrestris")
        # Same result, but _fetch_from_api called only once
        assert res1 == res2
        assert mock_fetch.call_count == 1
