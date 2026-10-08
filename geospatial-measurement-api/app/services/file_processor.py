"""Read KML and Shapefile ZIP uploads into processable feature records."""

import logging
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry

from app.models.schemas import FeatureResponse, FileStatus
from app.services.measurement import dataset_crs_string, measure_geometry

logger = logging.getLogger(__name__)


class FileProcessingError(Exception):
    """Raised when upload validation or parsing fails."""


def _validate_extension(filename: str, allowed: frozenset[str]) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in allowed:
        raise FileProcessingError(
            f"Unsupported file extension '{ext}'. Allowed: {', '.join(sorted(allowed))}"
        )
    return ext


def _safe_extract_zip(zip_path: Path, dest_dir: Path) -> None:
    """Extract ZIP members, rejecting path traversal."""
    dest_resolved = dest_dir.resolve()
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            if member.is_dir():
                continue
            target = (dest_dir / member.filename).resolve()
            if not str(target).startswith(str(dest_resolved)):
                raise FileProcessingError("ZIP archive contains unsafe paths")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, open(target, "wb") as out:
                out.write(src.read())


def _find_shapefile(directory: Path) -> Path:
    shp_files = list(directory.rglob("*.shp"))
    if not shp_files:
        raise FileProcessingError("ZIP does not contain a Shapefile (.shp)")
    if len(shp_files) > 1:
        logger.warning("Multiple .shp files found; using %s", shp_files[0])
    return shp_files[0]


def _load_geodataframe(path: Path, driver: str | None = None) -> gpd.GeoDataFrame:
    try:
        if driver:
            gdf = gpd.read_file(path, driver=driver)
        else:
            gdf = gpd.read_file(path)
    except Exception as exc:
        logger.exception("Failed to read geospatial file")
        raise FileProcessingError(f"Could not read geospatial file: {exc}") from exc

    if gdf is None or len(gdf) == 0:
        raise FileProcessingError("Geospatial file contains no features")

    if gdf.crs is None:
        logger.warning("No CRS in file; assuming EPSG:4326 for coordinates")
        gdf = gdf.set_crs("EPSG:4326", allow_override=True)

    return gdf


def _sanitize_value(value: Any) -> Any:
    """Convert pandas/numpy values to JSON-serializable Python types."""
    if value is None:
        return None
    if isinstance(value, (pd.Timestamp, pd.Timedelta)):
        return None if pd.isna(value) else value.isoformat()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            value = value.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(value, float):
        if value != value:
            return None
        if value.is_integer():
            return int(value)
        return value
    if isinstance(value, (list, tuple)):
        return [_sanitize_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _sanitize_value(v) for k, v in value.items()}
    return value


def _properties_from_row(row: Any) -> dict[str, Any]:
    props: dict[str, Any] = {}
    for key, value in row.items():
        if key == "geometry":
            continue
        props[str(key)] = _sanitize_value(value)
    return props


def _geometry_to_geojson(geom: BaseGeometry | None) -> dict[str, Any] | None:
    if geom is None or geom.is_empty:
        return None
    geo = mapping(geom)
    return _sanitize_value(geo)


def gdf_to_features(gdf: gpd.GeoDataFrame) -> list[FeatureResponse]:
    """Convert GeoDataFrame rows to API feature responses."""
    crs_str = dataset_crs_string(gdf.crs)
    features: list[FeatureResponse] = []

    for feature_id, (_, row) in enumerate(gdf.iterrows()):
        geom = row.geometry
        gtype = geom.geom_type if geom is not None and not geom.is_empty else "Unknown"
        measurement, m_status, m_error = measure_geometry(geom, gdf.crs, gtype)

        features.append(
            FeatureResponse(
                id=feature_id,
                geometry_type=gtype,
                geometry=_geometry_to_geojson(geom),
                crs=crs_str,
                properties=_properties_from_row(row),
                measurement=measurement,
                measurement_status=m_status,
                measurement_error=m_error,
            )
        )

    return features


def process_uploaded_file(
    content: bytes,
    original_filename: str,
    allowed_extensions: frozenset[str],
) -> tuple[gpd.GeoDataFrame, list[FeatureResponse]]:
    """
    Validate and parse upload bytes.

    Returns GeoDataFrame and computed feature list.
    """
    ext = _validate_extension(original_filename, allowed_extensions)

    with tempfile.TemporaryDirectory(prefix="geo_upload_") as tmp:
        tmp_path = Path(tmp)
        safe_name = Path(original_filename).name
        upload_path = tmp_path / safe_name
        upload_path.write_bytes(content)

        if ext == ".kml":
            gdf = _load_geodataframe(upload_path, driver="KML")
        elif ext == ".zip":
            extract_dir = tmp_path / "extracted"
            extract_dir.mkdir()
            try:
                _safe_extract_zip(upload_path, extract_dir)
            except zipfile.BadZipFile as exc:
                raise FileProcessingError("Invalid ZIP archive") from exc
            shp_path = _find_shapefile(extract_dir)
            gdf = _load_geodataframe(shp_path)
        else:
            raise FileProcessingError(f"Unsupported extension: {ext}")

        features = gdf_to_features(gdf)
        return gdf, features
