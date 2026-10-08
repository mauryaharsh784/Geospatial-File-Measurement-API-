"""API request/response schemas."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class FileStatus(str, Enum):
    """Processing lifecycle for an uploaded file."""

    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class MeasurementType(str, Enum):
    """Supported measurement kinds."""

    AREA = "area"
    LENGTH = "length"


class MeasurementStatus(str, Enum):
    """Why a feature has no measurement."""

    UNSUPPORTED = "UNSUPPORTED"
    ERROR = "ERROR"


class MeasurementResponse(BaseModel):
    """Area or length measurement in metric units."""

    type: MeasurementType
    value: float
    unit: str = Field(description="m² for area, m for length")


class FileResponse(BaseModel):
    """Metadata for an uploaded geospatial file."""

    id: str
    filename: str
    feature_count: int
    crs: str | None
    status: FileStatus
    error_message: str | None = None


class FeatureResponse(BaseModel):
    """Single feature with geometry, attributes, and optional measurement."""

    id: int
    geometry_type: str
    geometry: dict[str, Any] | None = None
    crs: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)
    measurement: MeasurementResponse | None = None
    measurement_status: MeasurementStatus | None = None
    measurement_error: str | None = None


class MeasurementsResponse(BaseModel):
    """All feature measurements for a file."""

    file_id: str
    filename: str
    crs: str | None
    features: list[FeatureResponse]


class ErrorResponse(BaseModel):
    """Consistent JSON error body."""

    detail: str
