"""Unit tests for the Firebase Cloud Firestore client module.

Uses mocking to verify Firestore collection operations, deduplication logic,
run lifecycle tracking, and credential error handling without requiring a real Firebase project.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from forestsentinel.firebase_client import FirebaseClient, FirebaseConfigError


def test_missing_credentials_raises_friendly_error(tmp_path: Path):
    """Verify that a missing service account JSON file raises FirebaseConfigError with instructions."""
    non_existent_path = tmp_path / "does_not_exist.json"

    with pytest.raises(FirebaseConfigError) as exc_info:
        FirebaseClient(service_account_path=non_existent_path, project_id="test-proj")

    assert "Firebase service account file not found" in str(exc_info.value)
    assert "Firebase Console" in str(exc_info.value)


def test_invalid_json_credentials_raises_error(tmp_path: Path):
    """Verify that an invalid or placeholder JSON credentials file raises an error."""
    bad_json_path = tmp_path / "bad_creds.json"
    bad_json_path.write_text("{\"type\": \"other\", \"project_id\": \"test\"}", encoding="utf-8")

    with pytest.raises(FirebaseConfigError) as exc_info:
        FirebaseClient(service_account_path=bad_json_path, project_id="test-proj")

    assert "not a valid Google service account key" in str(exc_info.value)


@pytest.fixture
def mock_firestore():
    """Create a mock Firestore database client."""
    mock_db = MagicMock()
    return mock_db


def test_create_and_update_etl_run(mock_firestore):
    """Test creating and updating an ETL run document in Firestore."""
    client = FirebaseClient(
        service_account_path="dummy.json",
        project_id="test-proj",
        firestore_client=mock_firestore,
    )

    metadata = {
        "api_source": "VIIRS_NOAA21_NRT",
        "study_bbox": "-62,-10,-58,-6",
        "day_range": 10,
    }

    run_id = client.create_etl_run(metadata)

    assert run_id.startswith("run_")
    # Verify set was called on etl_runs collection
    mock_firestore.collection.assert_called_with(FirebaseClient.COLLECTION_RUNS)
    mock_firestore.collection().document(run_id).set.assert_called_once()

    # Test updating run
    client.update_etl_run(run_id, {"status": "completed", "valid_records": 100})
    mock_firestore.collection().document(run_id).update.assert_called_once_with({
        "status": "completed",
        "valid_records": 100,
    })


def test_save_fire_detections_inserts_new_and_skips_duplicate(mock_firestore):
    """Test that existing documents are skipped and new documents are inserted via batch."""
    client = FirebaseClient(
        service_account_path="dummy.json",
        project_id="test-proj",
        firestore_client=mock_firestore,
    )

    # Prepare mock batch
    mock_batch = MagicMock()
    mock_firestore.batch.return_value = mock_batch

    # Prepare 2 records: one exists, one is new
    records = [
        {"detection_key": "existing_key_1", "latitude": -7.1, "longitude": -60.1},
        {"detection_key": "new_key_2", "latitude": -7.2, "longitude": -60.2},
    ]

    # Document mock behavior for get_all
    existing_doc_snapshot = MagicMock()
    existing_doc_snapshot.exists = True
    existing_doc_snapshot.id = "existing_key_1"

    new_doc_snapshot = MagicMock()
    new_doc_snapshot.exists = False
    new_doc_snapshot.id = "new_key_2"

    mock_firestore.get_all.return_value = [existing_doc_snapshot, new_doc_snapshot]

    inserted, skipped = client.save_fire_detections(run_id="run_123", valid_records=records)

    assert inserted == 1
    assert skipped == 1
    # Verify batch.set was called once for the new document
    assert mock_batch.set.call_count == 1
    assert mock_batch.commit.call_count == 1


def test_save_rejected_records(mock_firestore):
    """Test saving rejected audit records into rejected_records collection."""
    client = FirebaseClient(
        service_account_path="dummy.json",
        project_id="test-proj",
        firestore_client=mock_firestore,
    )

    mock_batch = MagicMock()
    mock_firestore.batch.return_value = mock_batch

    rejected_records = [
        {
            "source_row_number": 5,
            "raw_record": {"latitude": 99.0},
            "rejection_reason": "Latitude 99.0 out of bounds",
        },
        {
            "source_row_number": 8,
            "raw_record": {"acq_date": "invalid"},
            "rejection_reason": "Invalid date",
        },
    ]

    saved_count = client.save_rejected_records("run_123", rejected_records)

    assert saved_count == 2
    mock_firestore.collection.assert_called_with(FirebaseClient.COLLECTION_REJECTED)
    assert mock_batch.set.call_count == 2
    assert mock_batch.commit.call_count == 1
