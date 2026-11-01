"""Supabase (Postgres) integration module for ForestSentinel.

Talks to the Supabase REST API (PostgREST) with the project's service-role key:
creates and updates ETL run rows, records valid fire detections keyed by their
deterministic SHA-256 detection_key (so reruns never duplicate data), and
persists rejected records for data auditing. The table layout lives in
supabase/schema.sql.
"""

from __future__ import annotations

import logging
import math
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)


class SupabaseConfigError(Exception):
    """Exception raised when Supabase credentials or configuration are invalid."""


class SupabaseAPIError(Exception):
    """Exception raised when the Supabase REST API rejects a request."""


def _jsonable(value: Any) -> Any:
    """Make a value safe for JSON / Postgres: NaN and infinities become null, dates become ISO strings."""
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "item") and callable(value.item):  # numpy scalars
        return _jsonable(value.item())
    return value


class SupabaseClient:
    """Client wrapper for Supabase table operations in ForestSentinel."""

    TABLE_DETECTIONS = "fire_detections"
    TABLE_REJECTED = "rejected_records"
    TABLE_RUNS = "etl_runs"

    # Columns each table accepts; anything else in a payload is dropped so
    # report-only fields (e.g. duration_seconds) never break a write.
    COLUMNS: Dict[str, frozenset] = {
        "fire_detections": frozenset({
            "detection_key", "latitude", "longitude", "acq_datetime", "acq_date", "acq_time",
            "satellite", "instrument", "confidence", "frp", "bright_ti4", "bright_ti5",
            "daynight", "source_row_number", "ingested_at", "etl_run_id",
        }),
        "rejected_records": frozenset({
            "etl_run_id", "source_row_number", "raw_record", "rejection_reason", "rejected_at",
        }),
        "etl_runs": frozenset({
            "run_id", "started_at", "finished_at", "status", "api_source", "study_bbox", "day_range",
            "raw_rows_extracted", "exact_duplicates_removed", "cleaning_rejections",
            "pydantic_rejections", "valid_records", "inserted_records", "skipped_existing_records",
            "error_message",
        }),
        "conservation_analysis_runs": frozenset({
            "run_id", "started_at", "finished_at", "status", "source_fire_analysis_run",
            "grid_size_degrees", "priority_cells_considered", "gbif_requests_made",
            "gbif_occurrence_records_received", "unique_animal_species_found",
            "species_with_verified_iucn_status", "threatened_species_found",
            "aggregated_grid_species_records_saved", "error_message",
        }),
        "species_grid_summaries": frozenset({
            "id", "run_id", "grid_id", "taxon_key", "scientific_name", "data", "saved_at",
        }),
        "conservation_assessments": frozenset({
            "id", "taxon_key", "scientific_name", "iucn_category", "iucn_assessment_date",
            "iucn_verified", "iucn_source", "retrieved_at",
        }),
    }

    PAGE_SIZE = 1000  # PostgREST default max rows per response

    def __init__(
        self,
        url: Optional[str],
        service_role_key: Optional[str],
        session: Optional[requests.Session] = None,
        timeout_seconds: int = 30,
    ) -> None:
        """Validate credentials and prepare an authenticated REST session.

        Args:
            url: Supabase project URL, e.g. https://<ref>.supabase.co
            service_role_key: Secret / service_role key (bypasses row-level security).
            session: Optional pre-configured session (useful for mocking in unit tests).
            timeout_seconds: Per-request timeout.
        """
        self.url = self._validate_url(url)
        key = (service_role_key or "").strip()
        if not key:
            raise SupabaseConfigError(
                "SUPABASE_SERVICE_ROLE_KEY is missing.\n"
                "Copy the secret (service_role) key from Supabase -> Project Settings -> API Keys "
                "into your .env file."
            )
        if key.startswith("sb_publishable_"):
            raise SupabaseConfigError(
                "SUPABASE_SERVICE_ROLE_KEY holds the publishable key, which cannot write data.\n"
                "Use the secret key (starts with 'sb_secret_') or the legacy service_role key instead."
            )

        self.rest_url = f"{self.url}/rest/v1"
        self.timeout = timeout_seconds
        self.session = session or requests.Session()
        self.session.headers.update({
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        })
        logger.info("Supabase client ready for project '%s'", self.project_ref)

    @staticmethod
    def _validate_url(url: Optional[str]) -> str:
        cleaned = (url or "").strip().rstrip("/")
        if cleaned.endswith("/rest/v1"):
            cleaned = cleaned[: -len("/rest/v1")]
        parsed = urlparse(cleaned)
        if parsed.scheme != "https" or not parsed.netloc:
            raise SupabaseConfigError(
                f"SUPABASE_URL '{url}' is invalid.\n"
                "Use the Project URL from Supabase -> Project Settings -> Data API, "
                "e.g. https://abcdefgh.supabase.co"
            )
        return cleaned

    @property
    def project_ref(self) -> str:
        """Project reference: the subdomain of the Supabase URL."""
        return urlparse(self.url).netloc.split(".")[0]

    # ------------------------------------------------------------------
    # Generic table helpers (used by the repositories)
    # ------------------------------------------------------------------
    def _request(
        self,
        method: str,
        table: str,
        params: Optional[Dict[str, str]] = None,
        payload: Any = None,
        prefer: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> requests.Response:
        extra = dict(headers or {})
        if prefer:
            extra["Prefer"] = prefer
        resp = self.session.request(
            method,
            f"{self.rest_url}/{table}",
            params=params,
            json=_jsonable(payload) if payload is not None else None,
            headers=extra,
            timeout=self.timeout,
        )
        if resp.status_code >= 400:
            raise SupabaseAPIError(f"{method} {table} failed ({resp.status_code}): {resp.text[:500]}")
        return resp

    def _clean(self, table: str, row: Dict[str, Any]) -> Dict[str, Any]:
        allowed = self.COLUMNS.get(table)
        return {k: v for k, v in row.items() if allowed is None or k in allowed}

    def select(self, table: str, params: Optional[Dict[str, str]] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Read rows (all pages) from a table. `params` are PostgREST filters, e.g. {"run_id": "eq.x"}."""
        rows: List[Dict[str, Any]] = []
        offset = 0
        while True:
            page = self.PAGE_SIZE if limit is None else min(self.PAGE_SIZE, limit - len(rows))
            if page <= 0:
                break
            resp = self._request(
                "GET", table, params={"select": "*", **(params or {})},
                headers={"Range-Unit": "items", "Range": f"{offset}-{offset + page - 1}"},
            )
            batch = resp.json()
            rows.extend(batch)
            if len(batch) < page:
                break
            offset += page
        return rows

    def get_one(self, table: str, column: str, value: str) -> Optional[Dict[str, Any]]:
        """Return the row whose `column` equals `value`, or None."""
        found = self.select(table, params={column: f"eq.{value}"}, limit=1)
        return found[0] if found else None

    def insert(
        self,
        table: str,
        rows: List[Dict[str, Any]],
        on_conflict: Optional[str] = None,
        conflict: str = "error",
        batch_size: int = 500,
    ) -> int:
        """Insert rows in batches; returns how many rows were actually written.

        conflict: "error" (plain insert), "ignore" (skip rows whose key already
        exists) or "merge" (upsert: update existing rows).
        """
        written = 0
        resolution = {"ignore": "resolution=ignore-duplicates,", "merge": "resolution=merge-duplicates,"}.get(conflict, "")
        params = {"on_conflict": on_conflict} if on_conflict else None
        for i in range(0, len(rows), batch_size):
            chunk = [self._clean(table, r) for r in rows[i : i + batch_size]]
            # PostgREST bulk inserts need every object to carry the same keys.
            keys = sorted({k for r in chunk for k in r})
            chunk = [{k: r.get(k) for k in keys} for r in chunk]
            if conflict == "ignore":
                # Ask for the inserted rows back so skipped duplicates can be counted.
                resp = self._request("POST", table, params=params, payload=chunk,
                                     prefer=f"{resolution}return=representation")
                written += len(resp.json())
            else:
                self._request("POST", table, params=params, payload=chunk, prefer=f"{resolution}return=minimal")
                written += len(chunk)
        return written

    def update(self, table: str, match: Dict[str, Any], values: Dict[str, Any]) -> None:
        """Update the rows matching every `column == value` pair in `match`."""
        clean = self._clean(table, values)
        if not clean:
            return
        params = {col: f"eq.{val}" for col, val in match.items()}
        self._request("PATCH", table, params=params, payload=clean, prefer="return=minimal")

    # ------------------------------------------------------------------
    # Part 1: ETL operations
    # ------------------------------------------------------------------
    def create_etl_run(self, metadata: Dict[str, Any]) -> str:
        """Create a new ETL run row with status 'running'.

        Args:
            metadata: Run context including source, bbox, day_range, etc.

        Returns:
            Unique run ID.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        run_id = f"run_{timestamp}_{uuid.uuid4().hex[:6]}"

        run_row: Dict[str, Any] = {
            "run_id": run_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
            "status": "running",
            "api_source": metadata.get("api_source", "unknown"),
            "study_bbox": metadata.get("study_bbox", "unknown"),
            "day_range": metadata.get("day_range", 0),
            "raw_rows_extracted": 0,
            "exact_duplicates_removed": 0,
            "cleaning_rejections": 0,
            "pydantic_rejections": 0,
            "valid_records": 0,
            "inserted_records": 0,
            "skipped_existing_records": 0,
            "error_message": None,
        }

        self.insert(self.TABLE_RUNS, [run_row])
        logger.info("Created Supabase ETL run row: %s", run_id)
        return run_id

    def update_etl_run(self, run_id: str, updates: Dict[str, Any]) -> None:
        """Update an existing ETL run row.

        Args:
            run_id: The run identifier.
            updates: Dictionary of fields to update.
        """
        self.update(self.TABLE_RUNS, {"run_id": run_id}, updates)
        logger.info("Updated Supabase ETL run %s with status '%s'", run_id, updates.get("status"))

    def save_fire_detections(
        self,
        run_id: str,
        valid_records: List[Dict[str, Any]],
        batch_size: int = 500,
    ) -> Tuple[int, int]:
        """Save validated fire detections keyed by detection_key.

        Deduplication rule:
        If a row with the same detection_key already exists it is skipped and
        counted under skipped_existing_records to prevent duplicates across runs.

        Args:
            run_id: ID of the executing ETL run.
            valid_records: List of validated detection dictionaries.
            batch_size: Rows per insert request.

        Returns:
            Tuple[int, int]: (inserted_records_count, skipped_existing_count)
        """
        if not valid_records:
            return 0, 0

        rows = []
        for record in valid_records:
            row = dict(record)
            row["etl_run_id"] = run_id
            row.setdefault("ingested_at", datetime.now(timezone.utc).isoformat())
            rows.append(row)

        inserted_count = self.insert(
            self.TABLE_DETECTIONS, rows, on_conflict="detection_key", conflict="ignore", batch_size=batch_size
        )
        skipped_count = len(rows) - inserted_count

        logger.info(
            "Supabase fire_detections persistence complete: %d inserted, %d skipped duplicates",
            inserted_count,
            skipped_count,
        )
        return inserted_count, skipped_count

    def save_rejected_records(
        self,
        run_id: str,
        rejected_records: List[Dict[str, Any]],
        batch_size: int = 500,
    ) -> int:
        """Save rejected records into the rejected_records table for auditing.

        Args:
            run_id: ID of the executing ETL run.
            rejected_records: List of rejected dictionaries with rejection reasons.
            batch_size: Rows per insert request.

        Returns:
            Total number of rejected records saved.
        """
        if not rejected_records:
            return 0

        rows = [
            {
                "etl_run_id": run_id,
                "source_row_number": item.get("source_row_number", 0),
                "raw_record": item.get("raw_record", {}),
                "rejection_reason": item.get("rejection_reason", "Unknown reason"),
                "rejected_at": item.get("rejected_at") or datetime.now(timezone.utc).isoformat(),
            }
            for item in rejected_records
        ]
        saved_count = self.insert(self.TABLE_REJECTED, rows, batch_size=batch_size)
        logger.info("Saved %d rejected records to Supabase table '%s'", saved_count, self.TABLE_REJECTED)
        return saved_count
