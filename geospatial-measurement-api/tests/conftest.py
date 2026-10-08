"""Shared pytest fixtures."""

import io
import zipfile
from pathlib import Path

import geopandas as gpd
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Polygon

from app.main import app
from app.repositories.file_repository import file_repository


@pytest.fixture(autouse=True)
def clear_repository() -> None:
    """Isolate tests by clearing the in-memory store."""
    file_repository._store.clear()
    yield
    file_repository._store.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def make_kml_bytes() -> bytes:
    """Minimal valid KML with polygon, line, and point in EPSG:4326."""
    kml = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>area</name>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
              77.0,28.0,0 77.0,28.01,0 77.01,28.01,0 77.01,28.0,0 77.0,28.0,0
            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
    <Placemark>
      <name>line</name>
      <LineString>
        <coordinates>77.0,28.0,0 77.01,28.0,0</coordinates>
      </LineString>
    </Placemark>
    <Placemark>
      <name>point</name>
      <Point>
        <coordinates>77.005,28.005,0</coordinates>
      </Point>
    </Placemark>
  </Document>
</kml>
"""
    return kml.encode("utf-8")


def make_shapefile_zip_bytes() -> bytes:
    """Build an in-memory ZIP containing a valid Shapefile (single geometry type)."""
    polygons = [
        Polygon([(0, 0), (0, 0.01), (0.01, 0.01), (0.01, 0), (0, 0)]),
        Polygon([(0.02, 0), (0.02, 0.01), (0.03, 0.01), (0.03, 0), (0.02, 0)]),
        Polygon([(0, 0.02), (0, 0.03), (0.01, 0.03), (0.01, 0.02), (0, 0.02)]),
    ]
    gdf = gpd.GeoDataFrame(
        {"name": ["a", "b", "c"]},
        geometry=polygons,
        crs="EPSG:4326",
    )

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "layer"
        gdf.to_file(base.with_suffix(".shp"))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
                path = base.with_suffix(ext)
                if path.exists():
                    zf.write(path, arcname=f"data/{path.name}")
        return buf.getvalue()


@pytest.fixture
def kml_bytes() -> bytes:
    return make_kml_bytes()


@pytest.fixture
def shapefile_zip_bytes() -> bytes:
    return make_shapefile_zip_bytes()
