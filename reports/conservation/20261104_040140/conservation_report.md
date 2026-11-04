# ForestSentinel Conservation Exposure Analysis Report

**Generated:** 2026-11-04T04:02:09.021988+00:00  
**Run ID:** `conservation_run_20261104_040142_14433d`  
**Scope:** Part 3 Conservation Exposure Analysis  
**Supabase Project:** `advspndbkxswkloufnbu`  
**IUCN API Enrichment:** Not Configured (Pending IUCN Verification)  

---

## 1. Executive Summary & Data Sources

This phase integrates NASA FIRMS active fire hotspots with biodiversity occurrence records from the Global Biodiversity Information Facility (GBIF) and conservation statuses from the IUCN Red List API v4.

### Data Sources
- **NASA FIRMS**: Active fire detections stored in Supabase collection `fire_detections`.
- **GBIF Occurrence Search API**: Biodiversity occurrence records retrieved for selected High and Medium fire-activity priority grid cells.
- **IUCN Red List API v4**: Conservation assessment categories (CR, EN, VU, NT, LC, DD), verified through official API authentication.

### High-Level Metrics
| Metric | Value |
|---|---:|
| Fire-Priority Grid Cells Considered | **6** |
| GBIF API Requests Executed | **6** |
| Raw Animal Occurrences Received | **540** |
| Unique Animal Species Identified | **315** |
| Species with Verified IUCN Status | **0** |
| Verified Threatened Species Found (CR, EN, VU) | **0** |
| - Critically Endangered (CR) | 0 |
| - Endangered (EN) | 0 |
| - Vulnerable (VU) | 0 |
| High Conservation Priority Summaries | **0** |
| Medium Conservation Priority Summaries | **0** |
| Lower Conservation Priority Summaries | **0** |
| Pending IUCN Verification | **372** |
| Verified Not Threatened | **0** |

---

## 2. Priority Grid Cells Conservation Summary

Analysis of Medium and High Priority fire activity grid cells tessellated at 0.25° resolution:

| Grid ID | Fire Priority Score | Fire Priority Label | Unique Species Recorded | Verified Threatened Species | Highest IUCN Status | Conservation Exposure Score | Conservation Priority Label |
|---|---:|---|---:|---:|---|---:|---|
| `grid_-7.00_-59.50` | 96.4 | High Priority | 28 | 0 | Pending IUCN Verification | Pending Verification | Pending IUCN Verification |
| `grid_-9.25_-59.00` | 93.2 | High Priority | 52 | 0 | Pending IUCN Verification | Pending Verification | Pending IUCN Verification |
| `grid_-8.00_-61.50` | 72.3 | High Priority | 99 | 0 | Pending IUCN Verification | Pending Verification | Pending IUCN Verification |
| `grid_-9.50_-59.50` | 52.4 | Medium Priority | 11 | 0 | Pending IUCN Verification | Pending Verification | Pending IUCN Verification |
| `grid_-8.25_-61.25` | 47.3 | Medium Priority | 50 | 0 | Pending IUCN Verification | Pending Verification | Pending IUCN Verification |
| `grid_-9.25_-60.50` | 43.9 | Medium Priority | 132 | 0 | Pending IUCN Verification | Pending Verification | Pending IUCN Verification |

---

## 3. Verified Threatened Species in Fire-Priority Zones

> No threatened-species classifications are available in this run because IUCN verification has not yet been configured.

---

## 4. Privacy Safeguards & Data Governance

- **No Exact Coordinates Saved**: Exact latitudes and longitudes from GBIF occurrence records were strictly excluded from Supabase storage, reporting tables, logs, and map popups.
- **Aggregation Boundary**: All biodiversity occurrences are aggregated to 0.25° geographic grid cells (~27.7 km at equator).
- **Database Security**: Database rows in `species_grid_summaries` only store non-sensitive taxonomic summaries and year spans.
- **No Proof of Harm**: This platform calculates potential conservation exposure indicators and makes no claims regarding actual individual wildlife injury or mortality.

---

## 5. Generated Artifacts

- **Threatened Species By Category**: `C:/Users/MC/Desktop/Projects/ForestSentinel/reports/conservation/20261104_040140/threatened_species_by_category.png`
- **Species Exposure By Priority Zone**: `C:/Users/MC/Desktop/Projects/ForestSentinel/reports/conservation/20261104_040140/species_exposure_by_priority_zone.png`
- **Top Conservation Priority Cells**: `C:/Users/MC/Desktop/Projects/ForestSentinel/reports/conservation/20261104_040140/top_conservation_priority_cells.png`
- **Biodiversity Data Quality**: `C:/Users/MC/Desktop/Projects/ForestSentinel/reports/conservation/20261104_040140/biodiversity_data_quality.png`
- **Conservation Exposure Map**: `C:/Users/MC/Desktop/Projects/ForestSentinel/reports/conservation/20261104_040140/conservation_exposure_map.html`

---

## 6. Mandatory Limitations Statement

> GBIF records represent documented biodiversity occurrences and may be incomplete, historic, unevenly sampled, or not representative of current species presence. IUCN categories are shown only when verified through the configured IUCN API. This analysis aggregates wildlife data to grid cells to protect sensitive locations. It identifies potential conservation exposure associated with recorded fire activity, not confirmed wildlife harm, current occupancy, or official conservation guidance.
