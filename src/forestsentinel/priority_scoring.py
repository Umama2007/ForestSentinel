"""Explainable Grid-Cell Hotspot Analysis and Priority Scoring module for ForestSentinel.

Divides the study region into geographic grid cells, computes detection frequency,
recency, intensity (FRP), and confidence metrics, and calculates an explainable
Fire Activity Priority Score (0-100) with dynamic weight redistribution.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class PriorityScorer:
    """Computes geographic grid-cell statistics and explainable priority scores."""

    DEFAULT_GRID_SIZE = 0.25  # Decimal degrees (~27.7 km at equator)

    def __init__(self, grid_size_degrees: float = DEFAULT_GRID_SIZE) -> None:
        """Initialize PriorityScorer with specified grid cell resolution.

        Args:
            grid_size_degrees: Side length of square grid cells in decimal degrees.
        """
        self.grid_size = float(grid_size_degrees)

    def assign_grid_cells(self, df: pd.DataFrame) -> pd.DataFrame:
        """Assign deterministic grid identifiers to each detection record.

        Args:
            df: DataFrame containing latitude and longitude columns.

        Returns:
            DataFrame copy enriched with grid_lat, grid_lon, center_lat, center_lon, and grid_id.
        """
        enriched_df = df.copy()

        def compute_cell_lat(lat: float) -> float:
            return round(math.floor(lat / self.grid_size) * self.grid_size, 4)

        def compute_cell_lon(lon: float) -> float:
            return round(math.floor(lon / self.grid_size) * self.grid_size, 4)

        enriched_df["grid_lat"] = enriched_df["latitude"].apply(compute_cell_lat)
        enriched_df["grid_lon"] = enriched_df["longitude"].apply(compute_cell_lon)
        enriched_df["center_lat"] = (enriched_df["grid_lat"] + self.grid_size / 2.0).round(4)
        enriched_df["center_lon"] = (enriched_df["grid_lon"] + self.grid_size / 2.0).round(4)
        enriched_df["grid_id"] = enriched_df.apply(
            lambda r: f"grid_{r['grid_lat']:.2f}_{r['grid_lon']:.2f}", axis=1
        )

        return enriched_df

    @staticmethod
    def _min_max_scale(series: pd.Series) -> pd.Series:
        """Safely min-max scale a numeric series to [0, 1].

        If all values are identical or max == min, returns 0.5 (or 0.0 if all zero).
        """
        if series.empty:
            return series

        s_min = series.min()
        s_max = series.max()

        if pd.isna(s_min) or pd.isna(s_max) or s_max == s_min:
            return pd.Series(0.0 if s_max == 0.0 else 0.5, index=series.index)

        return (series - s_min) / (s_max - s_min)

    def compute_grid_metrics(self, enriched_df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """Aggregate detection statistics per populated grid cell and calculate priority scores.

        Args:
            enriched_df: DataFrame with grid_id and detection fields.

        Returns:
            Tuple[grid_cells_df, scoring_metadata]
        """
        if enriched_df.empty:
            return pd.DataFrame(), {}

        if "acq_datetime" in enriched_df.columns and not pd.api.types.is_datetime64_any_dtype(enriched_df["acq_datetime"]):
            enriched_df = enriched_df.copy()
            enriched_df["acq_datetime"] = pd.to_datetime(enriched_df["acq_datetime"], utc=True, errors="coerce")

        # Determine dataset latest observation time for recency scoring
        max_dt = enriched_df["acq_datetime"].max() if "acq_datetime" in enriched_df.columns else None

        records: List[Dict[str, Any]] = []

        grouped = enriched_df.groupby("grid_id")

        for grid_id, group in grouped:
            detection_count = len(group)
            grid_lat = group["grid_lat"].iloc[0]
            grid_lon = group["grid_lon"].iloc[0]
            center_lat = group["center_lat"].iloc[0]
            center_lon = group["center_lon"].iloc[0]

            if "detection_date" in group.columns:
                unique_dates = group["detection_date"].nunique()
            elif "acq_date" in group.columns:
                unique_dates = group["acq_date"].nunique()
            elif "acq_datetime" in group.columns and not group["acq_datetime"].isna().all():
                unique_dates = pd.to_datetime(group["acq_datetime"]).dt.date.nunique()
            else:
                unique_dates = 1

            # Fire intensity metrics
            frp_series = group["frp"].dropna() if "frp" in group.columns else pd.Series(dtype=float)
            mean_frp = float(frp_series.mean()) if not frp_series.empty else None
            max_frp = float(frp_series.max()) if not frp_series.empty else None

            # Confidence factor
            if "confidence" in group.columns:
                conf_str = group["confidence"].astype(str).str.lower()
                high_conf_count = int(conf_str.isin(["high", "nominal", "h", "n"]).sum())
            else:
                high_conf_count = 0

            # Recent activity: detections occurring in the final 48 hours or latest date
            if max_dt is not None and not group["acq_datetime"].isna().all():
                group_valid_dts = group["acq_datetime"].dropna()
                latest_dt = group_valid_dts.max()
                time_diff_hours = (max_dt - group_valid_dts).dt.total_seconds() / 3600.0
                recent_count = int((time_diff_hours <= 48.0).sum())
                latest_dt_str = latest_dt.isoformat()
            else:
                latest_dt_str = None
                recent_count = 0

            records.append({
                "grid_id": grid_id,
                "grid_lat": grid_lat,
                "grid_lon": grid_lon,
                "center_lat": center_lat,
                "center_lon": center_lon,
                "detection_count": detection_count,
                "unique_detection_dates": unique_dates,
                "mean_frp": mean_frp,
                "max_frp": max_frp,
                "high_confidence_count": high_conf_count,
                "recent_detection_count": recent_count,
                "latest_detection_datetime": latest_dt_str,
            })

        grid_df = pd.DataFrame(records)

        # Explainable Priority Scoring & Weight Redistribution
        base_weights = {
            "frequency": 0.45,
            "recency": 0.25,
            "frp": 0.20,
            "confidence": 0.10,
        }

        # Check availability of FRP and Confidence across all grid cells
        has_frp = grid_df["mean_frp"].notna().sum() > 0
        has_confidence = grid_df["high_confidence_count"].sum() > 0

        active_weights: Dict[str, float] = {}
        redistribution_notes: List[str] = []

        available_weight_sum = (
            base_weights["frequency"]
            + base_weights["recency"]
            + (base_weights["frp"] if has_frp else 0.0)
            + (base_weights["confidence"] if has_confidence else 0.0)
        )

        for comp, base_w in base_weights.items():
            if comp == "frp" and not has_frp:
                redistribution_notes.append(
                    "FRP data was unavailable; 20% weight was redistributed proportionally across frequency, recency, and confidence."
                )
                continue
            if comp == "confidence" and not has_confidence:
                redistribution_notes.append(
                    "Confidence data was unavailable; 10% weight was redistributed proportionally across available features."
                )
                continue
            active_weights[comp] = base_w / available_weight_sum

        # Calculate normalized component values [0, 1]
        norm_freq = self._min_max_scale(grid_df["detection_count"].astype(float))
        norm_recency = self._min_max_scale(grid_df["recent_detection_count"].astype(float))
        norm_frp = self._min_max_scale(grid_df["mean_frp"].fillna(0.0)) if has_frp else pd.Series(0.0, index=grid_df.index)
        norm_conf = self._min_max_scale(grid_df["high_confidence_count"].astype(float)) if has_confidence else pd.Series(0.0, index=grid_df.index)

        # Composite score calculation (0 to 100)
        raw_score = (
            active_weights.get("frequency", 0.0) * norm_freq
            + active_weights.get("recency", 0.0) * norm_recency
            + active_weights.get("frp", 0.0) * norm_frp
            + active_weights.get("confidence", 0.0) * norm_conf
        ) * 100.0

        grid_df["priority_score"] = raw_score.clip(lower=0.0, upper=100.0).round(2)

        # Assign priority labels
        def assign_label(score: float) -> str:
            if score >= 70.0:
                return "High Priority"
            elif score >= 35.0:
                return "Medium Priority"
            else:
                return "Low Priority"

        grid_df["priority_label"] = grid_df["priority_score"].apply(assign_label)

        # Generate human-readable score explanations
        explanations: List[str] = []
        for _, row in grid_df.iterrows():
            lbl = row["priority_label"]
            score = row["priority_score"]
            cnt = int(row["detection_count"])
            rec = int(row["recent_detection_count"])
            frp_val = f"{row['mean_frp']:.1f} MW" if pd.notna(row["mean_frp"]) else "N/A"

            if lbl == "High Priority":
                exp = (
                    f"High Priority (Score: {score}): Elevated fire activity with {cnt} total detections, "
                    f"{rec} recent observations (last 48h), and average FRP of {frp_val}."
                )
            elif lbl == "Medium Priority":
                exp = (
                    f"Medium Priority (Score: {score}): Moderate fire activity with {cnt} detections "
                    f"and {rec} recent observations."
                )
            else:
                exp = (
                    f"Low Priority (Score: {score}): Lower relative detection volume ({cnt} detections) "
                    f"and limited recent activity."
                )
            explanations.append(exp)

        grid_df["score_explanation"] = explanations

        # Sort grid cells descending by priority score
        grid_df = grid_df.sort_values(by="priority_score", ascending=False).reset_index(drop=True)
        grid_df["rank"] = range(1, len(grid_df) + 1)

        metadata = {
            "grid_size_degrees": self.grid_size,
            "total_populated_cells": len(grid_df),
            "high_priority_count": int((grid_df["priority_label"] == "High Priority").sum()),
            "medium_priority_count": int((grid_df["priority_label"] == "Medium Priority").sum()),
            "low_priority_count": int((grid_df["priority_label"] == "Low Priority").sum()),
            "active_weights": {k: round(v, 4) for k, v in active_weights.items()},
            "redistribution_notes": redistribution_notes,
        }

        logger.info(
            "Priority scoring complete for %d grid cells: %d High, %d Medium, %d Low",
            len(grid_df),
            metadata["high_priority_count"],
            metadata["medium_priority_count"],
            metadata["low_priority_count"],
        )
        return grid_df, metadata
