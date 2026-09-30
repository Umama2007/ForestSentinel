"""GBIF Occurrence Search API client for ForestSentinel.

Retrieves biodiversity occurrence records for selected geographic grid cells,
filters strictly for animal species, and returns privacy-safe in-memory normalized
records without storing or exposing exact wildlife coordinates.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional
import urllib.parse
import urllib.request
import json

import pandas as pd

logger = logging.getLogger(__name__)


class GBIFAPIError(Exception):
    """Exception raised for unrecoverable GBIF API errors."""


class GBIFClient:
    """Client for querying the GBIF Occurrence Search API."""

    BASE_URL = "https://api.gbif.org/v1/occurrence/search"
    USER_AGENT = "ForestSentinel/1.0 (Conservation Exposure Analysis; Academic Research)"

    KNOWN_ANIMAL_CLASSES = {
        "mammalia", "aves", "reptilia", "amphibia", "actinopterygii",
        "chondrichthyes", "insecta", "arachnida", "malacostraca", "gastropoda",
        "bivalvia", "cephalopoda", "clitellata", "polychaeta", "anthozoa",
    }

    NON_ANIMAL_KINGDOMS = {
        "plantae", "fungi", "bacteria", "archaea", "protozoa", "chromista", "viruses"
    }

    def __init__(
        self,
        max_records_per_grid: int = 300,
        request_timeout_seconds: int = 30,
        max_retries: int = 3,
        rate_limit_delay_seconds: float = 0.2,
    ) -> None:
        """Initialize GBIF client with safe query parameters.

        Args:
            max_records_per_grid: Maximum occurrences to retrieve per grid cell (default 300).
            request_timeout_seconds: HTTP request timeout in seconds.
            max_retries: Number of retry attempts on transient network errors.
            rate_limit_delay_seconds: Delay between requests to prevent API rate limiting.
        """
        self.max_records = max(1, min(int(max_records_per_grid), 1000))
        self.timeout = max(5, int(request_timeout_seconds))
        self.max_retries = max(1, int(max_retries))
        self.rate_limit_delay = max(0.0, float(rate_limit_delay_seconds))

    def _execute_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute HTTP GET request against GBIF API with exponential backoff retry.

        Args:
            params: Dictionary of query parameters.

        Returns:
            Parsed JSON dictionary from GBIF.
        """
        query_string = urllib.parse.urlencode(params)
        url = f"{self.BASE_URL}?{query_string}"

        headers = {
            "User-Agent": self.USER_AGENT,
            "Accept": "application/json",
        }

        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    status_code = response.getcode()
                    if status_code == 200:
                        raw_body = response.read().decode("utf-8")
                        return json.loads(raw_body)
                    elif status_code in {429, 500, 502, 503, 504}:
                        wait_time = (2 ** attempt) * 0.5
                        logger.warning(
                            "GBIF transient status %d on attempt %d/%d; retrying in %.1fs...",
                            status_code, attempt, self.max_retries, wait_time
                        )
                        time.sleep(wait_time)
                    else:
                        raise GBIFAPIError(f"GBIF API returned unexpected HTTP status {status_code}")
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    wait_time = (2 ** attempt) * 0.5
                    logger.warning(
                        "GBIF request failed (%s) on attempt %d/%d; retrying in %.1fs...",
                        exc, attempt, self.max_retries, wait_time
                    )
                    time.sleep(wait_time)
                else:
                    logger.error("GBIF request exhausted %d retries: %s", self.max_retries, exc)

        raise GBIFAPIError(f"Failed to query GBIF Occurrence API after {self.max_retries} attempts: {last_error}")

    def query_grid_cell(
        self,
        grid_id: str,
        min_lat: float,
        min_lon: float,
        max_lat: float,
        max_lon: float,
    ) -> List[Dict[str, Any]]:
        """Query GBIF occurrences for a specific grid cell bounding box.

        Paginates safely up to max_records_per_grid and normalizes records in memory.
        Exact coordinates are deliberately omitted from returned records to protect sensitive wildlife.

        Args:
            grid_id: Unique grid cell identifier (e.g. 'grid_-8.00_-61.25').
            min_lat: Southern latitude boundary.
            min_lon: Western longitude boundary.
            max_lat: Northern latitude boundary.
            max_lon: Eastern longitude boundary.

        Returns:
            List of normalized animal occurrence dictionaries for the grid cell.
        """
        logger.info(
            "Querying GBIF occurrences for %s (bounds: [%.2f, %.2f] to [%.2f, %.2f])...",
            grid_id, min_lat, min_lon, max_lat, max_lon
        )

        all_records: List[Dict[str, Any]] = []
        page_size = min(300, self.max_records)
        offset = 0

        while len(all_records) < self.max_records:
            limit = min(page_size, self.max_records - len(all_records))
            params = {
                "decimalLatitude": f"{min_lat:.4f},{max_lat:.4f}",
                "decimalLongitude": f"{min_lon:.4f},{max_lon:.4f}",
                "hasCoordinate": "true",
                "hasGeospatialIssue": "false",
                "taxonRank": "SPECIES",
                "limit": limit,
                "offset": offset,
            }

            try:
                data = self._execute_request(params)
            except Exception as exc:
                logger.error("Failed querying GBIF for cell %s: %s", grid_id, exc)
                break

            results = data.get("results", [])
            total_count = data.get("count", 0)

            if not results:
                break

            for raw in results:
                normalized = self._normalize_record(raw, grid_id)
                if normalized is not None:
                    all_records.append(normalized)

            offset += len(results)
            if data.get("endOfRecords", False) or offset >= total_count:
                break

            if self.rate_limit_delay > 0:
                time.sleep(self.rate_limit_delay)

        logger.info(
            "GBIF retrieved %d valid animal occurrence records for %s.",
            len(all_records), grid_id
        )
        return all_records

    def _normalize_record(self, raw: Dict[str, Any], grid_id: str) -> Optional[Dict[str, Any]]:
        """Validate and normalize a raw GBIF record into a privacy-safe animal summary.

        Filters out non-animals, records missing scientific names, and strictly excludes
        exact geographic coordinates.

        Args:
            raw: Raw occurrence dictionary from GBIF.
            grid_id: Grid cell identifier.

        Returns:
            Normalized dictionary or None if record is filtered out.
        """
        # Validate taxonomy: Animalia only
        kingdom = str(raw.get("kingdom", "")).strip().capitalize()
        class_name = str(raw.get("class", "")).strip().capitalize() if raw.get("class") else None

        kingdom_lower = kingdom.lower()
        if kingdom_lower in self.NON_ANIMAL_KINGDOMS:
            return None

        is_animal = kingdom_lower == "animalia" or (
            class_name and class_name.lower() in self.KNOWN_ANIMAL_CLASSES
        )
        if not is_animal:
            return None

        # Validate scientific name: must be non-empty and not generic placeholder
        scientific_name = raw.get("species") or raw.get("scientificName")
        if not scientific_name or not str(scientific_name).strip():
            return None

        cleaned_sci_name = str(scientific_name).strip()
        # Exclude unassigned/incertae sedis placeholder strings
        if cleaned_sci_name.lower() in {"unknown", "incertae sedis", "sp.", "spec."}:
            return None

        # Clean taxon key
        taxon_key_val = raw.get("speciesKey") or raw.get("taxonKey")
        taxon_key: Optional[int] = None
        if taxon_key_val is not None:
            try:
                taxon_key = int(taxon_key_val)
            except (ValueError, TypeError):
                taxon_key = None

        # Observation year
        year_val = raw.get("year")
        obs_year: Optional[int] = None
        if year_val is not None:
            try:
                obs_year = int(year_val)
                if not (1800 <= obs_year <= 2030):
                    obs_year = None
            except (ValueError, TypeError):
                obs_year = None

        # Common name if available in vernacularName
        common_name = raw.get("vernacularName")
        cleaned_common_name = str(common_name).strip() if common_name and str(common_name).strip() else None

        # Taxonomy attributes
        phylum = str(raw.get("phylum")).strip().capitalize() if raw.get("phylum") else None
        order_name = str(raw.get("order")).strip().capitalize() if raw.get("order") else None
        family = str(raw.get("family")).strip().capitalize() if raw.get("family") else None

        # PRIVACY NOTICE: Exact coordinates (decimalLatitude, decimalLongitude, key, etc.)
        # are intentionally omitted from this dictionary.
        return {
            "grid_id": grid_id,
            "taxon_key": taxon_key,
            "scientific_name": cleaned_sci_name,
            "common_name": cleaned_common_name,
            "kingdom": "Animalia",
            "phylum": phylum,
            "class": class_name,
            "order": order_name,
            "family": family,
            "observation_year": obs_year,
        }

    def fetch_occurrences_for_cells(
        self,
        cells_df: pd.DataFrame,
        grid_size_degrees: float = 0.25,
    ) -> pd.DataFrame:
        """Fetch and aggregate GBIF occurrences for a DataFrame of priority grid cells.

        Args:
            cells_df: DataFrame containing 'grid_id', 'grid_lat', 'grid_lon'.
            grid_size_degrees: Resolution of grid cells in degrees.

        Returns:
            DataFrame of normalized animal occurrences across all requested grid cells.
        """
        all_occurrences: List[Dict[str, Any]] = []

        for _, cell in cells_df.iterrows():
            grid_id = str(cell["grid_id"])
            min_lat = float(cell["grid_lat"])
            min_lon = float(cell["grid_lon"])
            max_lat = min_lat + grid_size_degrees
            max_lon = min_lon + grid_size_degrees

            records = self.query_grid_cell(
                grid_id=grid_id,
                min_lat=min_lat,
                min_lon=min_lon,
                max_lat=max_lat,
                max_lon=max_lon,
            )
            all_occurrences.extend(records)

        if not all_occurrences:
            return pd.DataFrame(columns=[
                "grid_id", "taxon_key", "scientific_name", "common_name",
                "kingdom", "phylum", "class", "order", "family", "observation_year"
            ])

        return pd.DataFrame(all_occurrences)
