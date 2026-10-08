"""CRS selection and metric measurement tests."""

from shapely.geometry import GeometryCollection, LineString, Point, Polygon

from app.models.schemas import MeasurementStatus

from app.services.crs import (
    geometry_for_measurement,
    is_geographic,
    select_projected_crs,
    utm_epsg_from_lon_lat,
)
from app.services.measurement import measure_geometry


def test_utm_zone_northern_india() -> None:
    # New Delhi area
    assert utm_epsg_from_lon_lat(77.2, 28.6) == 32643


def test_utm_zone_southern() -> None:
    assert utm_epsg_from_lon_lat(-58.0, -34.0) == 32721


def test_geographic_polygon_uses_metric_area_not_degree_squared() -> None:
    # ~1km x 1km at equator in degrees would be tiny if treated as planar degrees
    poly = Polygon([(0.0, 0.0), (0.0, 0.009), (0.009, 0.009), (0.009, 0.0), (0.0, 0.0)])
    measurement, status, err = measure_geometry(poly, "EPSG:4326", "Polygon")
    assert status is None and err is None
    assert measurement is not None
    assert measurement.unit == "m²"
    # Should be on the order of 1e6 m², not ~8e-5 (degree²)
    assert measurement.value > 100_000


def test_geographic_linestring_length_in_meters() -> None:
    line = LineString([(0.0, 0.0), (0.01, 0.0)])
    measurement, status, _ = measure_geometry(line, "EPSG:4326", "LineString")
    assert measurement is not None
    assert measurement.unit == "m"
    assert measurement.value > 500


def test_already_projected_utm_unchanged_crs_selection() -> None:
    poly = Polygon([(500000, 6000000), (501000, 6000000), (501000, 6001000), (500000, 6001000), (500000, 6000000)])
    crs = "EPSG:32632"
    selected = select_projected_crs(poly, crs)
    assert selected.to_epsg() == 32632
    assert not is_geographic(crs)


def test_unsupported_geometry_collection() -> None:
    gc = GeometryCollection([Point(0, 0), LineString([(0, 0), (1, 1)])])
    measurement, status, _ = measure_geometry(gc, "EPSG:4326", "GeometryCollection")
    assert measurement is None
    assert status == MeasurementStatus.UNSUPPORTED


def test_geometry_for_measurement_returns_projected() -> None:
    poly = Polygon([(77.0, 28.0), (77.01, 28.0), (77.01, 28.01), (77.0, 28.01), (77.0, 28.0)])
    projected, crs_str = geometry_for_measurement(poly, "EPSG:4326")
    assert projected.area > 0
    assert crs_str.startswith("EPSG:")
