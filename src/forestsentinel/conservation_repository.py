"""Conservation Repository module for ForestSentinel.

Manages Cloud Firestore storage for Part 3 conservation exposure analysis:
1. conservation_analysis_runs: metadata and audit counters per execution
2. species_grid_summaries: privacy-safe aggregated species occurrence summaries per grid cell
3. conservation_assessments: cached IUCN conservation categories

PRIVACY ENFORCEMENT: Never stores raw GBIF records or individual wildlife coordinates.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from forestsentinel.firebase_client import FirebaseClient

logger = logging.getLogger(__name__)


class ConservationRepository:
    """Cloud Firestore repository for ForestSentinel conservation data."""

    COLLECTION_RUNS = "conservation_analysis_runs"
    COLLECTION_SUMMARIES = "species_grid_summaries"
    COLLECTION_ASSESSMENTS = "conservation_assessments"

    PERMITTED_SUMMARY_FIELDS = {
        "grid_id",
        "grid_priority_label",
        "grid_priority_score",
        "taxon_key",
        "scientific_name",
        "common_name",
        "kingdom",
        "phylum",
        "class",
        "order",
        "family",
        "iucn_category",
        "iucn_assessment_date",
        "iucn_verified",
        "recorded_occurrence_count",
        "observation_year_min",
        "observation_year_max",
        "conservation_exposure_score",
        "conservation_exposure_label",
        "created_at",
        "analysis_run_id",
    }

    FORBIDDEN_FIELDS = {
        "latitude", "longitude", "decimalLatitude", "decimalLongitude",
        "key", "gbifID", "recordedBy", "collector", "raw_gbif", "verbatimLocality"
    }

    def __init__(self, firebase_client: FirebaseClient) -> None:
        """Initialize repository with FirebaseClient instance.

        Args:
            firebase_client: Authenticated FirebaseClient instance.
        """
        self.firebase_client = firebase_client
        self.db = firebase_client.db

    def create_run(self, metadata: Dict[str, Any]) -> str:
        """Create a new conservation analysis run document with status 'running'.

        Args:
            metadata: Run configuration and start parameters.

        Returns:
            Generated run document ID.
        """
        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        run_id = f"conservation_run_{timestamp_str}_{uuid.uuid4().hex[:6]}"

        run_doc = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
            "status": "running",
            "source_fire_analysis_run": metadata.get("source_fire_analysis_run", "live_recomputed"),
            "grid_size_degrees": metadata.get("grid_size_degrees", 0.25),
            "priority_cells_considered": metadata.get("priority_cells_considered", 0),
            "gbif_requests_made": 0,
            "gbif_occurrence_records_received": 0,
            "unique_animal_species_found": 0,
            "species_with_verified_iucn_status": 0,
            "threatened_species_found": 0,
            "aggregated_grid_species_records_saved": 0,
            "error_message": None,
        }

        try:
            self.db.collection(self.COLLECTION_RUNS).document(run_id).set(run_doc)
            logger.info("Created conservation run record '%s' in Firestore.", run_id)
        except Exception as exc:
            logger.error("Failed to create conservation run record: %s", exc)
            raise

        return run_id

    def update_run(self, run_id: str, updates: Dict[str, Any]) -> None:
        """Update fields on an existing conservation analysis run document.

        Args:
            run_id: ID of the run document to update.
            updates: Dictionary of fields to update.
        """
        try:
            self.db.collection(self.COLLECTION_RUNS).document(run_id).update(updates)
            logger.info("Updated conservation run '%s' with status: %s", run_id, updates.get("status"))
        except Exception as exc:
            logger.error("Failed updating conservation run '%s': %s", run_id, exc)
            raise

    def get_cached_assessment(
        self,
        scientific_name: str,
        taxon_key: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Look up a cached IUCN assessment by taxon key or normalized scientific name.

        Args:
            scientific_name: Binomial scientific name.
            taxon_key: Optional GBIF taxon identifier.

        Returns:
            Dictionary of cached assessment or None.
        """
        doc_id = self._make_assessment_doc_id(scientific_name, taxon_key)
        try:
            doc_ref = self.db.collection(self.COLLECTION_ASSESSMENTS).document(doc_id)
            doc_snap = doc_ref.get()
            if doc_snap.exists:
                data = doc_snap.to_dict()
                if data:
                    data["iucn_source"] = "firestore_cache"
                    return data
        except Exception as exc:
            logger.debug("Failed querying cached IUCN assessment '%s': %s", doc_id, exc)

        return None

    def save_cached_assessment(self, assessment: Dict[str, Any]) -> None:
        """Persist a verified IUCN assessment to the cache collection.

        Args:
            assessment: Assessment dictionary containing scientific_name, iucn_category, etc.
        """
        scientific_name = assessment.get("scientific_name", "")
        taxon_key = assessment.get("taxon_key")
        doc_id = self._make_assessment_doc_id(scientific_name, taxon_key)

        cache_doc = {
            "taxon_key": taxon_key,
            "scientific_name": scientific_name,
            "iucn_category": assessment.get("iucn_category"),
            "iucn_assessment_date": assessment.get("iucn_assessment_date"),
            "iucn_verified": assessment.get("iucn_verified", False),
            "iucn_source": assessment.get("iucn_source", "iucn_api_v4"),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            self.db.collection(self.COLLECTION_ASSESSMENTS).document(doc_id).set(cache_doc, merge=True)
            logger.debug("Cached IUCN assessment for '%s' (%s)", scientific_name, doc_id)
        except Exception as exc:
            logger.warning("Failed saving cached IUCN assessment '%s': %s", doc_id, exc)

    def save_species_grid_summaries(
        self,
        run_id: str,
        summaries: List[Dict[str, Any]],
        batch_size: int = 250,
    ) -> int:
        """Save non-sensitive aggregated species summaries to species_grid_summaries.

        Enforces strict privacy validation: explicitly strips any geographic coordinates
        or occurrence-level identifier fields before saving.

        Args:
            run_id: ID of the current analysis run.
            summaries: List of species-grid summary dictionaries.
            batch_size: Maximum batch write size.

        Returns:
            Number of documents successfully committed.
        """
        if not summaries:
            logger.info("No species grid summaries to save.")
            return 0

        saved_count = 0
        batches = [summaries[i:i + batch_size] for i in range(0, len(summaries), batch_size)]

        for chunk_idx, chunk in enumerate(batches, 1):
            batch = self.db.batch()
            for record in chunk:
                # Privacy verification
                sanitized_record = self._sanitize_summary_record(record, run_id)
                doc_id = self._make_summary_doc_id(
                    grid_id=sanitized_record["grid_id"],
                    taxon_key=sanitized_record.get("taxon_key"),
                    scientific_name=sanitized_record.get("scientific_name", "")
                )
                doc_ref = self.db.collection(self.COLLECTION_SUMMARIES).document(doc_id)
                batch.set(doc_ref, sanitized_record)

            try:
                batch.commit()
                saved_count += len(chunk)
                logger.debug(
                    "Committed species grid summary batch %d/%d (%d docs).",
                    chunk_idx, len(batches), len(chunk)
                )
            except Exception as exc:
                logger.error("Failed saving species grid summary batch %d: %s", chunk_idx, exc)
                raise

        logger.info(
            "Successfully saved %d species grid summaries to Firestore collection '%s'.",
            saved_count, self.COLLECTION_SUMMARIES
        )
        return saved_count

    def _sanitize_summary_record(self, raw_summary: Dict[str, Any], run_id: str) -> Dict[str, Any]:
        """Strictly filter fields to ensure only permitted aggregated attributes are stored.

        Raises ValueError if any coordinate or forbidden field is detected.
        """
        # Ensure no forbidden fields slip through
        for forbidden in self.FORBIDDEN_FIELDS:
            if forbidden in raw_summary:
                raise ValueError(
                    f"PRIVACY VIOLATION DETECTED: Field '{forbidden}' must NEVER be stored in "
                    f"Firestore '{self.COLLECTION_SUMMARIES}'!"
                )

        sanitized: Dict[str, Any] = {}
        for k in self.PERMITTED_SUMMARY_FIELDS:
            sanitized[k] = raw_summary.get(k)

        # Force analysis_run_id and created_at
        sanitized["analysis_run_id"] = run_id
        if not sanitized.get("created_at"):
            sanitized["created_at"] = datetime.now(timezone.utc).isoformat()

        return sanitized

    @staticmethod
    def _make_assessment_doc_id(scientific_name: str, taxon_key: Optional[int] = None) -> str:
        """Create deterministic document ID for IUCN assessment cache."""
        if taxon_key is not None:
            return f"taxon_{taxon_key}"
        clean_name = re.sub(r"[^a-zA-Z0-9_]+", "_", scientific_name.strip().lower()).strip("_")
        return f"sci_{clean_name}"

    @staticmethod
    def _make_summary_doc_id(grid_id: str, taxon_key: Optional[int], scientific_name: str) -> str:
        """Create deterministic document ID for species_grid_summaries: grid_id_taxon_key."""
        if taxon_key is not None:
            return f"{grid_id}_{taxon_key}"
        clean_name = re.sub(r"[^a-zA-Z0-9_]+", "_", scientific_name.strip().lower()).strip("_")
        return f"{grid_id}_{clean_name}"
