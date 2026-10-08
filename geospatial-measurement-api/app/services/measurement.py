"""Feature-level area and length calculations."""

import logging
from typing import Any

from shapely.geometry import (
    LineString,
    MultiLineString,
    MultiPolygon,
    Point,
    Polygon,
)
from shapely.geometry.base import BaseGeometry

from app.models.schemas import (
    MeasurementResponse,
    MeasurementStatus,
    MeasurementType,
)
from app.services.crs import crs_to_string, geometry_for_measurement

logger = logging.getLogger(__name__)


def _unsupported(
    geometry_type: str,
    reason: str | None = None,
) -> tuple[None, MeasurementStatus, str | None]:
    return None, MeasurementStatus.UNSUPPORTED, reason


def measure_geometry(
    geometry: BaseGeometry | None,
    source_crs: Any,
    geometry_type: str,
) -> tuple[MeasurementResponse | None, MeasurementStatus | None, str | None]:
    """
    Compute measurement for a single geometry.

    MultiPolygon and MultiLineString are supported (sum of parts).
    """
    if geometry is None or geometry.is_empty:
        return None, MeasurementStatus.ERROR, "Empty geometry"

    gtype = geometry_type or geometry.geom_type

    try:
        if gtype == "Point":
            return None, None, None

        if gtype == "LineString":
            if not isinstance(geometry, LineString):
                return _unsupported(gtype, "Expected LineString")
            projected, _ = geometry_for_measurement(geometry, source_crs)
            length_m = float(projected.length)
            return (
                MeasurementResponse(
                    type=MeasurementType.LENGTH,
                    value=round(length_m, 2),
                    unit="m",
                ),
                None,
                None,
            )

        if gtype == "MultiLineString":
            if not isinstance(geometry, MultiLineString):
                return _unsupported(gtype, "Expected MultiLineString")
            total = 0.0
            for part in geometry.geoms:
                projected, _ = geometry_for_measurement(part, source_crs)
                total += projected.length
            return (
                MeasurementResponse(
                    type=MeasurementType.LENGTH,
                    value=round(total, 2),
                    unit="m",
                ),
                None,
                None,
            )

        if gtype == "Polygon":
            if not isinstance(geometry, Polygon):
                return _unsupported(gtype, "Expected Polygon")
            projected, _ = geometry_for_measurement(geometry, source_crs)
            area_m2 = float(projected.area)
            return (
                MeasurementResponse(
                    type=MeasurementType.AREA,
                    value=round(area_m2, 2),
                    unit="m²",
                ),
                None,
                None,
            )

        if gtype == "MultiPolygon":
            if not isinstance(geometry, MultiPolygon):
                return _unsupported(gtype, "Expected MultiPolygon")
            total = 0.0
            for part in geometry.geoms:
                projected, _ = geometry_for_measurement(part, source_crs)
                total += projected.area
            return (
                MeasurementResponse(
                    type=MeasurementType.AREA,
                    value=round(total, 2),
                    unit="m²",
                ),
                None,
                None,
            )

        return _unsupported(gtype, f"Geometry type {gtype} is not supported")

    except Exception as exc:
        logger.exception("Measurement failed for %s", gtype)
        return None, MeasurementStatus.ERROR, str(exc)


def dataset_crs_string(crs: Any) -> str | None:
    """Format dataset CRS for responses."""
    if crs is None:
        return None
    return crs_to_string(crs)
