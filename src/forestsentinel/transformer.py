"""Transformation and cleaning module for ForestSentinel.

Cleans and standardizes raw NASA FIRMS detections, normalizes coordinates,
timestamps, instrument metrics, removes exact duplicates, and generates
deterministic detection keys.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


class FirmsTransformer:
    """Transforms raw active-fire / thermal-anomaly records into standardized candidates."""

    def __init__(self) -> None:
        pass

    @staticmethod
    def _standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
        """Standardize column names to lowercase snake_case."""
        clean_df = df.copy()
        clean_df.columns = [
            str(col).strip().lower().replace(" ", "_").replace("-", "_") for col in clean_df.columns
        ]
        return clean_df

    @staticmethod
    def _parse_acq_datetime(date_val: Any, time_val: Any) -> Tuple[datetime, str, str]:
        """Parse acq_date and acq_time into a timezone-aware UTC datetime.

        Handles time values like '930', 930, '0930', 0, '1425' by zero-padding to 4 digits.
        """
        if pd.isna(date_val) or pd.isna(time_val):
            raise ValueError(f"Missing date or time value: date={date_val}, time={time_val}")

        date_str = str(date_val).strip()
        # Time may come as int (e.g. 930 or 0) or float or str
        try:
            time_int = int(float(str(time_val).strip()))
            time_str = f"{time_int:04d}"
        except Exception:
            time_str = str(time_val).strip().zfill(4)

        if len(time_str) != 4 or not time_str.isdigit():
            raise ValueError(f"Cannot format acquisition time '{time_val}' into HHMM")

        hours = int(time_str[:2])
        minutes = int(time_str[2:])

        if not (0 <= hours <= 23 and 0 <= minutes <= 59):
            raise ValueError(f"Time values out of valid 24h range: HH={hours}, MM={minutes} from '{time_val}'")

        # Parse date part (common formats: YYYY-MM-DD or YYYY/MM/DD)
        date_str_clean = date_str.replace("/", "-")
        dt_base = datetime.strptime(date_str_clean, "%Y-%m-%d")
        dt_full = dt_base.replace(hour=hours, minute=minutes, second=0, microsecond=0, tzinfo=timezone.utc)

        return dt_full, dt_base.strftime("%Y-%m-%d"), time_str

    @staticmethod
    def _normalize_confidence(val: Any) -> Tuple[str | None, float | None]:
        """Normalize confidence value without guessing false categories.

        Returns:
            Tuple[textual_confidence, numeric_confidence]
        """
        if pd.isna(val) or val is None or str(val).strip() == "":
            return None, None

        val_str = str(val).strip().lower()
        if val_str in {"low", "nominal", "high"}:
            return val_str, None

        # Check if numeric (e.g. MODIS 0-100%)
        try:
            num = float(val_str)
            return f"numeric_{int(num)}" if num.is_integer() else f"numeric_{num}", num
        except ValueError:
            # Preserve string representation rather than inventing a category
            return val_str, None

    @staticmethod
    def _normalize_daynight(val: Any) -> str | None:
        """Normalize daynight indicator to uppercase 'D' or 'N'."""
        if pd.isna(val) or val is None:
            return None
        s = str(val).strip().upper()
        return s if s in {"D", "N"} else None

    @staticmethod
    def _generate_detection_key(
        lat: float,
        lon: float,
        dt_iso: str,
        satellite: str,
        instrument: str,
        frp: float | None,
    ) -> str:
        """Generate a deterministic SHA-256 hash identifier for an active-fire detection.

        Uses stable rounded coordinates (5 decimal places, ~1.1 meter resolution),
        acquisition datetime, satellite, instrument, and FRP.
        """
        lat_rounded = f"{round(lat, 5):.5f}"
        lon_rounded = f"{round(lon, 5):.5f}"
        frp_str = f"{round(frp, 2):.2f}" if frp is not None and not math.isnan(frp) else "none"
        sat_clean = (satellite or "unknown").strip().lower()
        inst_clean = (instrument or "unknown").strip().lower()

        composite_string = f"{lat_rounded}|{lon_rounded}|{dt_iso}|{sat_clean}|{inst_clean}|{frp_str}"
        return hashlib.sha256(composite_string.encode("utf-8")).hexdigest()

    def transform(
        self, df: pd.DataFrame
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, int]]:
        """Clean and transform raw DataFrame of active-fire detections.

        Args:
            df: Raw DataFrame downloaded from NASA FIRMS.

        Returns:
            Tuple containing:
                1. List of candidate dictionaries ready for Pydantic validation.
                2. List of rejected record dictionaries with rejection reasons.
                3. Statistics dictionary.
        """
        total_raw_rows = len(df)
        if total_raw_rows == 0:
            return [], [], {
                "total_raw_rows": 0,
                "exact_duplicates_removed": 0,
                "cleaning_rejections": 0,
                "valid_candidates": 0,
            }

        # 1. Standardize columns
        clean_df = self._standardize_columns(df)

        # 2. Preserve original source row number (1-indexed based on CSV rows)
        clean_df["_source_row_number"] = range(1, total_raw_rows + 1)

        # 3. Check and remove exact duplicate source rows (excluding row number)
        data_columns = [col for col in clean_df.columns if col != "_source_row_number"]
        initial_count = len(clean_df)
        clean_df = clean_df.drop_duplicates(subset=data_columns, keep="first")
        exact_duplicates_removed = initial_count - len(clean_df)

        valid_candidates: List[Dict[str, Any]] = []
        cleaning_rejections: List[Dict[str, Any]] = []

        # 4. Row-by-row defensive cleaning
        for _, row in clean_df.iterrows():
            row_num = int(row["_source_row_number"])
            raw_record = {k: (None if pd.isna(v) else v) for k, v in row.items() if k != "_source_row_number"}

            # Validate Latitude
            try:
                lat_raw = row.get("latitude")
                if pd.isna(lat_raw):
                    raise ValueError("Latitude is missing")
                lat = float(lat_raw)
                if not (-90.0 <= lat <= 90.0):
                    raise ValueError(f"Latitude {lat} out of bounds [-90, 90]")
            except Exception as exc:
                cleaning_rejections.append({
                    "source_row_number": row_num,
                    "raw_record": raw_record,
                    "rejection_reason": f"Cleaning error: {exc}",
                })
                continue

            # Validate Longitude
            try:
                lon_raw = row.get("longitude")
                if pd.isna(lon_raw):
                    raise ValueError("Longitude is missing")
                lon = float(lon_raw)
                if not (-180.0 <= lon <= 180.0):
                    raise ValueError(f"Longitude {lon} out of bounds [-180, 180]")
            except Exception as exc:
                cleaning_rejections.append({
                    "source_row_number": row_num,
                    "raw_record": raw_record,
                    "rejection_reason": f"Cleaning error: {exc}",
                })
                continue

            # Parse Acquisition DateTime
            try:
                acq_dt, acq_date_str, acq_time_str = self._parse_acq_datetime(
                    row.get("acq_date"), row.get("acq_time")
                )
            except Exception as exc:
                cleaning_rejections.append({
                    "source_row_number": row_num,
                    "raw_record": raw_record,
                    "rejection_reason": f"Cleaning error: {exc}",
                })
                continue

            # Convert numeric fields defensively
            def to_optional_float(field_name: str) -> float | None:
                val = row.get(field_name)
                if pd.isna(val) or val is None:
                    return None
                try:
                    f = float(val)
                    return None if math.isnan(f) else f
                except (ValueError, TypeError):
                    return None

            frp = to_optional_float("frp")
            bright_ti4 = to_optional_float("bright_ti4")
            bright_ti5 = to_optional_float("bright_ti5")

            confidence_text, _ = self._normalize_confidence(row.get("confidence"))
            daynight = self._normalize_daynight(row.get("daynight"))
            satellite = str(row.get("satellite")).strip() if not pd.isna(row.get("satellite")) else None
            instrument = str(row.get("instrument")).strip() if not pd.isna(row.get("instrument")) else None

            # Generate unique deterministic detection key
            detection_key = self._generate_detection_key(
                lat=lat,
                lon=lon,
                dt_iso=acq_dt.isoformat(),
                satellite=satellite or "none",
                instrument=instrument or "none",
                frp=frp,
            )

            candidate = {
                "detection_key": detection_key,
                "latitude": lat,
                "longitude": lon,
                "acq_datetime": acq_dt,
                "acq_date": acq_date_str,
                "acq_time": acq_time_str,
                "satellite": satellite,
                "instrument": instrument,
                "confidence": confidence_text,
                "frp": frp,
                "bright_ti4": bright_ti4,
                "bright_ti5": bright_ti5,
                "daynight": daynight,
                "source_row_number": row_num,
            }
            valid_candidates.append(candidate)

        stats = {
            "total_raw_rows": total_raw_rows,
            "exact_duplicates_removed": exact_duplicates_removed,
            "cleaning_rejections": len(cleaning_rejections),
            "valid_candidates": len(valid_candidates),
        }

        logger.info(
            "Transformation complete. Raw: %d, Duplicates removed: %d, Cleaning rejections: %d, Valid candidates: %d",
            total_raw_rows,
            exact_duplicates_removed,
            len(cleaning_rejections),
            len(valid_candidates),
        )
        return valid_candidates, cleaning_rejections, stats
