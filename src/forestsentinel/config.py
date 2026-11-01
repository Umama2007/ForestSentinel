"""Configuration module for ForestSentinel ETL pipeline.

Loads environment variables, validates them strictly, creates necessary directories,
and exposes a typed immutable configuration object.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    """Typed configuration container for the ForestSentinel pipeline."""

    nasa_firms_map_key: str
    firms_source: str
    amazon_bbox: str
    bbox_coords: tuple[float, float, float, float]  # (west, south, east, north)
    day_range: int
    supabase_url: str
    supabase_service_role_key: str
    log_level: str
    base_dir: Path
    raw_data_dir: Path
    reports_dir: Path
    logs_dir: Path
    secrets_dir: Path
    grid_size_degrees: float = 0.25
    iucn_api_token: Optional[str] = None
    iucn_api_base_url: str = "https://api.iucnredlist.org"
    gbif_max_records_per_grid: int = 300
    gbif_request_timeout_seconds: int = 30

    @property
    def database_project(self) -> str:
        """Supabase project reference (the subdomain of SUPABASE_URL), shown in reports."""
        return self.supabase_url.split("//", 1)[-1].split(".", 1)[0]

    def redacted_repr(self) -> str:
        """Return a string representation with secrets masked for safe logging."""
        supabase_masked = (
            self.supabase_service_role_key[:10] + "..."
            if len(self.supabase_service_role_key) > 14
            else "***"
        )
        key_masked = (
            self.nasa_firms_map_key[:4] + "..." + self.nasa_firms_map_key[-4:]
            if len(self.nasa_firms_map_key) > 8
            else "***"
        )
        iucn_masked = (
            (self.iucn_api_token[:4] + "..." + self.iucn_api_token[-4:])
            if self.iucn_api_token and len(self.iucn_api_token) > 8
            else ("***" if self.iucn_api_token else "Not Configured")
        )
        return (
            f"Config(\n"
            f"  firms_source={self.firms_source},\n"
            f"  amazon_bbox={self.amazon_bbox} (west={self.bbox_coords[0]}, south={self.bbox_coords[1]}, "
            f"east={self.bbox_coords[2]}, north={self.bbox_coords[3]}),\n"
            f"  day_range={self.day_range},\n"
            f"  grid_size_degrees={self.grid_size_degrees},\n"
            f"  supabase_url={self.supabase_url},\n"
            f"  supabase_service_role_key={supabase_masked},\n"
            f"  nasa_firms_map_key={key_masked},\n"
            f"  iucn_api_token={iucn_masked},\n"
            f"  iucn_api_base_url={self.iucn_api_base_url},\n"
            f"  gbif_max_records_per_grid={self.gbif_max_records_per_grid},\n"
            f"  gbif_request_timeout_seconds={self.gbif_request_timeout_seconds},\n"
            f"  log_level={self.log_level}\n"
            f")"
        )


def _validate_map_key(map_key: Optional[str]) -> str:
    """Validate that the NASA FIRMS map key is provided and not a placeholder."""
    if not map_key or not map_key.strip():
        raise ValueError(
            "Missing NASA_FIRMS_MAP_KEY in environment or .env file.\n"
            "Please obtain a free Map Key at https://firms.modaps.eosdis.nasa.gov/api/map_key\n"
            "and configure it in your .env file."
        )

    cleaned = map_key.strip()
    placeholder_values = {
        "replace_with_your_real_map_key",
        "your_map_key_here",
        "changeme",
        "sample_key",
    }
    if cleaned.lower() in placeholder_values:
        raise ValueError(
            f"NASA_FIRMS_MAP_KEY contains a placeholder value ('{cleaned}').\n"
            "Please replace it in your .env file with your actual NASA FIRMS Map Key."
        )
    return cleaned


def _validate_bbox(bbox_str: Optional[str]) -> tuple[str, tuple[float, float, float, float]]:
    """Validate that the bounding box contains 4 valid numeric values (west, south, east, north)."""
    if not bbox_str or not bbox_str.strip():
        raise ValueError("AMAZON_BBOX is missing. Expected format: 'west,south,east,north' (e.g. '-62,-10,-58,-6').")

    parts = [p.strip() for p in bbox_str.split(",")]
    if len(parts) != 4:
        raise ValueError(
            f"AMAZON_BBOX '{bbox_str}' is invalid. Must contain exactly 4 comma-separated values: west,south,east,north."
        )

    try:
        west, south, east, north = (float(p) for p in parts)
    except ValueError as exc:
        raise ValueError(f"AMAZON_BBOX coordinates must all be valid numbers. Got: '{bbox_str}'") from exc

    if not (-180.0 <= west <= 180.0 and -180.0 <= east <= 180.0):
        raise ValueError(f"Longitude values in AMAZON_BBOX must be between -180 and 180. Got west={west}, east={east}")

    if not (-90.0 <= south <= 90.0 and -90.0 <= north <= 90.0):
        raise ValueError(f"Latitude values in AMAZON_BBOX must be between -90 and 90. Got south={south}, north={north}")

    if west >= east:
        raise ValueError(f"Invalid BBOX: west ({west}) must be strictly less than east ({east}).")

    if south >= north:
        raise ValueError(f"Invalid BBOX: south ({south}) must be strictly less than north ({north}).")

    return f"{west},{south},{east},{north}", (west, south, east, north)


def _validate_day_range(day_range_val: Optional[str]) -> int:
    """Validate that DAY_RANGE is an integer between 1 and 30."""
    if not day_range_val or not str(day_range_val).strip():
        return 10  # default safe value

    try:
        days = int(str(day_range_val).strip())
    except ValueError as exc:
        raise ValueError(f"DAY_RANGE must be a positive integer. Got: '{day_range_val}'") from exc

    if not (1 <= days <= 30):
        raise ValueError(f"DAY_RANGE must be between 1 and 30 days for NASA FIRMS Area API. Got: {days}")

    return days


def _validate_grid_size(grid_size_val: Optional[str]) -> float:
    """Validate that GRID_SIZE_DEGREES is a positive float between 0.01 and 2.0."""
    if not grid_size_val or not str(grid_size_val).strip():
        return 0.25

    try:
        val = float(str(grid_size_val).strip())
    except ValueError as exc:
        raise ValueError(f"GRID_SIZE_DEGREES must be a valid number. Got: '{grid_size_val}'") from exc

    if not (0.01 <= val <= 2.0):
        raise ValueError(f"GRID_SIZE_DEGREES must be between 0.01 and 2.0 degrees. Got: {val}")

    return val


def load_config(env_path: Optional[Path | str] = None, base_dir: Optional[Path] = None) -> Config:
    """Load and validate pipeline configuration from environment variables and .env file.

    Args:
        env_path: Optional explicit path to .env file.
        base_dir: Optional base workspace directory (defaults to current working directory).

    Returns:
        Validated immutable Config instance.

    Raises:
        ValueError: If any required setting is missing or invalid.
    """
    if base_dir is None:
        base_dir = Path.cwd().resolve()
    else:
        base_dir = Path(base_dir).resolve()

    if env_path is not None:
        load_dotenv(dotenv_path=env_path)
    else:
        # Check current working directory or base_dir for .env
        env_candidate = base_dir / ".env"
        if env_candidate.is_file():
            load_dotenv(dotenv_path=env_candidate)
        else:
            load_dotenv()

    map_key = _validate_map_key(os.getenv("NASA_FIRMS_MAP_KEY"))
    firms_source = os.getenv("FIRMS_SOURCE", "VIIRS_NOAA21_NRT").strip()
    formatted_bbox, bbox_coords = _validate_bbox(os.getenv("AMAZON_BBOX", "-62,-10,-58,-6"))
    day_range = _validate_day_range(os.getenv("DAY_RANGE", "5"))
    grid_size_degrees = _validate_grid_size(os.getenv("GRID_SIZE_DEGREES", "0.25"))

    # Supabase configuration
    supabase_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    if not supabase_url.startswith("https://"):
        raise ValueError(
            "SUPABASE_URL is missing or invalid.\n"
            "Copy the Project URL (e.g. https://abcdefgh.supabase.co) from Supabase -> "
            "Project Settings -> Data API into your .env file."
        )
    supabase_service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not supabase_service_role_key:
        raise ValueError(
            "SUPABASE_SERVICE_ROLE_KEY is missing.\n"
            "Copy the secret (service_role) key from Supabase -> Project Settings -> API Keys "
            "into your .env file."
        )

    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    valid_log_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if log_level not in valid_log_levels:
        log_level = "INFO"

    # Part 3 Configuration: GBIF and IUCN
    raw_iucn_token = os.getenv("IUCN_API_TOKEN", "").strip()
    placeholder_iucn = {
        "",
        "replace_with_your_iucn_api_token",
        "your_iucn_api_token",
        "your_iucn_token_here",
        "changeme",
        "sample_token",
    }
    iucn_api_token = None if raw_iucn_token.lower() in placeholder_iucn else raw_iucn_token
    iucn_api_base_url = os.getenv("IUCN_API_BASE_URL", "https://api.iucnredlist.org").strip().rstrip("/")

    try:
        gbif_max_records = int(os.getenv("GBIF_MAX_RECORDS_PER_GRID", "300").strip())
        if gbif_max_records <= 0:
            gbif_max_records = 300
    except ValueError:
        gbif_max_records = 300

    try:
        gbif_timeout = int(os.getenv("GBIF_REQUEST_TIMEOUT_SECONDS", "30").strip())
        if gbif_timeout <= 0:
            gbif_timeout = 30
    except ValueError:
        gbif_timeout = 30

    # Define directories and ensure they exist
    raw_data_dir = base_dir / "data" / "raw"
    reports_dir = base_dir / "reports"
    conservation_reports_dir = reports_dir / "conservation"
    logs_dir = base_dir / "logs"
    secrets_dir = base_dir / "secrets"

    for d in (raw_data_dir, reports_dir, conservation_reports_dir, logs_dir, secrets_dir):
        d.mkdir(parents=True, exist_ok=True)

    return Config(
        nasa_firms_map_key=map_key,
        firms_source=firms_source,
        amazon_bbox=formatted_bbox,
        bbox_coords=bbox_coords,
        day_range=day_range,
        supabase_url=supabase_url,
        supabase_service_role_key=supabase_service_role_key,
        log_level=log_level,
        base_dir=base_dir,
        raw_data_dir=raw_data_dir,
        reports_dir=reports_dir,
        logs_dir=logs_dir,
        secrets_dir=secrets_dir,
        grid_size_degrees=grid_size_degrees,
        iucn_api_token=iucn_api_token,
        iucn_api_base_url=iucn_api_base_url,
        gbif_max_records_per_grid=gbif_max_records,
        gbif_request_timeout_seconds=gbif_timeout,
    )
