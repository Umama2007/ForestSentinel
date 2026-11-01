"""Conservation Reporter module for ForestSentinel.

Generates structured JSON and comprehensive Markdown audit reports for Part 3:
Conservation Exposure Analysis. Enforces strict privacy standards and includes
mandatory ethical and scientific limitations statements.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Mandatory scientific limitations statement required by ethics protocol
MANDATORY_LIMITATIONS_STATEMENT = (
    "GBIF records represent documented biodiversity occurrences and may be incomplete, "
    "historic, unevenly sampled, or not representative of current species presence. "
    "IUCN categories are shown only when verified through the configured IUCN API. "
    "This analysis aggregates wildlife data to grid cells to protect sensitive locations. "
    "It identifies potential conservation exposure associated with recorded fire activity, "
    "not confirmed wildlife harm, current occupancy, or official conservation guidance."
)


def generate_conservation_report(
    analysis_results: Dict[str, Any],
    artifact_paths: Dict[str, Path],
    output_dir: Path,
    database_project: str,
    run_id: str,
    iucn_configured: bool = False,
) -> Tuple[Path, Path]:
    """Generate both JSON and Markdown conservation audit reports.

    Args:
        analysis_results: Dictionary returned by ConservationAnalyzer.run_analysis.
        artifact_paths: Dictionary mapping artifact names to local Path objects.
        output_dir: Timestamped report destination directory.
        database_project: Configured Supabase project reference.
        run_id: Unique analysis run ID.
        iucn_configured: Whether IUCN API token was configured for this run.

    Returns:
        Tuple of (json_report_path, markdown_report_path).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()

    # 1. Prepare JSON report
    json_path = output_dir / "conservation_report.json"

    # Sanitize artifacts paths for JSON serializability
    artifacts_dict = {k: str(v.resolve()) for k, v in artifact_paths.items()}

    json_payload = {
        "metadata": {
            "title": "ForestSentinel Conservation Exposure Analysis Report",
            "scope": "Part 3: Conservation Exposure Analysis",
            "run_id": run_id,
            "generated_at": generated_at,
            "database_project": database_project,
            "iucn_api_configured": iucn_configured,
        },
        "data_sources": [
            "NASA FIRMS thermal-anomaly active-fire detections (via Supabase)",
            "GBIF Occurrence Search API (https://api.gbif.org/v1/occurrence/search)",
            "IUCN Red List API v4 (https://api.iucnredlist.org), where status was verified",
        ],
        "summary_metrics": {
            "priority_cells_considered": analysis_results.get("priority_cells_considered", 0),
            "gbif_requests_made": analysis_results.get("gbif_requests_made", 0),
            "gbif_occurrence_records_received": analysis_results.get("gbif_occurrence_records_received", 0),
            "unique_animal_species_found": analysis_results.get("unique_animal_species_found", 0),
            "species_with_verified_iucn_status": analysis_results.get("species_with_verified_iucn_status", 0),
            "threatened_species_found": analysis_results.get("threatened_species_found", 0),
            "threatened_by_category": analysis_results.get("threatened_by_category", {"CR": 0, "EN": 0, "VU": 0}),
            "high_conservation_priority_count": analysis_results.get("high_conservation_priority_count", 0),
            "medium_conservation_priority_count": analysis_results.get("medium_conservation_priority_count", 0),
            "lower_conservation_priority_count": analysis_results.get("lower_conservation_priority_count", 0),
            "pending_iucn_verification_count": analysis_results.get("pending_iucn_verification_count", 0),
            "verified_not_threatened_count": analysis_results.get("verified_not_threatened_count", 0),
        },
        "cell_conservation_summaries": analysis_results.get("cell_conservation_summaries", []),
        "threatened_species_summaries": analysis_results.get("threatened_species_summaries", []),
        "artifacts": artifacts_dict,
        "limitations_statement": MANDATORY_LIMITATIONS_STATEMENT,
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_payload, f, indent=2)
    logger.info("Generated JSON conservation report at %s", json_path)

    # 2. Prepare Markdown report
    md_path = output_dir / "conservation_report.md"
    md_content = _build_markdown_report(
        json_payload=json_payload,
        artifact_paths=artifact_paths,
        iucn_configured=iucn_configured,
    )

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    logger.info("Generated Markdown conservation report at %s", md_path)

    return json_path, md_path


