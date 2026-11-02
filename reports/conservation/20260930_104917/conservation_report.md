# ForestSentinel Conservation Exposure Analysis Report

**Generated:** 2026-09-30T10:50:02.743517+00:00  
**Run ID:** `conservation_run_20260930_104921_1dd755`  
**Scope:** Part 3 Conservation Exposure Analysis  
**Firebase Project ID:** `forestsentinel-58520`  
**IUCN API Enrichment:** Not Configured (Status Unavailable)  

---

## 1. Executive Summary & Data Sources

This phase integrates NASA FIRMS active fire hotspots with biodiversity occurrence records from the Global Biodiversity Information Facility (GBIF) and conservation statuses from the IUCN Red List API v4.

### Data Sources
- **NASA FIRMS**: Active fire detections stored in Cloud Firestore collection `fire_detections`.
- **GBIF Occurrence Search API**: Biodiversity occurrence records retrieved for selected High and Medium fire-activity priority grid cells.
- **IUCN Red List API v4**: Conservation assessment categories (CR, EN, VU, NT, LC, DD), verified through official API authentication.

### High-Level Metrics
| Metric | Value |
|---|---:|
| Fire-Priority Grid Cells Considered | **4** |
| GBIF API Requests Executed | **4** |
| Raw Animal Occurrences Received | **31** |
| Unique Animal Species Identified | **23** |
| Species with Verified IUCN Status | **0** |
| Verified Threatened Species Found (CR, EN, VU) | **0** |
| - Critically Endangered (CR) | 0 |
| - Endangered (EN) | 0 |
| - Vulnerable (VU) | 0 |
| High Conservation Priority Summaries | **0** |
| Medium Conservation Priority Summaries | **0** |
| Lower Conservation Priority Summaries | **0** |
| Status Unavailable or Not Threatened | **23** |

---

## 2. Priority Grid Cells Conservation Summary

Analysis of Medium and High Priority fire activity grid cells tessellated at 0.25° resolution:

| Grid ID | Fire Priority Score | Fire Priority Label | Unique Species Recorded | Verified Threatened Species | Highest IUCN Status | Conservation Exposure Score | Conservation Priority Label |
|---|---:|---|---:|---:|---|---:|---|
| `grid_-8.00_-61.25` | 72.2 | High Priority | 13 | 0 | None verified | Pending Verification | Status Unavailable or Not Threatened |
| `grid_-10.00_-60.75` | 57.6 | Medium Priority | 1 | 0 | None verified | Pending Verification | Status Unavailable or Not Threatened |
| `grid_-9.25_-61.00` | 46.2 | Medium Priority | 9 | 0 | None verified | Pending Verification | Status Unavailable or Not Threatened |
| `grid_-9.25_-61.50` | 42.9 | Medium Priority | 0 | 0 | None verified | Pending Verification | Status Unavailable or Not Threatened |

---

## 3. Verified Threatened Species in Fire-Priority Zones

> **Note:** IUCN enrichment was skipped because `IUCN_API_TOKEN` is not configured in `.env`. No species has been classified as threatened in this run. Occurrence data from GBIF has been safely aggregated into species-grid summaries.

---

## 4. Privacy Safeguards & Data Governance

- **No Exact Coordinates Saved**: Exact latitudes and longitudes from GBIF occurrence records were strictly excluded from Firestore storage, reporting tables, logs, and map popups.
- **Aggregation Boundary**: All biodiversity occurrences are aggregated to 0.25° geographic grid cells (~27.7 km at equator).
- **Firestore Security**: Firestore documents in `species_grid_summaries` only store non-sensitive taxonomic summaries and year spans.
- **No Proof of Harm**: This platform calculates potential conservation exposure indicators and makes no claims regarding actual individual wildlife injury or mortality.

---

## 5. Generated Artifacts

- **Threatened Species By Category**: `C:/Users/MC/Desktop/P4AI/reports/conservation/20260930_104917/threatened_species_by_category.png`
- **Species Exposure By Priority Zone**: `C:/Users/MC/Desktop/P4AI/reports/conservation/20260930_104917/species_exposure_by_priority_zone.png`
- **Top Conservation Priority Cells**: `C:/Users/MC/Desktop/P4AI/reports/conservation/20260930_104917/top_conservation_priority_cells.png`
- **Biodiversity Data Quality**: `C:/Users/MC/Desktop/P4AI/reports/conservation/20260930_104917/biodiversity_data_quality.png`
- **Conservation Exposure Map**: `C:/Users/MC/Desktop/P4AI/reports/conservation/20260930_104917/conservation_exposure_map.html`

---

## 6. Mandatory Limitations Statement

> GBIF records represent documented biodiversity occurrences and may be incomplete, historic, unevenly sampled, or not representative of current species presence. IUCN categories are shown only when verified through the configured IUCN API. This analysis aggregates wildlife data to grid cells to protect sensitive locations. It identifies potential conservation exposure associated with recorded fire activity, not confirmed wildlife harm, current occupancy, or official conservation guidance.
