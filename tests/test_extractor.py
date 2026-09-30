"""Unit tests for the extractor module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from forestsentinel.config import Config
from forestsentinel.extractor import ExtractionError, FirmsExtractor


@pytest.fixture
def mock_config(tmp_path: Path) -> Config:
    return Config(
        nasa_firms_map_key="my_secret_key_123",
        firms_source="VIIRS_NOAA21_NRT",
        amazon_bbox="-62,-10,-58,-6",
        bbox_coords=(-62.0, -10.0, -58.0, -6.0),
        day_range=5,
        firebase_service_account_path=tmp_path / "firebase.json",
        firebase_project_id="test-proj",
        log_level="INFO",
        base_dir=tmp_path,
        raw_data_dir=tmp_path / "data" / "raw",
        reports_dir=tmp_path / "reports",
        logs_dir=tmp_path / "logs",
        secrets_dir=tmp_path / "secrets",
    )


def test_build_url_and_redaction(mock_config: Config):
    extractor = FirmsExtractor(mock_config)
    real_url = extractor.build_url(redact_key=False)
    redacted_url = extractor.build_url(redact_key=True)

    assert "my_secret_key_123" in real_url
    assert "my_secret_key_123" not in redacted_url
    assert "***REDACTED***" in redacted_url
    assert "VIIRS_NOAA21_NRT" in redacted_url
    assert "-62,-10,-58,-6" in redacted_url
    assert "/5" in redacted_url


def test_extract_handles_html_error(mock_config: Config):
    extractor = FirmsExtractor(mock_config)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "<html><body>Invalid Map Key</body></html>"

    with patch("requests.get", return_value=mock_resp):
        with pytest.raises(ExtractionError) as exc_info:
            extractor.extract()

    assert "NASA FIRMS returned an error response" in str(exc_info.value)
    assert "Map Key may be invalid, expired, or not yet activated" in str(exc_info.value)


def test_extract_handles_non_200_status(mock_config: Config):
    extractor = FirmsExtractor(mock_config)

    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.text = "Forbidden"

    with patch("requests.get", return_value=mock_resp):
        with pytest.raises(ExtractionError) as exc_info:
            extractor.extract()

    assert "HTTP status 403" in str(exc_info.value)


def test_extract_saves_raw_csv_and_returns_dataframe(mock_config: Config):
    extractor = FirmsExtractor(mock_config)

    sample_csv = (
        "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight\n"
        "-7.1234,-60.5432,325.5,0.4,0.4,2026-09-28,1430,NOAA-21,VIIRS,nominal,2.0NRT,295.2,10.5,D\n"
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = sample_csv

    with patch("requests.get", return_value=mock_resp):
        csv_path, df = extractor.extract()

    assert csv_path.is_file()
    assert len(df) == 1
    assert df.iloc[0]["latitude"] == -7.1234
    # Ensure byte-for-byte server content was written to file
    assert csv_path.read_text(encoding="utf-8") == sample_csv