def _build_markdown_report(
    json_payload: Dict[str, Any],
    artifact_paths: Dict[str, Path],
    iucn_configured: bool,
) -> str:
    """Build formatted GitHub Markdown report."""
    meta = json_payload["metadata"]
    metrics = json_payload["summary_metrics"]
    cells = json_payload["cell_conservation_summaries"]
    threatened = json_payload["threatened_species_summaries"]
    threatened_cats = metrics.get("threatened_by_category", {})

    lines: List[str] = [
        f"# ForestSentinel Conservation Exposure Analysis Report",
        f"",
        f"**Generated:** {meta['generated_at']}  ",
        f"**Run ID:** `{meta['run_id']}`  ",
        f"**Scope:** Part 3 Conservation Exposure Analysis  ",
        f"**Supabase Project:** `{meta['database_project']}`  ",
        f"**IUCN API Enrichment:** {'Configured (Live API v4)' if iucn_configured else 'Not Configured (Pending IUCN Verification)'}  ",
        f"",
        f"---",
        f"",
        f"## 1. Executive Summary & Data Sources",
        f"",
        f"This phase integrates NASA FIRMS active fire hotspots with biodiversity occurrence records from the Global Biodiversity Information Facility (GBIF) and conservation statuses from the IUCN Red List API v4.",
        f"",
        f"### Data Sources",
        f"- **NASA FIRMS**: Active fire detections stored in Supabase collection `fire_detections`.",
        f"- **GBIF Occurrence Search API**: Biodiversity occurrence records retrieved for selected High and Medium fire-activity priority grid cells.",
        f"- **IUCN Red List API v4**: Conservation assessment categories (CR, EN, VU, NT, LC, DD), verified through official API authentication.",
        f"",
        f"### High-Level Metrics",
        f"| Metric | Value |",
        f"|---|---:|",
        f"| Fire-Priority Grid Cells Considered | **{metrics['priority_cells_considered']}** |",
        f"| GBIF API Requests Executed | **{metrics['gbif_requests_made']}** |",
        f"| Raw Animal Occurrences Received | **{metrics['gbif_occurrence_records_received']}** |",
        f"| Unique Animal Species Identified | **{metrics['unique_animal_species_found']}** |",
        f"| Species with Verified IUCN Status | **{metrics['species_with_verified_iucn_status']}** |",
        f"| Verified Threatened Species Found (CR, EN, VU) | **{metrics['threatened_species_found']}** |",
        f"| - Critically Endangered (CR) | {threatened_cats.get('CR', 0)} |",
        f"| - Endangered (EN) | {threatened_cats.get('EN', 0)} |",
        f"| - Vulnerable (VU) | {threatened_cats.get('VU', 0)} |",
        f"| High Conservation Priority Summaries | **{metrics['high_conservation_priority_count']}** |",
        f"| Medium Conservation Priority Summaries | **{metrics['medium_conservation_priority_count']}** |",
        f"| Lower Conservation Priority Summaries | **{metrics['lower_conservation_priority_count']}** |",
        f"| Pending IUCN Verification | **{metrics['pending_iucn_verification_count']}** |",
        f"| Verified Not Threatened | **{metrics['verified_not_threatened_count']}** |",
        f"",
        f"---",
        f"",
        f"## 2. Priority Grid Cells Conservation Summary",
        f"",
        f"Analysis of Medium and High Priority fire activity grid cells tessellated at 0.25° resolution:",
        f"",
        f"| Grid ID | Fire Priority Score | Fire Priority Label | Unique Species Recorded | Verified Threatened Species | Highest IUCN Status | Conservation Exposure Score | Conservation Priority Label |",
        f"|---|---:|---|---:|---:|---|---:|---|",
    ]

    for cell in cells:
        gid = cell.get("grid_id", "Unknown")
        fire_score = f"{cell.get('fire_priority_score', 0.0):.1f}"
        fire_lbl = cell.get("fire_priority_label", "Unknown")
        tot_sp = cell.get("total_species_recorded", 0)
        thr_cnt = cell.get("threatened_species_count", 0)
        hi_cat = cell.get("highest_iucn_category") or "Pending IUCN Verification"
        max_score = cell.get("max_conservation_exposure_score")
        score_str = f"{max_score:.1f}" if max_score is not None else "Pending Verification"
        cons_lbl = cell.get("conservation_priority_label", "Pending IUCN Verification")

        lines.append(
            f"| `{gid}` | {fire_score} | {fire_lbl} | {tot_sp} | {thr_cnt} | {hi_cat} | {score_str} | {cons_lbl} |"
        )

    lines.extend([
        f"",
        f"---",
        f"",
        f"## 3. Verified Threatened Species in Fire-Priority Zones",
        f"",
    ])

    if threatened:
        lines.extend([
            f"| Scientific Name | Common Name | Family | IUCN Category | Verification Status | Grid Cell ID | Conservation Priority Label |",
            f"|---|---|---|---|---|---|---|",
        ])
        for sp in threatened:
            sci = f"*{sp.get('scientific_name', 'Unknown')}*"
            com = sp.get("common_name") or "—"
            fam = sp.get("family") or "—"
            cat = sp.get("iucn_category", "—")
            ver = "Verified (IUCN v4)" if sp.get("iucn_verified") else "Unverified"
            gid = f"`{sp.get('grid_id', 'Unknown')}`"
            lbl = sp.get("conservation_exposure_label", "Pending IUCN Verification")
            lines.append(f"| {sci} | {com} | {fam} | **{cat}** | {ver} | {gid} | {lbl} |")
    else:
        if not iucn_configured:
            lines.append(
                "> No threatened-species classifications are available in this run because IUCN verification has not yet been configured."
            )
        else:
            lines.append(
                "> No animal species with verified CR, EN, or VU category was identified in the queried fire-priority grid cells."
            )

    lines.extend([
        f"",
        f"---",
        f"",
        f"## 4. Privacy Safeguards & Data Governance",
        f"",
        f"- **No Exact Coordinates Saved**: Exact latitudes and longitudes from GBIF occurrence records were strictly excluded from Supabase storage, reporting tables, logs, and map popups.",
        f"- **Aggregation Boundary**: All biodiversity occurrences are aggregated to 0.25° geographic grid cells (~27.7 km at equator).",
        f"- **Database Security**: Database rows in `species_grid_summaries` only store non-sensitive taxonomic summaries and year spans.",
        f"- **No Proof of Harm**: This platform calculates potential conservation exposure indicators and makes no claims regarding actual individual wildlife injury or mortality.",
        f"",
        f"---",
        f"",
        f"## 5. Generated Artifacts",
        f"",
    ])

    for name, path in artifact_paths.items():
        clean_name = name.replace("_", " ").title()
        lines.append(f"- **{clean_name}**: `{path.as_posix()}`")

    lines.extend([
        f"",
        f"---",
        f"",
        f"## 6. Mandatory Limitations Statement",
        f"",
        f"> {MANDATORY_LIMITATIONS_STATEMENT}",
        f"",
    ])

    return "\n".join(lines)
