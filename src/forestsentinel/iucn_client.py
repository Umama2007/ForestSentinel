"""IUCN Red List API v4 client for ForestSentinel.

Enriches species records with verified conservation statuses from the official
IUCN Red List API v4. Provides caching and defensive fallback when credentials
are not configured or when species data is absent.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)


class IUCNClient:
    """Client for querying the IUCN Red List API v4 with local and Firestore caching."""

    DEFAULT_BASE_URL = "https://api.iucnredlist.org"
    USER_AGENT = "ForestSentinel/1.0 (Conservation Exposure Analysis; Academic Research)"

    # Recognized standard IUCN Red List categories
    RECOGNIZED_CATEGORIES = {
        "CR": "Critically Endangered",
        "EN": "Endangered",
        "VU": "Vulnerable",
        "NT": "Near Threatened",
        "LC": "Least Concern",
        "DD": "Data Deficient",
        "EW": "Extinct in the Wild",
        "EX": "Extinct",
    }

    THREATENED_CATEGORIES = {"CR", "EN", "VU"}

    def __init__(
        self,
        api_token: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        firestore_repository: Optional[Any] = None,
        timeout_seconds: int = 20,
        max_retries: int = 2,
    ) -> None:
        """Initialize IUCN Red List client.

        Args:
            api_token: Optional personal API token for IUCN Red List v4.
            base_url: Base endpoint URL for the IUCN API.
            firestore_repository: Optional ConservationRepository instance for Firestore caching.
            timeout_seconds: Timeout for HTTP requests in seconds.
            max_retries: Maximum retry attempts for transient errors.
        """
        self.api_token = api_token.strip() if api_token and api_token.strip() else None
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.repository = firestore_repository
        self.timeout = max(5, int(timeout_seconds))
        self.max_retries = max(1, int(max_retries))

        # In-memory session cache to prevent redundant lookups in the same execution
        self._memory_cache: Dict[str, Dict[str, Any]] = {}

    @property
    def is_configured(self) -> bool:
        """Check if a valid IUCN API token is configured."""
        return self.api_token is not None and len(self.api_token) > 0

    def get_species_assessment(
        self,
        scientific_name: str,
        taxon_key: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Retrieve verified IUCN conservation category for a scientific name.

        Checks memory cache first, then Firestore cache, and queries the IUCN API
        only if credentials are available and no cache entry exists.

        Args:
            scientific_name: Binomial scientific name (e.g., 'Panthera onca').
            taxon_key: Optional GBIF taxon identifier for cache correlation.

        Returns:
            Normalized dictionary containing:
            - scientific_name
            - iucn_category (CR, EN, VU, NT, LC, DD, etc. or None)
            - iucn_assessment_date (str or None)
            - iucn_verified (bool)
            - iucn_source (str: 'iucn_api_v4', 'firestore_cache', or 'unavailable')
        """
        if not scientific_name or not scientific_name.strip():
            return {
                "scientific_name": scientific_name,
                "taxon_key": taxon_key,
                "iucn_category": None,
                "iucn_assessment_date": None,
                "iucn_verified": False,
                "iucn_source": "unavailable",
            }

        norm_name = " ".join(scientific_name.strip().split())
        cache_key = norm_name.lower()

        # 1. In-memory cache check
        if cache_key in self._memory_cache:
            return self._memory_cache[cache_key]

        # 2. Firestore cache check (if repository available)
        if self.repository is not None:
            cached_doc = self.repository.get_cached_assessment(scientific_name=norm_name, taxon_key=taxon_key)
            if cached_doc:
                self._memory_cache[cache_key] = cached_doc
                return cached_doc

        # 3. Check if token is available
        if not self.is_configured:
            unverified_result = {
                "scientific_name": norm_name,
                "taxon_key": taxon_key,
                "iucn_category": None,
                "iucn_assessment_date": None,
                "iucn_verified": False,
                "iucn_source": "unavailable",
            }
            self._memory_cache[cache_key] = unverified_result
            return unverified_result

        # 4. Query live IUCN Red List API v4
        api_result = self._fetch_from_api(norm_name)
        if api_result["iucn_verified"]:
            api_result["taxon_key"] = taxon_key
            # Cache in Firestore if repository configured
            if self.repository is not None:
                try:
                    self.repository.save_cached_assessment(api_result)
                except Exception as exc:
                    logger.warning("Failed to cache IUCN assessment in Firestore: %s", exc)

        self._memory_cache[cache_key] = api_result
        return api_result

    def _fetch_from_api(self, scientific_name: str) -> Dict[str, Any]:
        """Perform authenticated HTTP request to IUCN v4 API.

        Args:
            scientific_name: Clean scientific name.

        Returns:
            Normalized assessment dictionary.
        """
        encoded_name = urllib.parse.quote(scientific_name)
        # Primary v4 taxa endpoint
        url = f"{self.base_url}/api/v4/taxa/scientific_name?name={encoded_name}"

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "User-Agent": self.USER_AGENT,
            "Accept": "application/json",
        }

        for attempt in range(1, self.max_retries + 1):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    if resp.getcode() == 200:
                        body = resp.read().decode("utf-8")
                        data = json.loads(body)
                        return self._parse_iucn_response(data, scientific_name)
                    elif resp.getcode() == 404:
                        logger.info("IUCN v4 reported no match for species '%s'", scientific_name)
                        return {
                            "scientific_name": scientific_name,
                            "iucn_category": None,
                            "iucn_assessment_date": None,
                            "iucn_verified": False,
                            "iucn_source": "unavailable",
                        }
                    elif resp.getcode() == 429:
                        time.sleep(2.0 * attempt)
                    else:
                        logger.warning("IUCN API returned HTTP %d for '%s'", resp.getcode(), scientific_name)
            except urllib.error.HTTPError as http_err:
                if http_err.code == 404:
                    return {
                        "scientific_name": scientific_name,
                        "iucn_category": None,
                        "iucn_assessment_date": None,
                        "iucn_verified": False,
                        "iucn_source": "unavailable",
                    }
                elif http_err.code in {401, 403}:
                    logger.error("IUCN API Authentication failed (HTTP %d). Check IUCN_API_TOKEN.", http_err.code)
                    break
                elif http_err.code == 429:
                    time.sleep(2.0 * attempt)
                else:
                    logger.warning("IUCN HTTP error %d on attempt %d: %s", http_err.code, attempt, http_err)
            except Exception as exc:
                logger.warning("IUCN request exception for '%s': %s", scientific_name, exc)
                if attempt < self.max_retries:
                    time.sleep(1.0)

        # Fallback if unverified or unreachable
        return {
            "scientific_name": scientific_name,
            "iucn_category": None,
            "iucn_assessment_date": None,
            "iucn_verified": False,
            "iucn_source": "unavailable",
        }

    def _parse_iucn_response(self, data: Dict[str, Any], scientific_name: str) -> Dict[str, Any]:
        """Safely parse category and assessment timestamp from IUCN v4 payload.

        Args:
            data: Parsed JSON payload from IUCN v4 API.
            scientific_name: Expected scientific name.

        Returns:
            Normalized dictionary with verified status.
        """
        category: Optional[str] = None
        assessment_date: Optional[str] = None

        assessments = data.get("assessments", [])
        if isinstance(assessments, list) and assessments:
            # Pick latest assessment if multiple exist
            selected_assessment = assessments[0]
            for a in assessments:
                if isinstance(a, dict) and a.get("latest", False):
                    selected_assessment = a
                    break

            # Extract category
            cat_obj = selected_assessment.get("red_list_category")
            if isinstance(cat_obj, dict):
                category = cat_obj.get("code")
            elif isinstance(cat_obj, str):
                category = cat_obj

            if not category:
                category = selected_assessment.get("red_list_category_code") or selected_assessment.get("category")

            # Extract date
            assessment_date = (
                selected_assessment.get("assessment_date")
                or selected_assessment.get("year_published")
                or selected_assessment.get("year")
            )
        elif "red_list_category" in data:
            cat_obj = data["red_list_category"]
            category = cat_obj.get("code") if isinstance(cat_obj, dict) else str(cat_obj)
            assessment_date = data.get("assessment_date") or data.get("year_published")
        elif "category" in data:
            category = str(data["category"])
            assessment_date = data.get("assessment_date")

        # Validate category code against standard IUCN vocabulary
        if category and str(category).strip().upper() in self.RECOGNIZED_CATEGORIES:
            cleaned_cat = str(category).strip().upper()
            return {
                "scientific_name": scientific_name,
                "iucn_category": cleaned_cat,
                "iucn_assessment_date": str(assessment_date).strip() if assessment_date else None,
                "iucn_verified": True,
                "iucn_source": "iucn_api_v4",
            }

        # If category is absent or unparseable, never guess
        return {
            "scientific_name": scientific_name,
            "iucn_category": None,
            "iucn_assessment_date": None,
            "iucn_verified": False,
            "iucn_source": "unavailable",
        }
