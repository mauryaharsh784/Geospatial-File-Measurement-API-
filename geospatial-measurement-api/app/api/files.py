"""File upload and measurement endpoints."""

import logging
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.core.config import settings
from app.models.schemas import FileResponse, FileStatus, MeasurementsResponse
from app.repositories.file_repository import FileRecord, file_repository, new_file_id
from app.services.file_processor import FileProcessingError, process_uploaded_file
from app.services.measurement import dataset_crs_string

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/files", tags=["files"])


def _record_to_response(record: FileRecord) -> FileResponse:
    return FileResponse(
        id=record.id,
        filename=record.filename,
        feature_count=record.feature_count,
        crs=record.crs,
        status=record.status,
        error_message=record.error_message,
    )


@router.post("/", response_model=FileResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(file: UploadFile = File(...)) -> FileResponse:
    """Upload and synchronously process a KML or Shapefile ZIP."""
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )

    content = await file.read()
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds maximum size of {settings.max_upload_bytes} bytes",
        )

    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file",
        )

    file_id = new_file_id()
    record = FileRecord(
        id=file_id,
        filename=Path(file.filename).name,
        feature_count=0,
        crs=None,
        status=FileStatus.PROCESSING,
    )
    file_repository.create(record)

    try:
        gdf, features = process_uploaded_file(
            content,
            file.filename,
            settings.allowed_extensions,
        )
        crs_str = dataset_crs_string(gdf.crs)

        settings.ensure_uploads_dir()
        stored_name = f"{file_id}_{Path(file.filename).name}"
        stored_path = settings.uploads_dir / stored_name
        stored_path.write_bytes(content)

        record.feature_count = len(features)
        record.crs = crs_str
        record.features = features
        record.status = FileStatus.COMPLETED
        record.stored_path = stored_name
        file_repository.update(record)

        logger.info(
            "Processed file %s (%s) with %d features",
            file_id,
            record.filename,
            record.feature_count,
        )
        return _record_to_response(record)

    except FileProcessingError as exc:
        record.status = FileStatus.FAILED
        record.error_message = str(exc)
        file_repository.update(record)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error processing upload")
        record.status = FileStatus.FAILED
        record.error_message = "Internal processing error"
        file_repository.update(record)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process file",
        ) from exc


@router.get("/{file_id}/", response_model=FileResponse)
def get_file(file_id: str) -> FileResponse:
    """Return metadata for a processed upload."""
    record = file_repository.get(file_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with id '{file_id}' not found",
        )
    return _record_to_response(record)


@router.get("/{file_id}/measurements/", response_model=MeasurementsResponse)
def get_measurements(file_id: str) -> MeasurementsResponse:
    """Return per-feature measurements and attributes."""
    record = file_repository.get(file_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with id '{file_id}' not found",
        )
    if record.status == FileStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=record.error_message or "File processing failed",
        )
    return MeasurementsResponse(
        file_id=record.id,
        filename=record.filename,
        crs=record.crs,
        features=record.features,
    )
