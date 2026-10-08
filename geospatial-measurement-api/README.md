# Geospatial File Measurement API

Production-oriented take-home backend service that accepts **KML** and **Shapefile (ZIP)** uploads, extracts features with GeoPandas, and computes **metric area and length** using automatic CRS projection (UTM) instead of raw WGS84 degrees.

## Overview

This API ingests geospatial vector files, validates and parses them safely, stores metadata in a swappable in-memory repository, and exposes REST endpoints for file metadata and per-feature measurements. Processing is **synchronous** on upload (status `PROCESSING` → `COMPLETED`) but structured so background workers can be added later.

## Features

- Upload `.kml` or `.zip` (Shapefile bundle)
- Extract feature ID, geometry type, GeoJSON geometry, CRS, and attributes
- **Polygon** → area (m²), **LineString** → length (m), **Point** → no measurement
- **MultiPolygon** / **MultiLineString** → summed measurements (documented extension)
- Unsupported types (e.g. `GeometryCollection`) → `measurement: null`, `measurement_status: UNSUPPORTED`
- Geographic CRS (e.g. EPSG:4326) → automatic local **UTM** before measurement
- ZIP path-traversal protection, size limits, temp directory cleanup
- OpenAPI docs at `/docs` and `/redoc`
- Pytest suite with programmatic fixtures (no large binaries in Git)
- Docker image with GDAL/GEOS/PROJ

## Tech Stack

| Component | Role |
|-----------|------|
| **FastAPI** | HTTP API, validation, OpenAPI |
| **Uvicorn** | ASGI server |
| **GeoPandas** | Read KML/Shapefile, CRS-aware GeoDataFrames |
| **Shapely** | Geometry operations |
| **PyProj** | CRS parsing and reprojection |
| **Pyogrio** | Fast I/O backend for GeoPandas |
| **Pydantic v2** | Response schemas |
| **Pytest + HTTPX** | API and unit tests |

## Setup

```bash
cd geospatial-measurement-api
python -m venv .venv
```

**Windows:**

```bash
.venv\Scripts\activate
```

**Linux/macOS:**

```bash
source .venv/bin/activate
```

```bash
pip install -r requirements.txt
```

> **Note:** GeoPandas requires GDAL/GEOS on the host. On Windows, installing from `requirements.txt` often works via wheels; on Linux you may need `libgdal-dev` (see Dockerfile).

## Running

```bash
uvicorn app.main:app --reload
```

- Swagger UI: http://127.0.0.1:8000/docs  
- ReDoc: http://127.0.0.1:8000/redoc  
- Health: http://127.0.0.1:8000/health  

Optional environment variables (prefix `GEO_API_`):

- `GEO_API_MAX_UPLOAD_BYTES` (default 52428800)
- `GEO_API_DEBUG=true`

## API Documentation

### POST `/api/files/`

Upload and process a file immediately.

```bash
curl -X POST "http://127.0.0.1:8000/api/files/" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@survey.kml"
```

**Response (201):**

```json
{
  "id": "abc123def456",
  "filename": "survey.kml",
  "feature_count": 120,
  "crs": "EPSG:4326",
  "status": "COMPLETED",
  "error_message": null
}
```

**Errors (400):** unsupported extension, invalid ZIP, ZIP without `.shp`, malformed/empty dataset.

### GET `/api/files/{id}/`

```bash
curl "http://127.0.0.1:8000/api/files/abc123def456/"
```

Same shape as upload response. **404** if ID unknown.

### GET `/api/files/{id}/measurements/`

```bash
curl "http://127.0.0.1:8000/api/files/abc123def456/measurements/"
```

**Response (200):**

```json
{
  "file_id": "abc123def456",
  "filename": "survey.kml",
  "crs": "EPSG:4326",
  "features": [
    {
      "id": 0,
      "geometry_type": "Polygon",
      "geometry": { "type": "Polygon", "coordinates": [] },
      "crs": "EPSG:4326",
      "properties": { "name": "parcel-1" },
      "measurement": { "type": "area", "value": 12543.72, "unit": "m²" },
      "measurement_status": null,
      "measurement_error": null
    }
  ]
}
```

## Architecture

