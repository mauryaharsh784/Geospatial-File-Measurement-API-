"""Measurements endpoint tests."""

from fastapi.testclient import TestClient

from tests.conftest import make_kml_bytes, make_shapefile_zip_bytes


def _upload_kml(client: TestClient) -> str:
    r = client.post(
        "/api/files/",
        files={"file": ("survey.kml", make_kml_bytes(), "application/octet-stream")},
    )
    assert r.status_code == 201
    return r.json()["id"]


def test_measurements_polygon_line_point(client: TestClient) -> None:
    file_id = _upload_kml(client)
    response = client.get(f"/api/files/{file_id}/measurements/")
    assert response.status_code == 200
    body = response.json()
    assert body["file_id"] == file_id
    features = body["features"]
    assert len(features) >= 3

    by_type = {f["geometry_type"]: f for f in features}
    assert "Polygon" in by_type
    assert "LineString" in by_type
    assert "Point" in by_type

    poly = by_type["Polygon"]
    assert poly["measurement"]["type"] == "area"
    assert poly["measurement"]["unit"] == "m²"
    assert poly["measurement"]["value"] > 0

    line = by_type["LineString"]
    assert line["measurement"]["type"] == "length"
    assert line["measurement"]["unit"] == "m"
    assert line["measurement"]["value"] > 0

    point = by_type["Point"]
    assert point["measurement"] is None


def test_measurements_unknown_file(client: TestClient) -> None:
    response = client.get("/api/files/unknown123/measurements/")
    assert response.status_code == 404


def test_shapefile_measurements(client: TestClient) -> None:
    upload = client.post(
        "/api/files/",
        files={"file": ("layer.zip", make_shapefile_zip_bytes(), "application/zip")},
    )
    file_id = upload.json()["id"]
    response = client.get(f"/api/files/{file_id}/measurements/")
    assert response.status_code == 200
    for feat in response.json()["features"]:
        assert feat["geometry_type"] == "Polygon"
        assert feat["measurement"]["type"] == "area"
        assert feat["measurement"]["value"] > 0
