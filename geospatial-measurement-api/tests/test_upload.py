"""Upload endpoint tests."""

import io
import zipfile

from fastapi.testclient import TestClient

from tests.conftest import make_kml_bytes, make_shapefile_zip_bytes


def test_upload_valid_kml(client: TestClient) -> None:
    response = client.post(
        "/api/files/",
        files={"file": ("survey.kml", make_kml_bytes(), "application/vnd.google-earth.kml+xml")},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["filename"] == "survey.kml"
    assert data["status"] == "COMPLETED"
    assert data["feature_count"] >= 1
    assert data["crs"] is not None


def test_upload_valid_shapefile_zip(client: TestClient) -> None:
    response = client.post(
        "/api/files/",
        files={"file": ("parcel.zip", make_shapefile_zip_bytes(), "application/zip")},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "COMPLETED"
    assert data["feature_count"] == 3


def test_upload_unsupported_extension(client: TestClient) -> None:
    response = client.post(
        "/api/files/",
        files={"file": ("data.geojson", b"{}", "application/json")},
    )
    assert response.status_code == 400
    assert "Unsupported" in response.json()["detail"]


def test_upload_invalid_zip(client: TestClient) -> None:
    response = client.post(
        "/api/files/",
        files={"file": ("bad.zip", b"not a zip", "application/zip")},
    )
    assert response.status_code == 400
    assert "ZIP" in response.json()["detail"]


def test_upload_zip_without_shp(client: TestClient) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "no shapefile here")
    response = client.post(
        "/api/files/",
        files={"file": ("empty.zip", buf.getvalue(), "application/zip")},
    )
    assert response.status_code == 400
    assert ".shp" in response.json()["detail"].lower()


def test_get_file_valid_id(client: TestClient) -> None:
    upload = client.post(
        "/api/files/",
        files={"file": ("survey.kml", make_kml_bytes(), "application/octet-stream")},
    )
    file_id = upload.json()["id"]
    response = client.get(f"/api/files/{file_id}/")
    assert response.status_code == 200
    assert response.json()["id"] == file_id


def test_get_file_unknown_id(client: TestClient) -> None:
    response = client.get("/api/files/doesnotexist/")
    assert response.status_code == 404
