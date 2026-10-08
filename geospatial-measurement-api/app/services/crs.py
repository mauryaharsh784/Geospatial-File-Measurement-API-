"""CRS detection and automatic UTM projection for metric measurements."""

import logging
from pyproj import CRS
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

from pyproj import Transformer

logger = logging.getLogger(__name__)

WGS84 = "EPSG:4326"


def crs_to_string(crs: CRS | str | None) -> str | None:
    """Normalize CRS to an EPSG or WKT string for API responses."""
    if crs is None:
        return None
    if isinstance(crs, str):
        try:
            return CRS.from_user_input(crs).to_string()
        except Exception:
            return crs
    try:
        auth = crs.to_authority()
        if auth:
            return f"EPSG:{auth[1]}"
    except Exception:
        pass
    return crs.to_string()


def is_geographic(crs: CRS | str | None) -> bool:
    """Return True if CRS uses angular units (e.g. lat/lon)."""
    if crs is None:
        return True
    try:
        parsed = CRS.from_user_input(crs) if isinstance(crs, str) else crs
        return parsed.is_geographic
    except Exception:
        logger.warning("Could not parse CRS %s; treating as geographic", crs)
        return True


def representative_point(geometry: BaseGeometry) -> BaseGeometry:
    """Centroid for points; representative_point for lines/polygons."""
    if geometry.is_empty:
        return geometry
    if geometry.geom_type == "Point":
        return geometry
    return geometry.representative_point()


def utm_epsg_from_lon_lat(longitude: float, latitude: float) -> int:
    """
    Select WGS84 UTM EPSG code from a lon/lat pair.

    Zone 1–60; northern hemisphere 326xx, southern 327xx.
    """
    zone = int((longitude + 180) / 6) + 1
    zone = max(1, min(60, zone))
    if latitude >= 0:
        return 32600 + zone
    return 32700 + zone


def select_projected_crs(geometry: BaseGeometry, source_crs: CRS | str | None) -> CRS:
    """
    Pick a projected CRS for metric area/length.

    Geographic sources → local UTM from representative point.
    Already projected → keep source CRS.
    Missing/invalid CRS → assume WGS84 then UTM.
    """
    if geometry.is_empty:
        return CRS.from_user_input(WGS84)

    if source_crs is not None and not is_geographic(source_crs):
        return CRS.from_user_input(source_crs)

    ref = representative_point(geometry)
    if ref.is_empty:
        return CRS.from_user_input(WGS84)

    lon, lat = ref.x, ref.y
    epsg = utm_epsg_from_lon_lat(lon, lat)
    return CRS.from_user_input(epsg)


def transform_geometry_to_crs(
    geometry: BaseGeometry,
    source_crs: CRS | str | None,
    target_crs: CRS,
) -> BaseGeometry:
    """Reproject geometry from source_crs to target_crs."""
    if geometry.is_empty:
        return geometry

    src = WGS84 if source_crs is None else CRS.from_user_input(source_crs)
    dst = CRS.from_user_input(target_crs)
    transformer = Transformer.from_crs(src, dst, always_xy=True)

    def _transform(x: float, y: float, z: float | None = None) -> tuple[float, float]:
        xx, yy = transformer.transform(x, y)
        return xx, yy

    return transform(_transform, geometry)


def geometry_for_measurement(
    geometry: BaseGeometry,
    source_crs: CRS | str | None,
) -> tuple[BaseGeometry, str]:
    """
    Return geometry in a CRS suitable for metric measurement.

    Returns (projected_geometry, crs_string).
    """
    target = select_projected_crs(geometry, source_crs)
    if source_crs is not None and not is_geographic(source_crs):
        projected = geometry
    else:
        projected = transform_geometry_to_crs(geometry, source_crs, target)
    return projected, crs_to_string(target) or target.to_string()
