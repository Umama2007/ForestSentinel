"""Unit tests for configuration loading and validation."""

from __future__ import annotations

from pathlib import Path
import pytest

from forestsentinel.config import Config, load_config, _validate_bbox, _validate_day_range, _validate_map_key


def test_validate_map_key_missing_or_empty():
    with pytest.raises(ValueError) as exc:
        _validate_map_key(None)
    assert "Missing NASA_FIRMS_MAP_KEY" in str(exc.value)

    with pytest.raises(ValueError) as exc:
        _validate_map_key("   ")
    assert "Missing NASA_FIRMS_MAP_KEY" in str(exc.value)


def test_validate_map_key_placeholder():
    with pytest.raises(ValueError) as exc:
        _validate_map_key("replace_with_your_real_map_key")
    assert "placeholder value" in str(exc.value)


def test_validate_bbox_valid():
    formatted, coords = _validate_bbox("-62,-10,-58,-6")
    assert formatted == "-62.0,-10.0,-58.0,-6.0"
    assert coords == (-62.0, -10.0, -58.0, -6.0)


def test_validate_bbox_invalid_parts():
    with pytest.raises(ValueError) as exc:
        _validate_bbox("-62,-10,-58")
    assert "Must contain exactly 4 comma-separated values" in str(exc.value)


def test_validate_bbox_inverted_bounds():
    with pytest.raises(ValueError) as exc:
        _validate_bbox("-58,-10,-62,-6")  # west > east
    assert "west" in str(exc.value) and "less than east" in str(exc.value)


def test_validate_day_range():
    assert _validate_day_range("5") == 5
    assert _validate_day_range(None) == 10

    with pytest.raises(ValueError) as exc:
        _validate_day_range("0")
    assert "between 1 and 30" in str(exc.value)

    with pytest.raises(ValueError) as exc:
        _validate_day_range("40")
    assert "between 1 and 30" in str(exc.value)


def test_config_redacted_repr():
    cfg = Config(
        nasa_firms_map_key="abcdef1234567890",
        firms_source="VIIRS_NOAA21_NRT",
        amazon_bbox="-62,-10,-58,-6",
        bbox_coords=(-62.0, -10.0, -58.0, -6.0),
        day_range=10,
        supabase_url="https://testproject.supabase.co",
        supabase_service_role_key="sb_secret_test_key_1234567890",
        log_level="INFO",
        base_dir=Path("."),
        raw_data_dir=Path("./data/raw"),
        reports_dir=Path("./reports"),
        logs_dir=Path("./logs"),
        secrets_dir=Path("./secrets"),
    )
    repr_str = cfg.redacted_repr()
    assert "abcdef1234567890" not in repr_str
    assert "abcd...7890" in repr_str
