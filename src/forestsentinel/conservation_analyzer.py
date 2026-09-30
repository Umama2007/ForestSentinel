"""Conservation Analyzer module for ForestSentinel.

Coordinates species occurrence extraction from GBIF, species-level deduplication,
IUCN Red List status enrichment, and explainable conservation exposure scoring
for selected Amazon fire-priority grid cells.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd

from forestsentinel.gbif_client import GBIFClient
from forestsentinel.iucn_client import IUCNClient
from forestsentinel.conservation_scoring import ConservationScorer

logger = logging.getLogger(__name__)


class ConservationAnalyzer:
    """Performs privacy-safe biodiversity aggregation and conservation exposure analysis."""

    def __init__(
        self,
        gbif_client: GBIFClient,
        iucn_client: IUCNClient,
    ) -> None:
        """Initialize ConservationAnalyzer with GBIF and IUCN clients.

        Args:
            gbif_client: Client for querying GBIF occurrence data.
            iucn_client: Client for enriching with verified IUCN Red List categories.
        """
        self.gbif_client = gbif_client
        self.iucn_client = iucn_client

    def filter_priority_cells(
        self,
        grid_df: pd.DataFrame,
        allowed_priorities: Tuple[str, ...] = ("High Priority", "Medium Priority"),
    ) -> pd.DataFrame:
        """Filter Part 2 grid cells to only selected priority zones (High and Medium).

        Args:
            grid_df: DataFrame of scored grid cells from Part 2.
            allowed_priorities: Priority labels to select.

        Returns:
            Filtered DataFrame of high/medium priority cells.
        """
        if grid_df.empty or "priority_label" not in grid_df.columns:
            return pd.DataFrame()

        filtered = grid_df[grid_df["priority_label"].isin(allowed_priorities)].copy()
        logger.info(
            "Selected %d/%d grid cells matching priorities %s for biodiversity analysis.",
            len(filtered), len(grid_df), allowed_priorities
        )
        return filtered

    def deduplicate_occurrences(
        self,
        occurrences_df: pd.DataFrame,
        grid_cells_df: pd.DataFrame,
    ) -> List[Dict[str, Any]]:
        """Deduplicate raw occurrences per grid cell into privacy-safe species summaries.

        Groups records by (grid_id, taxon_key) or fallback (grid_id, normalized scientific_name).
        Extracts occurrence counts, min/max observation years, and taxonomy.

        Args:
            occurrences_df: In-memory DataFrame of normalized animal occurrences from GBIF.
            grid_cells_df: Scored grid cells DataFrame containing fire priority metadata.

        Returns:
            List of species-grid summary dictionaries.
        """
        if occurrences_df.empty:
            return []

        # Create quick lookup map for grid cell fire metadata
        grid_lookup: Dict[str, Dict[str, Any]] = {}
        for _, r in grid_cells_df.iterrows():
            gid = str(r["grid_id"])
            grid_lookup[gid] = {
                "grid_priority_score": float(r.get("priority_score", 0.0)),
                "grid_priority_label": str(r.get("priority_label", "Unknown")),
            }

        # Deduplication grouping key: use taxon_key if present, else normalized scientific name
        summaries: List[Dict[str, Any]] = []

        # Group by grid_id first
        for grid_id, cell_group in occurrences_df.groupby("grid_id"):
            cell_fire_info = grid_lookup.get(str(grid_id), {
                "grid_priority_score": 0.0,
                "grid_priority_label": "Unknown",
            })

            # Sub-group by taxon_key or scientific name
            def make_group_key(row: pd.Series) -> str:
                tk = row.get("taxon_key")
                if pd.notna(tk) and str(tk).strip() and str(tk).isdigit():
                    return f"tk_{int(tk)}"
                name = str(row.get("scientific_name", "")).strip().lower()
                return f"name_{name}"

            cell_group = cell_group.copy()
            cell_group["group_key"] = cell_group.apply(make_group_key, axis=1)

            for _, species_records in cell_group.groupby("group_key"):
                first_rec = species_records.iloc[0]

                # Clean attributes
                sci_name = str(first_rec["scientific_name"]).strip()
                taxon_key_val = first_rec.get("taxon_key")
                taxon_key = int(taxon_key_val) if pd.notna(taxon_key_val) and str(taxon_key_val).isdigit() else None

                # Common name (pick first non-empty)
                common_name = None
                for cn in species_records["common_name"]:
                    if pd.notna(cn) and str(cn).strip():
                        common_name = str(cn).strip()
                        break

                # Count recorded occurrences in this cell
                occurrence_count = len(species_records)

                # Min/max observation years
                years = [int(y) for y in species_records["observation_year"] if pd.notna(y) and 1800 <= y <= 2030]
                min_year = min(years) if years else None
                max_year = max(years) if years else None

                summary_doc = {
                    "grid_id": str(grid_id),
                    "grid_priority_label": cell_fire_info["grid_priority_label"],
                    "grid_priority_score": cell_fire_info["grid_priority_score"],
                    "taxon_key": taxon_key,
                    "scientific_name": sci_name,
                    "common_name": common_name,
                    "kingdom": "Animalia",
                    "phylum": first_rec.get("phylum"),
                    "class": first_rec.get("class"),
                    "order": first_rec.get("order"),
                    "family": first_rec.get("family"),
                    "recorded_occurrence_count": occurrence_count,
                    "observation_year_min": min_year,
                    "observation_year_max": max_year,
                }
                summaries.append(summary_doc)

        logger.info(
            "Deduplicated %d raw occurrences into %d unique species-grid summaries.",
            len(occurrences_df), len(summaries)
        )
        return summaries

    def enrich_with_iucn(
        self,
        species_summaries: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Enrich species summaries with verified conservation categories from IUCN client.

        Args:
            species_summaries: Deduplicated species summaries.

        Returns:
            List of species summaries updated with iucn_category, iucn_assessment_date,
            and iucn_verified fields.
        """
        enriched: List[Dict[str, Any]] = []

        # Unique scientific names across summaries
        unique_taxa: Dict[str, Optional[int]] = {}
        for s in species_summaries:
            name = s["scientific_name"]
            if name not in unique_taxa:
                unique_taxa[name] = s.get("taxon_key")

        # Fetch assessment for each unique species
        assessments_by_name: Dict[str, Dict[str, Any]] = {}
        for name, tk in unique_taxa.items():
            assessment = self.iucn_client.get_species_assessment(scientific_name=name, taxon_key=tk)
            assessments_by_name[name] = assessment

        for s in species_summaries:
            s_copy = dict(s)
            ass = assessments_by_name.get(s_copy["scientific_name"], {
                "iucn_category": None,
                "iucn_assessment_date": None,
                "iucn_verified": False,
                "iucn_source": "unavailable",
            })

            s_copy["iucn_category"] = ass.get("iucn_category")
            s_copy["iucn_assessment_date"] = ass.get("iucn_assessment_date")
            s_copy["iucn_verified"] = ass.get("iucn_verified", False)
            enriched.append(s_copy)

        verified_cnt = sum(1 for e in enriched if e.get("iucn_verified"))
        logger.info(
            "IUCN enrichment completed: %d/%d summaries have verified IUCN categories.",
            verified_cnt, len(enriched)
        )
        return enriched

    def run_analysis(
        self,
        grid_df: pd.DataFrame,
        grid_size_degrees: float = 0.25,
    ) -> Dict[str, Any]:
        """Execute end-to-end conservation exposure analysis.

        1. Filter to Medium and High priority fire cells
        2. Query GBIF occurrences
        3. Deduplicate into species-grid summaries
        4. Enrich with IUCN Red List categories
        5. Compute Conservation Exposure Priority Scores
        6. Aggregate cell-level conservation metrics

        Args:
            grid_df: Part 2 grid cells DataFrame.
            grid_size_degrees: Grid resolution.

        Returns:
            Dictionary containing species summaries, cell summaries, threatened species,
            and audit counters.
        """
        # 1. Filter cells
        priority_cells_df = self.filter_priority_cells(grid_df)
        if priority_cells_df.empty:
            logger.warning("No High or Medium priority cells found to analyze.")
            return self._empty_results()

        # 2. Query GBIF
        raw_occurrences_df = self.gbif_client.fetch_occurrences_for_cells(
            cells_df=priority_cells_df,
            grid_size_degrees=grid_size_degrees,
        )

        gbif_records_count = len(raw_occurrences_df)
        gbif_requests_count = len(priority_cells_df)

        if raw_occurrences_df.empty:
            logger.info("No animal occurrences found in GBIF for the queried cells.")
            return self._empty_results(
                priority_cells_count=len(priority_cells_df),
                gbif_requests=gbif_requests_count,
            )

        # 3. Deduplicate
        deduped_summaries = self.deduplicate_occurrences(raw_occurrences_df, priority_cells_df)

        # 4. Enrich with IUCN
        enriched_summaries = self.enrich_with_iucn(deduped_summaries)

        # 5. Score conservation exposure
        scored_summaries = ConservationScorer.score_species_summaries(enriched_summaries)

        # Filter threatened species
        threatened_summaries = [
            s for s in scored_summaries
            if s.get("iucn_verified") and s.get("iucn_category") in ConservationScorer.IUCN_SEVERITY_WEIGHTS
        ]

        # 6. Aggregate by grid cell
        cell_conservation_summaries: List[Dict[str, Any]] = []
        for _, cell in priority_cells_df.iterrows():
            gid = str(cell["grid_id"])
            fire_score = float(cell.get("priority_score", 0.0))
            fire_label = str(cell.get("priority_label", "Unknown"))
            cell_species = [s for s in scored_summaries if s.get("grid_id") == gid]

            cell_agg = ConservationScorer.aggregate_cell_conservation(
                grid_id=gid,
                fire_priority_score=fire_score,
                fire_priority_label=fire_label,
                species_in_cell=cell_species,
            )
            # Add spatial coordinates for mapping (cell center and bounds)
            cell_agg["grid_lat"] = float(cell["grid_lat"])
            cell_agg["grid_lon"] = float(cell["grid_lon"])
            cell_agg["center_lat"] = float(cell["center_lat"])
            cell_agg["center_lon"] = float(cell["center_lon"])
            cell_agg["detection_count"] = int(cell.get("detection_count", 0))
            cell_conservation_summaries.append(cell_agg)

        # Metrics & counters
        unique_species_count = len({s["scientific_name"] for s in scored_summaries})
        unique_threatened_count = len({s["scientific_name"] for s in threatened_summaries})
        verified_iucn_count = len({s["scientific_name"] for s in scored_summaries if s.get("iucn_verified")})

        high_cons_count = sum(1 for s in scored_summaries if s.get("conservation_exposure_label") == ConservationScorer.LABEL_HIGH)
        med_cons_count = sum(1 for s in scored_summaries if s.get("conservation_exposure_label") == ConservationScorer.LABEL_MEDIUM)
        low_cons_count = sum(1 for s in scored_summaries if s.get("conservation_exposure_label") == ConservationScorer.LABEL_LOWER)
        pending_iucn_count = sum(1 for s in scored_summaries if s.get("conservation_exposure_label") == ConservationScorer.LABEL_PENDING_IUCN)
        verified_not_threatened_count = sum(1 for s in scored_summaries if s.get("conservation_exposure_label") == ConservationScorer.LABEL_VERIFIED_NOT_THREATENED)

        threatened_by_cat = {
            "CR": sum(1 for s in threatened_summaries if s.get("iucn_category") == "CR"),
            "EN": sum(1 for s in threatened_summaries if s.get("iucn_category") == "EN"),
            "VU": sum(1 for s in threatened_summaries if s.get("iucn_category") == "VU"),
        }

        return {
            "priority_cells_considered": len(priority_cells_df),
            "gbif_requests_made": gbif_requests_count,
            "gbif_occurrence_records_received": gbif_records_count,
            "unique_animal_species_found": unique_species_count,
            "species_with_verified_iucn_status": verified_iucn_count,
            "threatened_species_found": unique_threatened_count,
            "threatened_by_category": threatened_by_cat,
            "high_conservation_priority_count": high_cons_count,
            "medium_conservation_priority_count": med_cons_count,
            "lower_conservation_priority_count": low_cons_count,
            "pending_iucn_verification_count": pending_iucn_count,
            "verified_not_threatened_count": verified_not_threatened_count,
            "species_grid_summaries": scored_summaries,
            "threatened_species_summaries": threatened_summaries,
            "cell_conservation_summaries": cell_conservation_summaries,
            "priority_cells_df": priority_cells_df,
        }

    def _empty_results(
        self,
        priority_cells_count: int = 0,
        gbif_requests: int = 0,
    ) -> Dict[str, Any]:
        """Return standardized empty results structure."""
        return {
            "priority_cells_considered": priority_cells_count,
            "gbif_requests_made": gbif_requests,
            "gbif_occurrence_records_received": 0,
            "unique_animal_species_found": 0,
            "species_with_verified_iucn_status": 0,
            "threatened_species_found": 0,
            "threatened_by_category": {"CR": 0, "EN": 0, "VU": 0},
            "high_conservation_priority_count": 0,
            "medium_conservation_priority_count": 0,
            "lower_conservation_priority_count": 0,
            "pending_iucn_verification_count": 0,
            "verified_not_threatened_count": 0,
            "species_grid_summaries": [],
            "threatened_species_summaries": [],
            "cell_conservation_summaries": [],
            "priority_cells_df": pd.DataFrame(),
        }
