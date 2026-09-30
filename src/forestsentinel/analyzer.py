"""Data preparation and Exploratory Data Analysis (EDA) module for ForestSentinel.

Performs robust temporal, fire-intensity, sensor-confidence, and spatial analyses
on validated active-fire and thermal-anomaly detections.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class FireActivityAnalyzer:
    """Performs Exploratory Data Analysis on validated active-fire detection records."""

    def __init__(self, df: pd.DataFrame) -> None:
        """Initialize analyzer with a validated DataFrame and prepare analysis columns.

        Args:
            df: Raw detection DataFrame loaded from Firestore.
        """
        self.raw_df = df.copy()
        self.df, self.data_quality_notes = self._prepare_data(self.raw_df)

    @staticmethod
    def _prepare_data(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
        """Clean, cast, and derive analytical temporal columns.

        Returns:
            Tuple[prepared_df, data_quality_notes]
        """
        clean_df = df.copy()
        notes: List[str] = []

        # 1. Parse acq_datetime to UTC
        if "acq_datetime" in clean_df.columns:
            clean_df["acq_datetime"] = pd.to_datetime(clean_df["acq_datetime"], utc=True, errors="coerce")
            invalid_dt_count = clean_df["acq_datetime"].isna().sum()
            if invalid_dt_count > 0:
                notes.append(f"{invalid_dt_count} records had invalid or unparseable acq_datetime values.")

        # 2. Derive temporal dimensions
        clean_df["detection_date"] = clean_df["acq_datetime"].dt.strftime("%Y-%m-%d")
        clean_df["detection_hour"] = clean_df["acq_datetime"].dt.hour
        clean_df["day_of_week"] = clean_df["acq_datetime"].dt.day_name()
        clean_df["month"] = clean_df["acq_datetime"].dt.month
        clean_df["year"] = clean_df["acq_datetime"].dt.year
        clean_df["week"] = clean_df["acq_datetime"].dt.isocalendar().week

        # 3. Handle FRP and numeric metrics
        for col in ["frp", "bright_ti4", "bright_ti5"]:
            if col not in clean_df.columns:
                clean_df[col] = np.nan
            else:
                clean_df[col] = pd.to_numeric(clean_df[col], errors="coerce")

        missing_frp = clean_df["frp"].isna().sum()
        if missing_frp > 0:
            notes.append(
                f"{missing_frp} records ({missing_frp / len(clean_df):.1%}) do not have Fire Radiative Power (FRP) readings."
            )

        # 4. Standardize text categories
        for col in ["confidence", "satellite", "instrument", "daynight"]:
            if col in clean_df.columns:
                clean_df[col] = clean_df[col].astype(str).str.strip()
                clean_df[col] = clean_df[col].replace({"nan": None, "None": None, "": None})

        return clean_df, notes

    def get_dataset_overview(self) -> Dict[str, Any]:
        """Generate comprehensive high-level dataset metrics."""
        total_records = len(self.df)
        if total_records == 0:
            return {"total_records": 0}

        valid_dts = self.df["acq_datetime"].dropna()
        earliest_dt = valid_dts.min().isoformat() if not valid_dts.empty else None
        latest_dt = valid_dts.max().isoformat() if not valid_dts.empty else None

        unique_dates = self.df["detection_date"].dropna().nunique()
        unique_satellites = self.df["satellite"].dropna().unique().tolist()
        unique_instruments = self.df["instrument"].dropna().unique().tolist()

        day_count = int((self.df["daynight"] == "D").sum())
        night_count = int((self.df["daynight"] == "N").sum())

        frp_series = self.df["frp"].dropna()
        frp_present_count = len(frp_series)
        frp_percentage = round((frp_present_count / total_records) * 100, 2) if total_records else 0.0

        confidence_counts = (
            self.df["confidence"].fillna("unknown").value_counts().to_dict()
        )

        return {
            "total_records": total_records,
            "earliest_detection_datetime": earliest_dt,
            "latest_detection_datetime": latest_dt,
            "unique_detection_dates_count": unique_dates,
            "unique_detection_dates": sorted(self.df["detection_date"].dropna().unique().tolist()),
            "unique_satellites_count": len(unique_satellites),
            "satellites": unique_satellites,
            "unique_instruments_count": len(unique_instruments),
            "instruments": unique_instruments,
            "day_detections": day_count,
            "night_detections": night_count,
            "records_with_frp_count": frp_present_count,
            "records_with_frp_percentage": frp_percentage,
            "confidence_counts": confidence_counts,
        }

    def analyze_temporal(self) -> Dict[str, Any]:
        """Analyze daily and hourly fire activity trends."""
        if self.df.empty:
            return {}

        # Detections per day
        daily_counts = (
            self.df.groupby("detection_date").size().sort_index().to_dict()
        )

        # Detections by hour of day (0-23)
        hourly_counts_series = self.df.groupby("detection_hour").size()
        hourly_counts = {int(h): int(hourly_counts_series.get(h, 0)) for h in range(24)}

        # Day vs Night
        day_night_counts = self.df["daynight"].value_counts(dropna=False).to_dict()

        # Trend summary
        dates_sorted = sorted(daily_counts.keys())
        if len(dates_sorted) < 2:
            trend_summary = "insufficient data"
            trend_explanation = "Fewer than two observation dates are available to assess temporal direction."
        else:
            counts = [daily_counts[d] for d in dates_sorted]
            # Simple regression slope / midpoint comparison
            half = len(counts) // 2
            first_half_avg = np.mean(counts[:half])
            second_half_avg = np.mean(counts[half:])
            diff_pct = (second_half_avg - first_half_avg) / (first_half_avg + 1e-6)

            if diff_pct > 0.15:
                trend_summary = "increasing"
                trend_explanation = (
                    f"Average daily detections rose from {first_half_avg:.1f} in the early window "
                    f"to {second_half_avg:.1f} in the latter window (+{diff_pct:.1%})."
                )
            elif diff_pct < -0.15:
                trend_summary = "decreasing"
                trend_explanation = (
                    f"Average daily detections fell from {first_half_avg:.1f} in the early window "
                    f"to {second_half_avg:.1f} in the latter window ({diff_pct:.1%})."
                )
            else:
                trend_summary = "stable"
                trend_explanation = (
                    f"Daily fire activity remained relatively steady between first half ({first_half_avg:.1f}) "
                    f"and second half ({second_half_avg:.1f})."
                )

        return {
            "daily_detections": daily_counts,
            "hourly_detections": hourly_counts,
            "day_night_distribution": day_night_counts,
            "trend_summary": trend_summary,
            "trend_explanation": trend_explanation,
        }

    def analyze_fire_intensity(self) -> Dict[str, Any]:
        """Analyze Fire Radiative Power (FRP) metrics and extremes."""
        if "frp" not in self.df.columns or self.df["frp"].dropna().empty:
            return {
                "frp_available": False,
                "note": "No Fire Radiative Power (FRP) data available in the dataset.",
            }

        frp_series = self.df["frp"].dropna()

        stats = {
            "frp_available": True,
            "count": int(frp_series.count()),
            "min_frp": round(float(frp_series.min()), 2),
            "max_frp": round(float(frp_series.max()), 2),
            "mean_frp": round(float(frp_series.mean()), 2),
            "median_frp": round(float(frp_series.median()), 2),
            "q25_frp": round(float(frp_series.quantile(0.25)), 2),
            "q75_frp": round(float(frp_series.quantile(0.75)), 2),
            "std_frp": round(float(frp_series.std()), 2) if len(frp_series) > 1 else 0.0,
        }

        # Top 10 highest-FRP detections
        top_10_df = (
            self.df.sort_values(by="frp", ascending=False)
            .head(10)[["detection_key", "latitude", "longitude", "acq_datetime", "frp", "confidence", "satellite"]]
            .copy()
        )
        top_10_records: List[Dict[str, Any]] = []
        for _, row in top_10_df.iterrows():
            top_10_records.append({
                "detection_key": str(row["detection_key"]),
                "latitude": round(float(row["latitude"]), 4),
                "longitude": round(float(row["longitude"]), 4),
                "acq_datetime": row["acq_datetime"].isoformat() if pd.notna(row["acq_datetime"]) else None,
                "frp": round(float(row["frp"]), 2) if pd.notna(row["frp"]) else None,
                "confidence": str(row["confidence"]) if pd.notna(row["confidence"]) else "unknown",
                "satellite": str(row["satellite"]) if pd.notna(row["satellite"]) else "unknown",
            })
        stats["top_10_detections"] = top_10_records

        # FRP by detection date
        frp_by_date = (
            self.df.groupby("detection_date")["frp"]
            .agg(mean="mean", median="median", count="count", max="max")
            .round(2)
            .to_dict(orient="index")
        )
        stats["frp_by_date"] = frp_by_date

        # FRP by confidence category
        if "confidence" in self.df.columns and self.df["confidence"].notna().sum() > 0:
            frp_by_conf = (
                self.df.groupby("confidence")["frp"]
                .agg(mean="mean", median="median", count="count")
                .round(2)
                .to_dict(orient="index")
            )
            stats["frp_by_confidence"] = frp_by_conf

        return stats

    def analyze_confidence_and_sensors(self) -> Dict[str, Any]:
        """Analyze sensor breakdown and confidence ratings."""
        total = len(self.df)
        if total == 0:
            return {}

        conf_counts = self.df["confidence"].fillna("unknown").value_counts().to_dict()
        conf_percentages = {k: round((v / total) * 100, 2) for k, v in conf_counts.items()}

        sat_counts = self.df["satellite"].fillna("unknown").value_counts().to_dict()
        inst_counts = self.df["instrument"].fillna("unknown").value_counts().to_dict()

        # Cross tab: satellite x confidence
        sat_conf_crosstab = (
            pd.crosstab(
                self.df["satellite"].fillna("unknown"),
                self.df["confidence"].fillna("unknown"),
            )
            .to_dict(orient="index")
        )

        # Cross tab: daynight x confidence
        daynight_conf_crosstab = (
            pd.crosstab(
                self.df["daynight"].fillna("unknown"),
                self.df["confidence"].fillna("unknown"),
            )
            .to_dict(orient="index")
        )

        return {
            "confidence_counts": conf_counts,
            "confidence_percentages": conf_percentages,
            "satellite_counts": sat_counts,
            "instrument_counts": inst_counts,
            "satellite_confidence": sat_conf_crosstab,
            "daynight_confidence": daynight_conf_crosstab,
        }

    def analyze_spatial_bounds(self) -> Dict[str, Any]:
        """Compute bounding extents and spatial center of the active-fire observations."""
        lat_valid = self.df["latitude"].dropna()
        lon_valid = self.df["longitude"].dropna()

        if lat_valid.empty or lon_valid.empty:
            return {}

        return {
            "min_latitude": round(float(lat_valid.min()), 4),
            "max_latitude": round(float(lat_valid.max()), 4),
            "min_longitude": round(float(lon_valid.min()), 4),
            "max_longitude": round(float(lon_valid.max()), 4),
            "center_latitude": round(float(lat_valid.mean()), 4),
            "center_longitude": round(float(lon_valid.mean()), 4),
        }

    def run_full_eda(self) -> Dict[str, Any]:
        """Execute all exploratory data analysis routines and return combined results."""
        logger.info("Executing comprehensive Exploratory Data Analysis...")
        return {
            "overview": self.get_dataset_overview(),
            "temporal": self.analyze_temporal(),
            "intensity": self.analyze_fire_intensity(),
            "sensors": self.analyze_confidence_and_sensors(),
            "spatial_bounds": self.analyze_spatial_bounds(),
            "data_quality_notes": self.data_quality_notes,
        }
