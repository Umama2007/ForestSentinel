"""Analytics Repository module for ForestSentinel.

Provides read-only access to validated active-fire / thermal-anomaly detections
stored in Firebase Cloud Firestore and loads them into a structured Pandas DataFrame.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

from forestsentinel.firebase_client import FirebaseClient

logger = logging.getLogger(__name__)


class NoDataError(Exception):
    """Exception raised when no records are found in the fire_detections collection."""


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

    def __init__(self, firebase_client: FirebaseClient) -> None:
        """Initialize with an existing authenticated FirebaseClient.

        Args:
            firebase_client: Authenticated FirebaseClient instance.
        """
        self.firebase_client = firebase_client
        self.db = firebase_client.db

    def load_fire_detections(self, limit: Optional[int] = None) -> pd.DataFrame:
        """Fetch validated fire detection documents from Firestore into a clean DataFrame.

        Never writes, updates, or deletes existing data.

        Args:
            limit: Optional maximum number of documents to read.

        Returns:
            Pandas DataFrame containing validated active-fire detection records.

        Raises:
            NoDataError: If the fire_detections collection is empty or non-existent.
        """
        logger.info("Reading validated fire detections from Cloud Firestore collection '%s'...", FirebaseClient.COLLECTION_DETECTIONS)
        collection_ref = self.db.collection(FirebaseClient.COLLECTION_DETECTIONS)

        query = collection_ref
        if limit is not None and limit > 0:
            query = query.limit(limit)

        records: List[Dict[str, Any]] = []
        try:
            # Stream documents for memory-efficient iteration
            docs = query.stream()
            for doc in docs:
                data = doc.to_dict()
                if data:
                    records.append(data)
        except Exception as exc:
            logger.error("Failed to query Firestore fire_detections: %s", exc)
            raise

        if not records:
            msg = (
                "No Firestore fire_detections were found.\n"
                "Run Part 1 with 'python run_pipeline.py' before running Part 2 analysis."
            )
            logger.warning(msg)
            raise NoDataError(msg)

        logger.info("Retrieved %d raw detection documents from Firestore.", len(records))

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
