"""Analysis Reporting module for ForestSentinel.

Generates comprehensive, machine-readable JSON reports and instructor-ready
Markdown audit reports detailing Exploratory Data Analysis, Hotspot Aggregations,
and Explainable Priority-Zone Classifications.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

LIMITATION_STATEMENT = (
    "NASA FIRMS records active-fire detections or thermal anomalies. A detection alone "
    "does not prove a confirmed wildfire. The Fire Activity Priority Score is an analytical "
    "ranking based on stored detections, not a wildfire prediction or official emergency warning."
)


def generate_analysis_report(
    eda_results: Dict[str, Any],
    grid_df: pd.DataFrame,
    grid_metadata: Dict[str, Any],
    artifact_paths: Dict[str, Path],
    reports_dir: Path,
    firebase_project_id: str,
) -> Tuple[Path, Path]:
    """Generate both JSON and Markdown comprehensive analysis reports.

    Args:
        eda_results: Dictionary containing overview, temporal, intensity, sensor findings.
        grid_df: DataFrame of ranked grid cells and priority scores.
        grid_metadata: Metadata regarding active weights and score redistribution.
        artifact_paths: File paths to generated static PNG charts and HTML map.
        reports_dir: Directory where report files will be written.
        firebase_project_id: Firebase project identifier.

    Returns:
        Tuple[json_report_path, md_report_path]
    """
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    json_path = reports_dir / f"analysis_report_{timestamp_str}.json"
    md_path = reports_dir / f"analysis_report_{timestamp_str}.md"

    # Convert grid_df to serializable dictionary list
    top_grid_cells: List[Dict[str, Any]] = []
    for _, row in grid_df.head(15).iterrows():
        top_grid_cells.append({
            "rank": int(row["rank"]),
            "grid_id": str(row["grid_id"]),
            "center_coordinates": f"{row['center_lat']:.4f}, {row['center_lon']:.4f}",
            "detection_count": int(row["detection_count"]),
            "unique_dates": int(row["unique_detection_dates"]),
            "mean_frp": round(float(row["mean_frp"]), 2) if pd.notna(row["mean_frp"]) else None,
            "max_frp": round(float(row["max_frp"]), 2) if pd.notna(row["max_frp"]) else None,
            "recent_count": int(row["recent_detection_count"]),
            "latest_detection_time": str(row["latest_detection_datetime"]),
            "priority_score": float(row["priority_score"]),
            "priority_label": str(row["priority_label"]),
            "score_explanation": str(row["score_explanation"]),
        })

    # Prepare complete payload
    payload: Dict[str, Any] = {
        "title": "ForestSentinel Fire Activity EDA & Priority-Zone Analysis Report",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Part 2: Fire Activity Exploratory Data Analysis & Explainable Priority-Zone Classification",
        "data_source": {
            "platform": "Google Firebase Cloud Firestore",
            "collection": "fire_detections",
            "project_id": firebase_project_id,
        },
        "eda_results": eda_results,
        "grid_metadata": grid_metadata,
        "top_hotspot_cells": top_grid_cells,
        "artifacts": {k: str(v) for k, v in artifact_paths.items()},
        "scientific_limitation_statement": LIMITATION_STATEMENT,
    }

    # 1. Write Machine-Readable JSON Report
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)

    # 2. Write Instructor-Ready Markdown Report
    ov = eda_results.get("overview", {})
    temp = eda_results.get("temporal", {})
    intensity = eda_results.get("intensity", {})
    sensors = eda_results.get("sensors", {})
    bounds = eda_results.get("spatial_bounds", {})
    weights = grid_metadata.get("active_weights", {})
    redist_notes = grid_metadata.get("redistribution_notes", [])

    md_lines: List[str] = [
        "# ForestSentinel: Fire Activity EDA & Priority-Zone Analysis",
        "",
        f"**Report Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
        "**Pipeline Phase:** Part 2 - Exploratory Data Analysis, Hotspots & Explainable Priority Scoring  ",
        f"**Data Source:** Firebase Cloud Firestore (`fire_detections` collection in project `{firebase_project_id}`)  ",
        "",
        "---",
        "",
        "## 1. Executive Summary & Dataset Overview",
        "",
        "This analytical audit examines live active-fire / thermal-anomaly detections ingested during Part 1, "
        "derives temporal and radiative intensity patterns, groups detections into standardized geographic grid cells, "
        "and computes an explainable **Fire Activity Priority Score**.",
        "",
        "| Overview Metric | Value |",
        "| :--- | :--- |",
        f"| **Total Firestore Records Analyzed** | **{ov.get('total_records', 0)}** |",
        f"| **Observation Temporal Window (UTC)** | `{ov.get('earliest_detection_datetime', 'N/A')}` to `{ov.get('latest_detection_datetime', 'N/A')}` |",
        f"| **Unique Observation Dates** | {ov.get('unique_detection_dates_count', 0)} ({', '.join(ov.get('unique_detection_dates', []))}) |",
        f"| **Satellites Represented** | {', '.join(ov.get('satellites', []))} ({ov.get('unique_satellites_count', 0)} total) |",
        f"| **Sensors / Instruments** | {', '.join(ov.get('instruments', []))} ({ov.get('unique_instruments_count', 0)} total) |",
        f"| **Day vs. Night Observations** | Day: **{ov.get('day_detections', 0)}** ({ov.get('day_detections', 0)/max(ov.get('total_records', 1), 1):.1%}) / Night: **{ov.get('night_detections', 0)}** ({ov.get('night_detections', 0)/max(ov.get('total_records', 1), 1):.1%}) |",
        f"| **Records with FRP Telemetry** | {ov.get('records_with_frp_count', 0)} ({ov.get('records_with_frp_percentage', 0)}%) |",
        f"| **Geographic Bounding Box** | Lat: [{bounds.get('min_latitude')}, {bounds.get('max_latitude')}], Lon: [{bounds.get('min_longitude')}, {bounds.get('max_longitude')}] |",
        "",
        "---",
        "",
        "## 2. Temporal Fire Activity Findings",
        "",
        f"- **Activity Trend Classification:** `{temp.get('trend_summary', 'N/A').upper()}`",
        f"- **Trend Description:** {temp.get('trend_explanation', 'N/A')}",
        "",
        "### Daily Detection Counts Table",
        "| Observation Date | Active-Fire Detections | Daily Share (%) |",
        "| :--- | :--- | :--- |",
    ]

    total_records = max(ov.get("total_records", 1), 1)
    daily_dict = temp.get("daily_detections", {})
    for dt, cnt in daily_dict.items():
        md_lines.append(f"| `{dt}` | **{cnt}** | {cnt / total_records:.1%} |")

    md_lines.extend([
        "",
        "---",
        "",
        "## 3. Fire Radiative Power (FRP) & Intensity Analysis",
        "",
        "> **Note on FRP Interpretation:** Fire Radiative Power (expressed in Megawatts, MW) measures the instantaneous rate "
        "of radiant heat energy emitted by the thermal anomaly at the exact second of satellite overpass. It serves as a physical proxy "
        "for combustion intensity, but does not equate directly to final burned surface area.",
        "",
        "### Summary Statistics (FRP in Megawatts)",
        "| Metric | Value (MW) | Metric | Value (MW) |",
        "| :--- | :--- | :--- | :--- |",
        f"| **Mean FRP** | {intensity.get('mean_frp', 'N/A')} MW | **Median FRP** | {intensity.get('median_frp', 'N/A')} MW |",
        f"| **Min FRP** | {intensity.get('min_frp', 'N/A')} MW | **Max FRP** | {intensity.get('max_frp', 'N/A')} MW |",
        f"| **25th Percentile (Q1)** | {intensity.get('q25_frp', 'N/A')} MW | **75th Percentile (Q3)** | {intensity.get('q75_frp', 'N/A')} MW |",
        f"| **Standard Deviation** | {intensity.get('std_frp', 'N/A')} MW | **Sample Size** | {intensity.get('count', 0)} detections |",
        "",
        "### Top 5 Peak-Intensity Thermal Anomalies",
        "| Rank | Observation Time (UTC) | Coordinates | FRP (MW) | Confidence | Sensor |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ])

    for i, top in enumerate(intensity.get("top_10_detections", [])[:5], 1):
        md_lines.append(
            f"| {i} | `{top['acq_datetime']}` | {top['latitude']}, {top['longitude']} | **{top['frp']} MW** | {top['confidence']} | {top['satellite']} |"
        )

    md_lines.extend([
        "",
        "---",
        "",
        "## 4. Confidence & Sensor Distribution",
        "",
        "| Confidence Rating | Observation Count | Percentage |",
        "| :--- | :--- | :--- |",
    ])

    for conf, cnt in sensors.get("confidence_counts", {}).items():
        pct = sensors.get("confidence_percentages", {}).get(conf, 0.0)
        md_lines.append(f"| **{conf.capitalize()}** | {cnt} | {pct:.1f}% |")

    md_lines.extend([
        "",
        "---",
        "",
        "## 5. Hotspot Analysis & Explainable Priority-Zone Classification",
        "",
        "The Amazon pilot study area was tessellated into square geographic cells of **0.25° × 0.25°** "
        "(approximately 27.7 km per side). Every cell aggregates thermal detections and derives an **explainable 0–100 score**.",
        "",
        "### Priority Score Formula & Weights Applied",
        "The composite score evaluates four key dimensions of fire activity:",
        "",
        "$$\\text{Priority Score} = \\left( w_{\\text{freq}} \\cdot \\hat{F} + w_{\\text{rec}} \\cdot \\hat{R} + w_{\\text{frp}} \\cdot \\hat{I} + w_{\\text{conf}} \\cdot \\hat{C} \\right) \\times 100$$",
        "",
        "| Factor | Active Weight | Description |",
        "| :--- | :--- | :--- |",
        f"| **Detection Frequency ($\\hat{{F}}$)** | **{weights.get('frequency', 0.45):.1%}** | Min-max scaled total detection volume |",
        f"| **Recent Activity ($\\hat{{R}}$)** | **{weights.get('recency', 0.25):.1%}** | Detections recorded in the latest 48-hour window |",
        f"| **Mean Intensity / FRP ($\\hat{{I}}$)** | **{weights.get('frp', 0.20):.1%}** | Normalized average Fire Radiative Power (MW) |",
        f"| **Confidence Level ($\\hat{{C}}$)** | **{weights.get('confidence', 0.10):.1%}** | Proportion of high/nominal confidence satellite detections |",
        "",
    ])

    if redist_notes:
        md_lines.append("**Weight Redistribution Notes:**")
        for note in redist_notes:
            md_lines.append(f"- _{note}_")
        md_lines.append("")

    md_lines.extend([
        "### Priority Thresholds",
        "- **High Priority** (Score $\\ge 70.0$): Persistent, high-volume, or severe thermal clusters requiring immediate attention.",
        "- **Medium Priority** (Score $35.0 - 69.9$): Moderate activity or emergent clusters.",
        "- **Low Priority** (Score $< 35.0$): Low detection density or isolated thermal anomalies.",
        "",
        f"**Summary Distribution:** **{grid_metadata.get('high_priority_count', 0)} High Priority**, "
        f"**{grid_metadata.get('medium_priority_count', 0)} Medium Priority**, "
        f"**{grid_metadata.get('low_priority_count', 0)} Low Priority** "
        f"across **{grid_metadata.get('total_populated_cells', 0)} populated grid cells**.",
        "",
        "### Top Ranked Hotspot Grid Cells",
        "| Rank | Grid ID | Center Coordinates | Detections | Recent (48h) | Mean FRP | Priority Score | Priority Label |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ])

    for cell in top_grid_cells:
        frp_disp = f"{cell['mean_frp']:.1f} MW" if cell["mean_frp"] is not None else "N/A"
        md_lines.append(
            f"| {cell['rank']} | `{cell['grid_id']}` | {cell['center_coordinates']} | **{cell['detection_count']}** | {cell['recent_count']} | {frp_disp} | **{cell['priority_score']:.1f}** | `{cell['priority_label']}` |"
        )

    md_lines.extend([
        "",
        "---",
        "",
        "## 6. Generated Visual Artifacts",
        "",
        "All visual assets were rendered using the official ForestSentinel styling guidelines and are saved locally:",
        "",
        "| Artifact Name | Type | Relative Path |",
        "| :--- | :--- | :--- |",
        f"| **Interactive Folium Map** | HTML Map | `{artifact_paths.get('fire_activity_map', 'N/A')}` |",
        f"| **Daily Fire Activity** | Line Chart (PNG) | `{artifact_paths.get('daily_fire_activity', 'N/A')}` |",
        f"| **Confidence Distribution** | Bar Chart (PNG) | `{artifact_paths.get('confidence_distribution', 'N/A')}` |",
        f"| **FRP Distribution** | Histogram (PNG) | `{artifact_paths.get('frp_distribution', 'N/A')}` |",
        f"| **Day vs. Night Distribution** | Donut Chart (PNG) | `{artifact_paths.get('day_night_distribution', 'N/A')}` |",
        f"| **Satellite Sensor Distribution** | Horizontal Bar (PNG) | `{artifact_paths.get('satellite_sensor_distribution', 'N/A')}` |",
        f"| **Hotspot Priority Distribution** | Dual Bar Chart (PNG) | `{artifact_paths.get('hotspot_priority_distribution', 'N/A')}` |",
        "",
        "---",
        "",
        "## 7. Data Quality & Limitations Notice",
        "",
    ])

    notes = eda_results.get("data_quality_notes", [])
    if notes:
        md_lines.append("### Data Quality Notes:")
        for note in notes:
            md_lines.append(f"- {note}")
        md_lines.append("")

    md_lines.extend([
        "> **CRITICAL SCIENTIFIC & OPERATIONAL LIMITATIONS:**  ",
        f"> {LIMITATION_STATEMENT}",
        "",
        "> A thermal anomaly indicates a pixel with significant temperature contrast compared to its ambient background. "
        "> Detections can stem from agricultural burns, industrial flaring, hot ground features, or atmospheric reflection. "
        "> Prioritization scores represent relative statistical activity inside the current Firestore dataset window and "
        "> must not be cited as predictive wildfire occurrence forecasts.",
        "",
    ])

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    logger.info("Generated Part 2 analysis reports:\n  JSON: %s\n  Markdown: %s", json_path, md_path)
    return json_path, md_path
