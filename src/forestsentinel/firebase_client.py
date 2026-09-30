"""Firebase Cloud Firestore integration module for ForestSentinel.

Manages connections via firebase-admin SDK, creates and updates ETL run metadata,
records valid fire detections using deterministic document IDs for deduplication,
and persists rejected records for data auditing.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import uuid

import firebase_admin
from firebase_admin import credentials, firestore

logger = logging.getLogger(__name__)


class FirebaseConfigError(Exception):
    """Exception raised when Firebase credentials or configuration are invalid."""


class FirebaseClient:
    """Client wrapper for Firebase Cloud Firestore operations in ForestSentinel ETL."""

    COLLECTION_DETECTIONS = "fire_detections"
    COLLECTION_REJECTED = "rejected_records"
    COLLECTION_RUNS = "etl_runs"

    def __init__(
        self,
        service_account_path: Path | str,
        project_id: Optional[str] = None,
        firestore_client: Optional[Any] = None,
    ) -> None:
        """Initialize Firebase Admin SDK and Cloud Firestore client.

        Args:
            service_account_path: Local filesystem path to the service account JSON file.
            project_id: Optional Firebase project ID.
            firestore_client: Optional pre-configured client (useful for mocking in unit tests).
        """
        self.service_account_path = Path(service_account_path).resolve()
        self.project_id = project_id

        if firestore_client is not None:
            self.db = firestore_client
            logger.info("Using injected Firestore client instance.")
            return

        self.db = self._init_firebase()

    def _init_firebase(self) -> Any:
        """Validate credentials file and initialize Firebase Admin SDK singleton."""
        if not self.service_account_path.is_file():
            raise FirebaseConfigError(
                f"Firebase service account file not found at:\n  '{self.service_account_path}'\n\n"
                f"Actionable instructions:\n"
                f"1. Go to Firebase Console (https://console.firebase.google.com/)\n"
                f"2. Navigate to Project Settings -> Service Accounts\n"
                f"3. Click 'Generate new private key' and download the JSON file\n"
                f"4. Save it as 'secrets/firebase-service-account.json' (or configure FIREBASE_SERVICE_ACCOUNT_PATH in .env)"
            )

        # Validate JSON content integrity
        try:
            with open(self.service_account_path, "r", encoding="utf-8") as f:
                cred_data = json.load(f)
            if cred_data.get("type") != "service_account" or "private_key" not in cred_data:
                raise ValueError("JSON file is not a valid Google service account key.")
            # Check for placeholder
            if "replace_with_your_firebase_project_id" in str(cred_data):
                raise ValueError("Service account JSON contains example placeholder values.")
        except Exception as exc:
            raise FirebaseConfigError(
                f"Invalid Firebase service account JSON at '{self.service_account_path}': {exc}"
            ) from exc

        # Initialize Firebase Admin App once
        app_name = f"forestsentinel_{self.project_id or 'default'}"
        try:
            app = firebase_admin.get_app(app_name)
        except ValueError:
            cred = credentials.Certificate(str(self.service_account_path))
            options = {"projectId": self.project_id} if self.project_id else None
            app = firebase_admin.initialize_app(cred, options=options, name=app_name)

        logger.info("Firebase Admin SDK successfully initialized for project '%s'", self.project_id)
        return firestore.client(app=app)

    def create_etl_run(self, metadata: Dict[str, Any]) -> str:
        """Create a new ETL run document with status 'running'.

        Args:
            metadata: Run context including source, bbox, day_range, etc.

        Returns:
            Unique run document ID.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        run_id = f"run_{timestamp}_{uuid.uuid4().hex[:6]}"

        run_doc: Dict[str, Any] = {
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

        self.db.collection(self.COLLECTION_RUNS).document(run_id).set(run_doc)
        logger.info("Created Firestore ETL run document: %s", run_id)
        return run_id

    def update_etl_run(self, run_id: str, updates: Dict[str, Any]) -> None:
        """Update an existing ETL run document in Firestore.

        Args:
            run_id: The run identifier document key.
            updates: Dictionary of fields to update.
        """
        doc_ref = self.db.collection(self.COLLECTION_RUNS).document(run_id)
        doc_ref.update(updates)
        logger.info("Updated Firestore ETL run %s with status '%s'", run_id, updates.get("status"))

    def save_fire_detections(
        self,
        run_id: str,
        valid_records: List[Dict[str, Any]],
        batch_size: int = 400,
    ) -> Tuple[int, int]:
        """Save normalized valid fire detections into Firestore using detection_key as doc ID.

        Deduplication rule:
        If a document with detection_key already exists, it is skipped and counted
        under skipped_existing_records to prevent duplicate data across runs.

        Args:
            run_id: ID of the executing ETL run.
            valid_records: List of validated detection dictionaries.
            batch_size: Number of writes per Firestore commit batch (max 500 allowed by Firestore).

        Returns:
            Tuple[int, int]: (inserted_records_count, skipped_existing_count)
        """
        if not valid_records:
            return 0, 0

        inserted_count = 0
        skipped_count = 0
        collection_ref = self.db.collection(self.COLLECTION_DETECTIONS)

        # Batch lookup all keys to check existence efficiently
        doc_refs = [collection_ref.document(str(r["detection_key"])) for r in valid_records]
        existing_keys = set()

        for i in range(0, len(doc_refs), batch_size):
            chunk_refs = doc_refs[i : i + batch_size]
            for snapshot in self.db.get_all(chunk_refs):
                if snapshot.exists:
                    existing_keys.add(snapshot.id)

        # Process insertions in batches for high performance
        batch = self.db.batch()
        batch_operations = 0

        for record in valid_records:
            detection_key = str(record["detection_key"])

            # Check if document already exists
            if detection_key in existing_keys:
                skipped_count += 1
                continue

            doc_ref = collection_ref.document(detection_key)

            # Ensure etl_run_id is set
            record_to_save = dict(record)
            record_to_save["etl_run_id"] = run_id

            batch.set(doc_ref, record_to_save)
            batch_operations += 1
            inserted_count += 1

            if batch_operations >= batch_size:
                batch.commit()
                batch = self.db.batch()
                batch_operations = 0

        if batch_operations > 0:
            batch.commit()

        logger.info(
            "Firestore fire_detections persistence complete: %d inserted, %d skipped duplicates",
            inserted_count,
            skipped_count,
        )
        return inserted_count, skipped_count

    def save_rejected_records(
        self,
        run_id: str,
        rejected_records: List[Dict[str, Any]],
        batch_size: int = 400,
    ) -> int:
        """Save rejected records into the rejected_records collection for auditing.

        Args:
            run_id: ID of the executing ETL run.
            rejected_records: List of rejected dictionaries with rejection reasons.
            batch_size: Number of writes per Firestore commit batch.

        Returns:
            Total number of rejected records saved.
        """
        if not rejected_records:
            return 0

        collection_ref = self.db.collection(self.COLLECTION_REJECTED)
        batch = self.db.batch()
        batch_operations = 0
        saved_count = 0

        for item in rejected_records:
            doc_ref = collection_ref.document()  # auto-generated unique ID
            doc_data = {
                "etl_run_id": run_id,
                "source_row_number": item.get("source_row_number", 0),
                "raw_record": item.get("raw_record", {}),
                "rejection_reason": item.get("rejection_reason", "Unknown reason"),
                "rejected_at": item.get("rejected_at") or datetime.now(timezone.utc).isoformat(),
            }
            batch.set(doc_ref, doc_data)
            batch_operations += 1
            saved_count += 1

            if batch_operations >= batch_size:
                batch.commit()
                batch = self.db.batch()
                batch_operations = 0

        if batch_operations > 0:
            batch.commit()

        logger.info("Saved %d rejected records to Firestore collection '%s'", saved_count, self.COLLECTION_REJECTED)
        return saved_count
