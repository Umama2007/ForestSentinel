"""Analytics Repository module for ForestSentinel.

Provides read-only access to validated active-fire / thermal-anomaly detections
stored in the Supabase fire_detections table and loads them into a structured
Pandas DataFrame.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from forestsentinel.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)


class NoDataError(Exception):
    """Exception raised when no records are found in the fire_detections table."""


class AnalyticsRepository:
    """Read-only data access layer for ForestSentinel analytics."""

    EXPECTED_COLUMNS = [
        "detection_key",
        "latitude",
        "longitude",
        "acq_datetime",
        "acq_date",
        "acq_time",
        "satellite",
        "instrument",
        "confidence",
        "frp",
        "bright_ti4",
        "bright_ti5",
        "daynight",
        "ingested_at",
        "etl_run_id",
    ]

    def __init__(self, db_client: SupabaseClient) -> None:
        """Initialize with an existing authenticated SupabaseClient.

        Args:
            db_client: Authenticated SupabaseClient instance.
        """
        self.db_client = db_client

    def load_fire_detections(self, limit: Optional[int] = None) -> pd.DataFrame:
        """Fetch validated fire detection rows from Supabase into a clean DataFrame.

        Never writes, updates, or deletes existing data.

        Args:
            limit: Optional maximum number of rows to read.

        Returns:
            Pandas DataFrame containing validated active-fire detection records.

        Raises:
            NoDataError: If the fire_detections table is empty.
        """
        logger.info("Reading validated fire detections from Supabase table '%s'...", SupabaseClient.TABLE_DETECTIONS)

        try:
            records: List[Dict[str, Any]] = self.db_client.select(
                SupabaseClient.TABLE_DETECTIONS,
                params={"order": "acq_datetime.desc"},
                limit=limit if limit and limit > 0 else None,
            )
        except Exception as exc:
            logger.error("Failed to query Supabase fire_detections: %s", exc)
            raise

        if not records:
            msg = (
                "No fire_detections were found in the database.\n"
                "Run Part 1 with 'python run_pipeline.py' before running Part 2 analysis."
            )
            logger.warning(msg)
            raise NoDataError(msg)

        logger.info("Retrieved %d raw detection rows from Supabase.", len(records))

        # Convert to DataFrame
        df = pd.DataFrame(records)

        # Ensure all expected columns are present, padding with None if missing
        for col in self.EXPECTED_COLUMNS:
            if col not in df.columns:
                df[col] = None

        # Reorder to standard schema
        df = df[self.EXPECTED_COLUMNS].copy()

        # Coerce numeric types
        for col in ["latitude", "longitude", "frp", "bright_ti4", "bright_ti5"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        logger.info(
            "Constructed analysis DataFrame with %d rows and %d columns. Memory usage: %.2f KB",
            len(df),
            len(df.columns),
            df.memory_usage(deep=True).sum() / 1024,
        )
        return df
