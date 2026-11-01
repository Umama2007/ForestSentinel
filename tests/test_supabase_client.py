"""Unit tests for the Supabase client module.

Uses a mocked HTTP session to verify request shapes, deduplication logic,
run lifecycle tracking, and credential error handling without a real Supabase project.
"""

from __future__ import annotations

import math
from unittest.mock import MagicMock

import pytest

from forestsentinel.supabase_client import SupabaseAPIError, SupabaseClient, SupabaseConfigError

URL = "https://testproject.supabase.co"
KEY = "sb_secret_test_key_1234567890"


def make_response(status=201, json_data=None):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data if json_data is not None else []
    resp.text = ""
    return resp


@pytest.fixture
def session():
    s = MagicMock()
    s.headers = {}
    s.request.return_value = make_response()
    return s


@pytest.fixture
def client(session):
    return SupabaseClient(URL, KEY, session=session)


def test_missing_key_raises_config_error():
    with pytest.raises(SupabaseConfigError, match="SUPABASE_SERVICE_ROLE_KEY is missing"):
        SupabaseClient(URL, "", session=MagicMock(headers={}))


def test_publishable_key_is_rejected():
    with pytest.raises(SupabaseConfigError, match="publishable key"):
        SupabaseClient(URL, "sb_publishable_abc", session=MagicMock(headers={}))


def test_invalid_url_raises_config_error():
    with pytest.raises(SupabaseConfigError, match="SUPABASE_URL"):
        SupabaseClient("not-a-url", KEY, session=MagicMock(headers={}))


def test_url_with_rest_suffix_is_normalised(session):
    c = SupabaseClient(URL + "/rest/v1/", KEY, session=session)
    assert c.rest_url == URL + "/rest/v1"
    assert c.project_ref == "testproject"
    assert session.headers["apikey"] == KEY
    assert session.headers["Authorization"] == f"Bearer {KEY}"


def test_create_and_update_etl_run(client, session):
    run_id = client.create_etl_run({"api_source": "VIIRS_NOAA21_NRT", "study_bbox": "-62,-10,-58,-6", "day_range": 5})

    assert run_id.startswith("run_")
    method, url = session.request.call_args.args
    assert method == "POST" and url.endswith("/etl_runs")
    payload = session.request.call_args.kwargs["json"]
    assert payload[0]["run_id"] == run_id
    assert payload[0]["status"] == "running"

    client.update_etl_run(run_id, {"status": "completed", "inserted_records": 3, "saved_rejections": 1})
    method, url = session.request.call_args.args
    assert method == "PATCH"
    assert session.request.call_args.kwargs["params"] == {"run_id": f"eq.{run_id}"}
    # Columns the table does not have are dropped instead of failing the write.
    assert session.request.call_args.kwargs["json"] == {"status": "completed", "inserted_records": 3}


def test_save_fire_detections_inserts_new_and_skips_duplicate(client, session):
    """Only rows returned by the ignore-duplicates insert count as inserted."""
    records = [
        {"detection_key": "existing", "latitude": -8.0, "longitude": -60.0, "frp": 10.0},
        {"detection_key": "new", "latitude": -8.1, "longitude": -60.1, "frp": float("nan")},
    ]
    session.request.return_value = make_response(201, [{"detection_key": "new"}])

    inserted, skipped = client.save_fire_detections("run_1", records)

    assert (inserted, skipped) == (1, 1)
    kwargs = session.request.call_args.kwargs
    assert kwargs["params"] == {"on_conflict": "detection_key"}
    assert "resolution=ignore-duplicates" in kwargs["headers"]["Prefer"]
    rows = kwargs["json"]
    assert all(r["etl_run_id"] == "run_1" for r in rows)
    # NaN is not valid JSON for Postgres; it must be sent as null.
    assert rows[1]["frp"] is None and not any(isinstance(v, float) and math.isnan(v) for v in rows[1].values())


def test_save_rejected_records(client, session):
    rejected = [
        {"source_row_number": 5, "raw_record": {"latitude": "bad"}, "rejection_reason": "Invalid latitude"},
        {"source_row_number": 9, "raw_record": {}, "rejection_reason": "Missing acq_time"},
    ]

    saved = client.save_rejected_records("run_1", rejected)

    assert saved == 2
    method, url = session.request.call_args.args
    assert method == "POST" and url.endswith("/rejected_records")
    rows = session.request.call_args.kwargs["json"]
    assert rows[0]["etl_run_id"] == "run_1"
    assert rows[1]["rejection_reason"] == "Missing acq_time"


def test_select_reads_all_pages(client, session):
    client.PAGE_SIZE = 2
    session.request.side_effect = [
        make_response(200, [{"id": 1}, {"id": 2}]),
        make_response(200, [{"id": 3}]),
    ]

    rows = client.select("fire_detections")

    assert [r["id"] for r in rows] == [1, 2, 3]
    assert session.request.call_args_list[1].kwargs["headers"]["Range"] == "2-3"


def test_api_error_is_raised(client, session):
    session.request.return_value = make_response(400)
    with pytest.raises(SupabaseAPIError):
        client.update("etl_runs", {"run_id": "x"}, {"status": "failed"})
