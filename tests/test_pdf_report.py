"""Tests for the PDF report builders."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from forestsentinel import pdf_report
from forestsentinel.analyzer import FireActivityAnalyzer
from forestsentinel.priority_scoring import PriorityScorer
from forestsentinel.visualizer import Visualizer

ETL = {
    "run_id": "run_test",
    "status": "completed",
    "started_at": "2026-10-03T10:05:35+00:00",
    "duration_seconds": 9.9,
    "api_source": "VIIRS_NOAA21_NRT",
    "study_bbox": "-62,-10,-58,-6",
    "day_range": 5,
    "database_project": "demo",
    "raw_csv_saved_at": "data/raw/firms_test.csv",
    "counts": {
        "raw_rows_extracted": 10, "exact_duplicates_removed": 0, "cleaning_rejections": 1,
        "pydantic_rejections": 0, "valid_records": 9, "inserted_records": 7,
        "skipped_existing_records": 2, "saved_rejections": 1,
    },
    "rejected_sample": [{"reason": "latitude out of range", "latitude": 95}],
}


def _analysis_payload(tmp_path: Path) -> dict:
    """Run the real analyzer, scorer and visualizer on a small sample to get a realistic payload."""
    rows = []
    for i in range(12):
        rows.append({
            "detection_key": f"k{i}", "latitude": -8.1 - (i % 3) * 0.3, "longitude": -60.1 - (i % 4) * 0.3,
            "acq_datetime": f"2026-10-0{1 + i % 3}T{'17' if i % 2 else '05'}:30:00Z",
            "satellite": "N21", "instrument": "VIIRS", "confidence": "nhl"[i % 3],
            "frp": 3.0 + i * (8 if i == 11 else 1), "bright_ti4": 320 + i, "bright_ti5": 290 + i % 4,
            "daynight": "D" if i % 2 else "N",
        })
    analyzer = FireActivityAnalyzer(pd.DataFrame(rows))
    eda = analyzer.run_full_eda()
    scorer = PriorityScorer(grid_size_degrees=0.25)
    enriched = scorer.assign_grid_cells(analyzer.df)
    grid_df, grid_meta = scorer.compute_grid_metrics(enriched)
    Visualizer(output_dir=tmp_path / "charts").render_all(enriched, grid_df, 0.25)
    return {
        "generated_at": "2026-10-03T11:00:00+00:00",
        "eda_results": eda,
        "grid_metadata": grid_meta,
        "top_hotspot_cells": [{
            "rank": int(r["rank"]), "grid_id": r["grid_id"], "detection_count": int(r["detection_count"]),
            "unique_dates": int(r["unique_detection_dates"]), "mean_frp": float(r["mean_frp"]),
            "max_frp": float(r["max_frp"]), "recent_count": int(r["recent_detection_count"]),
            "priority_score": float(r["priority_score"]), "priority_label": r["priority_label"],
        } for _, r in grid_df.iterrows()],
    }


CONSERVATION = {
    "metadata": {"run_id": "cons_test", "generated_at": "2026-10-03T12:00:00+00:00",
                 "database_project": "demo", "iucn_api_configured": False},
    "summary_metrics": {"priority_cells_considered": 1, "gbif_occurrence_records_received": 5,
                        "unique_animal_species_found": 4, "species_with_verified_iucn_status": 0},
    "cell_conservation_summaries": [{
        "grid_id": "grid_-8.25_-60.25", "fire_priority_label": "High Priority", "fire_priority_score": 80.0,
        "detection_count": 6, "total_species_recorded": 4, "conservation_priority_label": "Pending IUCN Verification",
    }],
}


def _is_pdf(path: Path) -> bool:
    return path.is_file() and path.read_bytes()[:5] == b"%PDF-" and path.stat().st_size > 2000


def test_etl_pdf(tmp_path: Path):
    assert _is_pdf(pdf_report.build_etl_pdf(ETL, tmp_path / "etl.pdf"))


def test_analysis_pdf_includes_charts(tmp_path: Path):
    analysis = _analysis_payload(tmp_path)
    with_charts = pdf_report.build_analysis_pdf(analysis, tmp_path / "charts", tmp_path / "a.pdf", etl=ETL)
    without = pdf_report.build_analysis_pdf(analysis, None, tmp_path / "b.pdf")
    assert _is_pdf(with_charts) and _is_pdf(without)
    assert with_charts.stat().st_size > without.stat().st_size  # chart images are embedded


def test_conservation_and_project_pdfs(tmp_path: Path):
    analysis = _analysis_payload(tmp_path)
    assert _is_pdf(pdf_report.build_conservation_pdf(CONSERVATION, None, tmp_path / "c.pdf"))
    assert _is_pdf(pdf_report.build_project_pdf(ETL, analysis, tmp_path / "charts", CONSERVATION, None,
                                                tmp_path / "p.pdf", cons_stale=True))
    # project report still builds before Part 3 has ever run
    assert _is_pdf(pdf_report.build_project_pdf(None, analysis, None, None, None, tmp_path / "p2.pdf"))


def test_try_build_swallows_errors(tmp_path: Path):
    assert pdf_report.try_build(pdf_report.build_etl_pdf, None, tmp_path / "bad.pdf") is None
