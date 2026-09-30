"""Conservation Exposure Priority Scoring module for ForestSentinel.

Calculates an explainable Conservation Exposure Priority Score (0-100) combining:
1. Fire Activity Priority Score (45%) from Part 2
2. IUCN Threat Severity (35%): CR=1.00, EN=0.75, VU=0.50
3. Recorded Occurrence Evidence (20%): Normalized GBIF occurrence count in the grid cell

STRICT ETHICAL & SCIENTIFIC ACCURACY:
- Only scores verified CR, EN, and VU categories.
- Unverified or non-threatened species are labeled 'Status Unavailable or Not Threatened'
  and not given an arbitrary or false exposure score.
- Output represents potential conservation-monitoring priority, NOT proof of animal harm.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd

logger = logging.getLogger(__name__)


class ConservationScorer:
    """Computes explainable conservation exposure priority scores and audit labels."""

    # IUCN Threat Severity weights
    IUCN_SEVERITY_WEIGHTS: Dict[str, float] = {
        "CR": 1.00,  # Critically Endangered
        "EN": 0.75,  # Endangered
        "VU": 0.50,  # Vulnerable
    }

    # Component weights
    WEIGHT_FIRE_ACTIVITY = 0.45
    WEIGHT_IUCN_SEVERITY = 0.35
    WEIGHT_OCCURRENCE_EVIDENCE = 0.20

    LABEL_HIGH = "High Conservation Priority"
    LABEL_MEDIUM = "Medium Conservation Priority"
    LABEL_LOWER = "Lower Conservation Priority"
    LABEL_PENDING_IUCN = "Pending IUCN Verification"
    LABEL_VERIFIED_NOT_THREATENED = "Verified Not Threatened"
    LABEL_VERIFIED_THREATENED = "Verified Threatened"

    @classmethod
    def calculate_score(
        cls,
        fire_priority_score: float,
        iucn_category: Optional[str],
        iucn_verified: bool,
        occurrence_count: int,
        max_occurrence_count: int = 1,
    ) -> Tuple[Optional[float], str, str]:
        """Calculate Conservation Exposure Score for a single species-grid occurrence.

        Args:
            fire_priority_score: Part 2 Fire Activity Priority Score for the grid cell (0-100).
            iucn_category: Verified IUCN category (e.g., 'CR', 'EN', 'VU', 'LC', etc.).
            iucn_verified: Whether the IUCN category was verified through official API.
            occurrence_count: Number of recorded GBIF occurrences in the cell.
            max_occurrence_count: Max occurrences observed across species in the dataset (for scaling).

        Returns:
            Tuple of (score, label, explanation):
            - score: Float in [0, 100] or None if unverified/non-threatened
            - label: Human-readable priority label
            - explanation: Clear, transparent justification text
        """
        # Validate IUCN status
        cleaned_cat = str(iucn_category).strip().upper() if iucn_category else None

        if not iucn_verified or not cleaned_cat:
            return (
                None,
                cls.LABEL_PENDING_IUCN,
                "Conservation exposure score not calculated: Pending IUCN Verification."
            )

        if cleaned_cat not in cls.IUCN_SEVERITY_WEIGHTS:
            return (
                None,
                cls.LABEL_VERIFIED_NOT_THREATENED,
                f"Conservation exposure score not calculated: Verified Not Threatened (IUCN Category: {cleaned_cat})."
            )

        # 1. Normalized fire priority [0, 1]
        norm_fire = max(0.0, min(float(fire_priority_score) / 100.0, 1.0))

        # 2. IUCN severity [0, 1]
        severity = cls.IUCN_SEVERITY_WEIGHTS[cleaned_cat]

        # 3. Normalized occurrence evidence [0, 1]
        safe_max_occ = max(1, int(max_occurrence_count))
        safe_occ = max(1, int(occurrence_count))
        # Logarithmic or linear proportion capped at 1.0
        norm_occ = min(1.0, safe_occ / safe_max_occ)

        # Composite score calculation (0 to 100)
        raw_score = (
            (cls.WEIGHT_FIRE_ACTIVITY * norm_fire)
            + (cls.WEIGHT_IUCN_SEVERITY * severity)
            + (cls.WEIGHT_OCCURRENCE_EVIDENCE * norm_occ)
        ) * 100.0

        final_score = round(max(0.0, min(raw_score, 100.0)), 2)

        # Label assignment
        if final_score >= 70.0:
            label = cls.LABEL_HIGH
            explanation = (
                f"{cls.LABEL_HIGH} (Score: {final_score}): Grid cell has elevated fire activity "
                f"(Fire Score: {fire_priority_score:.1f}) and recorded occurrences of a "
                f"{cls._category_name(cleaned_cat)} ({cleaned_cat}) species ({occurrence_count} record(s))."
            )
        elif final_score >= 40.0:
            label = cls.LABEL_MEDIUM
            explanation = (
                f"{cls.LABEL_MEDIUM} (Score: {final_score}): Moderate conservation exposure reflecting "
                f"fire activity score of {fire_priority_score:.1f} and recorded occurrences of a "
                f"{cls._category_name(cleaned_cat)} ({cleaned_cat}) species."
            )
        else:
            label = cls.LABEL_LOWER
            explanation = (
                f"{cls.LABEL_LOWER} (Score: {final_score}): Lower exposure zone (Fire Score: {fire_priority_score:.1f}) "
                f"with recorded occurrences of a {cls._category_name(cleaned_cat)} ({cleaned_cat}) species."
            )

        return final_score, label, explanation

    @classmethod
    def score_species_summaries(
        cls,
        summaries: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Compute conservation exposure scores across a list of species-grid summary dicts.

        Args:
            summaries: List of species-grid summaries containing 'grid_priority_score',
                       'iucn_category', 'iucn_verified', 'recorded_occurrence_count'.

        Returns:
            Updated list with 'conservation_exposure_score', 'conservation_exposure_label',
            and 'exposure_explanation' fields populated.
        """
        if not summaries:
            return []

        # Find maximum occurrence count for safe normalization
        max_occ = max(
            (int(s.get("recorded_occurrence_count", 1)) for s in summaries),
            default=1
        )
        if max_occ <= 0:
            max_occ = 1

        scored_summaries: List[Dict[str, Any]] = []

        for item in summaries:
            s_copy = dict(item)
            fire_score = float(s_copy.get("grid_priority_score", 0.0))
            cat = s_copy.get("iucn_category")
            verified = bool(s_copy.get("iucn_verified", False))
            occ_cnt = int(s_copy.get("recorded_occurrence_count", 1))

            score, label, exp = cls.calculate_score(
                fire_priority_score=fire_score,
                iucn_category=cat,
                iucn_verified=verified,
                occurrence_count=occ_cnt,
                max_occurrence_count=max_occ,
            )

            s_copy["conservation_exposure_score"] = score
            s_copy["conservation_exposure_label"] = label
            s_copy["exposure_explanation"] = exp
            scored_summaries.append(s_copy)

        return scored_summaries

    @classmethod
    def aggregate_cell_conservation(
        cls,
        grid_id: str,
        fire_priority_score: float,
        fire_priority_label: str,
        species_in_cell: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Aggregate threatened species exposure metrics for a single grid cell.

        Args:
            grid_id: Grid cell identifier.
            fire_priority_score: Part 2 fire score.
            fire_priority_label: Part 2 fire label.
            species_in_cell: Scored species summaries located in this cell.

        Returns:
            Dictionary of aggregated grid cell conservation metrics.
        """
        threatened_in_cell = [
            s for s in species_in_cell
            if s.get("iucn_verified") and s.get("iucn_category") in cls.IUCN_SEVERITY_WEIGHTS
        ]

        # Highest IUCN category present
        highest_cat = None
        for cat in ("CR", "EN", "VU"):
            if any(s.get("iucn_category") == cat for s in threatened_in_cell):
                highest_cat = cat
                break

        # Max exposure score in cell
        scores = [s["conservation_exposure_score"] for s in threatened_in_cell if s.get("conservation_exposure_score") is not None]
        max_exposure = max(scores) if scores else None
        avg_exposure = round(sum(scores) / len(scores), 2) if scores else None

        # Overall conservation label for the cell
        if max_exposure is not None:
            if max_exposure >= 70.0:
                cell_cons_label = cls.LABEL_HIGH
            elif max_exposure >= 40.0:
                cell_cons_label = cls.LABEL_MEDIUM
            else:
                cell_cons_label = cls.LABEL_LOWER
        else:
            if any(s.get("conservation_exposure_label") == cls.LABEL_PENDING_IUCN for s in species_in_cell) or not species_in_cell:
                cell_cons_label = cls.LABEL_PENDING_IUCN
            else:
                cell_cons_label = cls.LABEL_VERIFIED_NOT_THREATENED

        return {
            "grid_id": grid_id,
            "fire_priority_score": fire_priority_score,
            "fire_priority_label": fire_priority_label,
            "total_species_recorded": len(species_in_cell),
            "threatened_species_count": len(threatened_in_cell),
            "highest_iucn_category": highest_cat,
            "max_conservation_exposure_score": max_exposure,
            "avg_conservation_exposure_score": avg_exposure,
            "conservation_priority_label": cell_cons_label,
        }

    @staticmethod
    def _category_name(cat_code: str) -> str:
        """Return full category name for display."""
        mapping = {
            "CR": "Critically Endangered",
            "EN": "Endangered",
            "VU": "Vulnerable",
        }
        return mapping.get(cat_code, cat_code)
