"""Reporter module for ForestSentinel.

Generates structured JSON and human-readable Markdown ETL quality audit reports
documenting extraction, cleaning, Pydantic validation, and Firestore persistence metrics.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


def generate_etl_report(
    summary_data: Dict[str, Any],
    reports_dir: Path,
) -> Tuple[Path, Path]:
    """Generate both JSON and Markdown ETL quality audit reports.

    Args:
        summary_data: Dictionary containing pipeline metrics and configuration.
        reports_dir: Target directory where reports should be saved.

    Returns:
        Tuple[Path, Path]: (path_to_json_report, path_to_md_report)
    """
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    json_path = reports_dir / f"etl_report_{timestamp_str}.json"
    md_path = reports_dir / f"etl_report_{timestamp_str}.md"

    # 1. Write JSON Report
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2, default=str)

    # 2. Write Markdown Report
    run_id = summary_data.get("run_id", "N/A")
    started_at = summary_data.get("started_at", "N/A")
    finished_at = summary_data.get("finished_at", "N/A")
    status = summary_data.get("status", "N/A")
    api_source = summary_data.get("api_source", "N/A")
    study_bbox = summary_data.get("study_bbox", "N/A")
    day_range = summary_data.get("day_range", "N/A")
    firebase_project = summary_data.get("firebase_project_id", "N/A")

    counts = summary_data.get("counts", {})
    raw_extracted = counts.get("raw_rows_extracted", 0)
    exact_dups = counts.get("exact_duplicates_removed", 0)
    clean_rejections = counts.get("cleaning_rejections", 0)
    pydantic_rejections = counts.get("pydantic_rejections", 0)
    valid_records = counts.get("valid_records", 0)
    inserted_records = counts.get("inserted_records", 0)
    skipped_existing = counts.get("skipped_existing_records", 0)

    rejected_sample: List[Dict[str, Any]] = summary_data.get("rejected_sample", [])

    md_content = f"""# ForestSentinel ETL Quality & Audit Report

**Report Generated:** {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}  
**Pipeline Run ID:** `{run_id}`  
**Status:** **{status.upper()}**

---

## 1. Executive Summary

The **ForestSentinel** pipeline extracts satellite active-fire and thermal-anomaly detections from the **NASA FIRMS API**, cleans and transforms the data using **Pandas**, strictly validates normalized records against **Pydantic v2 schemas**, and persists data into **Google Firebase Cloud Firestore** with deterministic deduplication.

| Pipeline Metric | Value |
| :--- | :--- |
| **NASA API Source** | `{api_source}` |
| **Study Bounding Box (west,south,east,north)** | `{study_bbox}` |
| **Observation Window (Days)** | `{day_range}` |
| **Execution Start (UTC)** | `{started_at}` |
| **Execution Finish (UTC)** | `{finished_at}` |
| **Firebase Project** | `{firebase_project}` |

---

## 2. Pipeline Execution Funnel & Record Accounting

The accounting below tracks every extracted row through deduplication, sanitization, schema validation, and persistence:

```text
[NASA FIRMS API]
      │
      ▼  {raw_extracted} Raw Detections Extracted
[Deduplication]
      ├── {exact_dups} Exact Duplicate Rows Removed
      │
      ▼  {raw_extracted - exact_dups} Unique Extracted Rows
[Data Cleaning & Normalization]
      ├── {clean_rejections} Cleaning Rejections (invalid coords, dates, or formats)
      │
      ▼  {valid_records + pydantic_rejections} Cleaned Candidates
[Pydantic v2 Schema Validation]
      ├── {pydantic_rejections} Pydantic Rejections (schema/range violations)
      │
      ▼  {valid_records} Validated Records
[Firebase Cloud Firestore Storage]
      ├── {inserted_records} New Detections Inserted
      └── {skipped_existing} Skipped Existing Records (Identical Detection Keys)
```

### Quantitative Metrics Table

| Stage | Metric Name | Record Count | % of Raw Total |
| :--- | :--- | :--- | :--- |
| **Extract** | Raw Rows Extracted | **{raw_extracted}** | 100.0% |
| **Transform** | Exact Duplicates Removed | **{exact_dups}** | {f"{(exact_dups/raw_extracted*100):.1f}%" if raw_extracted else "0.0%"} |
| **Transform** | Cleaning Rejections | **{clean_rejections}** | {f"{(clean_rejections/raw_extracted*100):.1f}%" if raw_extracted else "0.0%"} |
| **Validate** | Pydantic Schema Rejections | **{pydantic_rejections}** | {f"{(pydantic_rejections/raw_extracted*100):.1f}%" if raw_extracted else "0.0%"} |
| **Validate** | Valid Records Produced | **{valid_records}** | {f"{(valid_records/raw_extracted*100):.1f}%" if raw_extracted else "0.0%"} |
| **Load** | Inserted into Firestore | **{inserted_records}** | {f"{(inserted_records/raw_extracted*100):.1f}%" if raw_extracted else "0.0%"} |
| **Load** | Skipped Existing (Deduplicated) | **{skipped_existing}** | {f"{(skipped_existing/raw_extracted*100):.1f}%" if raw_extracted else "0.0%"} |

---

## 3. Database Persistence Architecture

Data is stored in **Google Firebase Cloud Firestore** using the following collections:

1. **`fire_detections`**:
   - Stores normalized, validated active-fire records.
   - **Document ID**: `detection_key` (Deterministic SHA-256 hash computed from latitude, longitude, UTC observation datetime, satellite, instrument, and Fire Radiative Power).
   - This prevents duplicate records across overlapping or repeated ETL runs.
2. **`rejected_records`**:
   - Stores unvalidated/corrupted records with original row number, raw payload, and exact failure reason.
   - Provides an immutable audit trail for data quality monitoring.
3. **`etl_runs`**:
   - Stores pipeline execution metadata, execution durations, run status, and record count statistics.

---

## 4. Sample Rejection Audit Log

"""
    if rejected_sample:
        md_content += "The following is an illustrative sample of rejected records and their reasons:\n\n"
        for i, item in enumerate(rejected_sample[:5], 1):
            row_no = item.get("source_row_number", "Unknown")
            reason = item.get("rejection_reason", "No reason provided")
            md_content += f"- **Sample {i} (Source Row #{row_no}):** `{reason}`\n"
    else:
        md_content += "_No records were rejected during this pipeline run. Data quality was 100%._\n"

    md_content += """

---

## 5. Scientific & Operational Data Limitations

> **IMPORTANT SCIENTIFIC LIMITATION NOTICE:**  
> NASA FIRMS records **active-fire detections** or **thermal anomalies** based on satellite infrared radiometer measurements (e.g. VIIRS, MODIS). A thermal anomaly indicates a pixel with significant temperature contrast compared to its ambient background. **A detection is not by itself proof of a confirmed wildfire.** Thermal anomalies can be caused by prescribed agricultural burns, industrial flares, hot rock surfaces, or sensor artifacts. Confirmation of wildfire activity requires multi-sensor fusion, ground observation, or specialized environmental cross-referencing (planned for later project phases).
"""

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    logger.info("Generated ETL audit reports:\n  JSON: %s\n  Markdown: %s", json_path, md_path)
    return json_path, md_path