```text
app/
├── main.py              # FastAPI app, exception handlers
├── api/files.py         # Thin routes
├── services/
│   ├── file_processor.py # KML/ZIP read, validation, feature extraction
│   ├── measurement.py    # Area/length per geometry type
│   └── crs.py            # Geographic detection, UTM selection, transform
├── repositories/         # In-memory store (replaceable)
├── models/schemas.py     # Pydantic models
└── core/config.py        # Settings
```

### File processing flow

```text
Upload
 ↓
Validate (extension, size, ZIP safety)
 ↓
Temporary directory (extract ZIP, locate .shp)
 ↓
GeoPandas read (KML driver or Shapefile)
 ↓
Default missing CRS to EPSG:4326 (logged)
 ↓
Per-feature measurement + properties
 ↓
Persist bytes under uploads/ + in-memory metadata
 ↓
Return FileResponse
```

### Storage

`InMemoryFileRepository` holds `FileRecord` (metadata + feature list). The processing pipeline does not depend on storage implementation—swap for PostgreSQL/PostGIS by implementing the same interface.

### Measurement calculation

| Geometry | Behavior |
|----------|----------|
| Point | `measurement: null` |
| LineString | Length in **meters** after projection |
| Polygon | Area in **m²** after projection |
| MultiLineString / MultiPolygon | Sum of parts (supported extension) |
| Other | `measurement_status: UNSUPPORTED` |

Never call `.area` or `.length` on EPSG:4326 coordinates for reporting.

## CRS Handling

**Why not EPSG:4326 for area/length?**  
EPSG:4326 uses **degrees**. Shapely’s `area`/`length` in that CRS are in degree² and degrees—not meters.

**Strategy (`app/services/crs.py`):**

1. Detect source CRS from the dataset (or assume EPSG:4326 if missing).
2. If CRS is **geographic**, compute a **representative point** (centroid / representative_point).
3. Derive **UTM zone** from longitude: `zone = floor((lon + 180) / 6) + 1` (clamped 1–60).
4. Northern hemisphere → EPSG `32600 + zone`, southern → `32700 + zone`.
5. Transform geometry with **PyProj** `Transformer` (`always_xy=True`).
6. If CRS is already **projected** (e.g. UTM), use it directly—no extra transform.

**Edge cases:**

- **Zone boundaries:** UTM is chosen from one representative point; very large polygons spanning zones may have small distortion at edges—a production system might split geometries or use an equal-area projection.
- **Missing CRS:** Assumed WGS84 for reading; UTM still applied for measurement.
- **Invalid CRS:** Treated as geographic when parsing fails (logged).

## Design Decisions

| Choice | Rationale |
|--------|-----------|
| FastAPI | Typed routes, automatic OpenAPI, async upload I/O |
| GeoPandas | Single API for KML + Shapefile + CRS metadata |
| Automatic UTM | Local metric accuracy without hard-coding one global CRS |
| Temp directories | Safe ZIP extract; automatic cleanup via `TemporaryDirectory` |
| Repository abstraction | Easy migration to PostGIS |
| Sync processing | Simplicity for take-home; status enum ready for Celery/RQ |
| Multi* geometries | Practical extension; documented in README |

**Large files:** Would use object storage, streaming read, background jobs, and chunked processing.

## Docker

```bash
docker build -t geo-measurement-api .
docker run -p 8000:8000 geo-measurement-api
```

The image installs GDAL/GEOS/PROJ system libraries required by GeoPandas.

## Testing

```bash
pytest
```

Tests cover upload validation, 404s, polygon/line/point measurements, EPSG:4326 metric results, projected CRS passthrough, and unsupported geometries.

## Learning

This project covers FastAPI service design, geospatial ingestion with GeoPandas, Shapely geometry handling, CRS and coordinate transformation concepts, metric measurements after projection, ZIP security, repository patterns, and pytest-based API testing.

## Future Scope

- PostgreSQL + PostGIS persistence
- Background job queue for large uploads
- S3/GCS object storage
- Authentication and rate limiting
- Spatial indexing and caching
- Additional formats (GeoPackage, GeoJSON)
- Smarter CRS (equal-area for global polygons, CRS per feature)
- Kubernetes Helm charts and horizontal scaling

## License

MIT (or as required by your submission).
