"""Extractor module for ForestSentinel.

Extracts real active-fire / thermal-anomaly detections from the NASA FIRMS Area API,
validates response integrity, saves the unedited raw CSV for traceability,
and loads the data into a Pandas DataFrame.
"""

from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd
import requests

from forestsentinel.config import Config

logger = logging.getLogger(__name__)


class ExtractionError(Exception):
    """Custom exception raised when NASA FIRMS extraction fails."""


class FirmsExtractor:
    """Extractor for NASA FIRMS Area CSV API."""

    BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

    def __init__(self, config: Config, timeout: int = 30) -> None:
        """Initialize extractor with pipeline configuration."""
        self.config = config
        self.timeout = timeout

    def build_url(self, redact_key: bool = False) -> str:
        """Construct the NASA FIRMS Area API URL.

        Args:
            redact_key: If True, replace the API key with a placeholder for safe logging.
        """
        key_value = "***REDACTED***" if redact_key else self.config.nasa_firms_map_key
        return f"{self.BASE_URL}/{key_value}/{self.config.firms_source}/{self.config.amazon_bbox}/{self.config.day_range}"

    def extract(self, custom_output_dir: Optional[Path] = None) -> Tuple[Path, pd.DataFrame]:
        """Download active-fire detections from NASA FIRMS API.

        Saves raw unedited CSV to the raw data directory with a timestamped filename,
        and returns both the file path and parsed DataFrame.

        Returns:
            Tuple[Path, pd.DataFrame]: (path_to_saved_raw_csv, parsed_dataframe)

        Raises:
            ExtractionError: If network connection fails, status code != 200,
                             or response is an HTML/text error message.
        """
        url = self.build_url(redact_key=False)
        safe_url = self.build_url(redact_key=True)

        logger.info("Requesting active-fire detections from NASA FIRMS: %s", safe_url)

        try:
            response = requests.get(url, timeout=self.timeout)
        except requests.exceptions.Timeout as exc:
            msg = f"Request to NASA FIRMS timed out after {self.timeout}s. Endpoint: {safe_url}"
            logger.error(msg)
            raise ExtractionError(msg) from exc
        except requests.exceptions.ConnectionError as exc:
            msg = f"Network connection error contacting NASA FIRMS at {safe_url}. Please check your internet connection."
            logger.error(msg)
            raise ExtractionError(msg) from exc
        except requests.exceptions.RequestException as exc:
            msg = f"HTTP request failed for NASA FIRMS: {exc}"
            logger.error(msg)
            raise ExtractionError(msg) from exc

        # Check HTTP status code
        if response.status_code != 200:
            error_preview = response.text[:200].strip()
            msg = (
                f"NASA FIRMS API returned HTTP status {response.status_code}.\n"
                f"Response preview: {error_preview}\n"
                f"Actionable note: Check if your NASA FIRMS Map Key is valid, activated, or rate-limited."
            )
            logger.error(msg)
            raise ExtractionError(msg)

        raw_text = response.text

        # Validate that response is CSV, not HTML or text error
        stripped = raw_text.strip()
        lower_stripped = stripped.lower()

        if (
            lower_stripped.startswith("<!doctype")
            or lower_stripped.startswith("<html")
            or "invalid map key" in lower_stripped
            or "bad request" in lower_stripped
            or "not authorized" in lower_stripped
            or "error" in lower_stripped and len(stripped.splitlines()) <= 3
        ):
            msg = (
                f"NASA FIRMS returned an error response instead of valid CSV data:\n"
                f"'{stripped[:300]}'\n"
                f"Actionable note: The NASA FIRMS Map Key may be invalid, expired, or not yet activated.\n"
                f"Keys requested at firms.modaps.eosdis.nasa.gov typically take up to 30 minutes to activate."
            )
            logger.error(msg)
            raise ExtractionError(msg)

        # Parse CSV into DataFrame
        try:
            df = pd.read_csv(io.StringIO(raw_text))
        except Exception as exc:
            msg = f"Failed to parse CSV response from NASA FIRMS: {exc}"
            logger.error(msg)
            raise ExtractionError(msg) from exc

        # Save raw CSV with timestamp
        target_dir = custom_output_dir or self.config.raw_data_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        raw_csv_path = target_dir / f"firms_{timestamp_str}.csv"

        # Write raw CSV text preserving byte-for-byte server content
        with open(raw_csv_path, "w", encoding="utf-8", newline="") as f:
            f.write(raw_text)

        logger.info(
            "Successfully extracted %d raw records from NASA FIRMS. Saved raw CSV to %s",
            len(df),
            raw_csv_path,
        )
        return raw_csv_path, df
