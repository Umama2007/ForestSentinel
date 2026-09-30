"""Pydantic v2 schemas for ForestSentinel data validation.

Ensures every active-fire / thermal-anomaly detection record strictly satisfies
data quality standards before being written to persistent storage.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

logger = logging.getLogger(__name__)


class FireDetection(BaseModel):
    """Pydantic v2 model representing a validated active-fire detection."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    detection_key: str = Field(
        ...,
        min_length=1,
        description="Deterministic SHA-256 hash identifying unique detection",
    )
    latitude: float = Field(
        ...,
        ge=-90.0,
        le=90.0,
        description="Latitude in decimal degrees (-90 to +90)",
    )
    longitude: float = Field(
        ...,
        ge=-180.0,
        le=180.0,
        description="Longitude in decimal degrees (-180 to +180)",
    )
    acq_datetime: datetime = Field(
        ...,
        description="UTC timestamp of the satellite observation",
    )
    acq_date: str = Field(
        ...,
        min_length=8,
        description="Observation date string (YYYY-MM-DD)",
    )
    acq_time: str = Field(
        ...,
        min_length=4,
        max_length=4,
        description="Observation time in 4-digit HHMM 24h format",
    )
    satellite: Optional[str] = Field(
        default=None,
        description="Satellite platform (e.g. NOAA-21, Suomi-NPP, Terra, Aqua)",
    )
    instrument: Optional[str] = Field(
        default=None,
        description="Sensor instrument (e.g. VIIRS, MODIS)",
    )
    confidence: Optional[str] = Field(
        default=None,
        description="Normalized confidence indicator (low, nominal, high, or numeric string)",
    )
    frp: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Fire Radiative Power in Megawatts (MW), non-negative",
    )
    bright_ti4: Optional[float] = Field(
        default=None,
        description="Channel 4 brightness temperature in Kelvin",
    )
    bright_ti5: Optional[float] = Field(
        default=None,
        description="Channel 5 brightness temperature in Kelvin",
    )
    daynight: Optional[str] = Field(
        default=None,
        pattern=r"^[DN]$",
        description="Day or Night flag ('D' or 'N')",
    )
    source_row_number: int = Field(
        ...,
        gt=0,
        description="1-indexed row number from the original extracted CSV",
    )
    ingested_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of ETL ingestion",
    )
    etl_run_id: Optional[str] = Field(
        default=None,
        description="Unique identifier of the executing ETL run",
    )

    @field_validator("daynight", mode="before")
    @classmethod
    def clean_daynight(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        s = str(v).strip().upper()
        return s if s in {"D", "N"} else None

    @field_validator("satellite", "instrument", "confidence", mode="before")
    @classmethod
    def clean_strings(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    def to_storage_dict(self) -> Dict[str, Any]:
        """Convert model to a dictionary suitable for Firestore storage (ISO strings for datetimes)."""
        d = self.model_dump()
        d["acq_datetime"] = self.acq_datetime.isoformat()
        d["ingested_at"] = self.ingested_at.isoformat()
        return d


def validate_fire_records(
    candidates: List[Dict[str, Any]],
    etl_run_id: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Validate a list of candidate dictionaries using the Pydantic FireDetection schema.

    Any invalid record is caught and isolated without failing the rest of the batch.

    Args:
        candidates: Cleaned record dictionaries from the transformer.
        etl_run_id: Run identifier to stamp onto records.

    Returns:
        Tuple of (valid_records, pydantic_rejected_records).
    """
    valid_records: List[Dict[str, Any]] = []
    pydantic_rejections: List[Dict[str, Any]] = []

    for item in candidates:
        row_num = item.get("source_row_number", 0)
        item_copy = dict(item)
        item_copy["etl_run_id"] = etl_run_id

        try:
            model = FireDetection.model_validate(item_copy)
            valid_records.append(model.to_storage_dict())
        except ValidationError as val_err:
            # Format readable reason message
            error_details = []
            for err in val_err.errors():
                loc = ".".join(str(p) for p in err["loc"])
                msg = err["msg"]
                error_details.append(f"{loc}: {msg}")
            reason_str = "Pydantic validation failed: " + "; ".join(error_details)

            logger.warning("Record at row %d rejected by Pydantic: %s", row_num, reason_str)
            pydantic_rejections.append({
                "etl_run_id": etl_run_id,
                "source_row_number": row_num,
                "raw_record": item,
                "rejection_reason": reason_str,
                "rejected_at": datetime.now(timezone.utc).isoformat(),
            })

    logger.info(
        "Pydantic validation complete. Candidates: %d -> Valid: %d, Rejected: %d",
        len(candidates),
        len(valid_records),
        len(pydantic_rejections),
    )
    return valid_records, pydantic_rejections
