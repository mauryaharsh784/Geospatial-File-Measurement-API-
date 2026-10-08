"""In-memory file metadata and feature results (swappable for PostGIS later)."""

from dataclasses import dataclass, field
from typing import Protocol
from uuid import uuid4

from app.models.schemas import FeatureResponse, FileStatus


@dataclass
class FileRecord:
    """Stored upload with processing outcome."""

    id: str
    filename: str
    feature_count: int
    crs: str | None
    status: FileStatus
    features: list[FeatureResponse] = field(default_factory=list)
    error_message: str | None = None
    stored_path: str | None = None


class FileRepository(Protocol):
    """Repository interface for file records."""

    def create(self, record: FileRecord) -> FileRecord: ...

    def get(self, file_id: str) -> FileRecord | None: ...

    def update(self, record: FileRecord) -> FileRecord: ...


class InMemoryFileRepository:
    """Thread-unsafe in-memory store suitable for the assignment."""

    def __init__(self) -> None:
        self._store: dict[str, FileRecord] = {}

    def create(self, record: FileRecord) -> FileRecord:
        self._store[record.id] = record
        return record

    def get(self, file_id: str) -> FileRecord | None:
        return self._store.get(file_id)

    def update(self, record: FileRecord) -> FileRecord:
        self._store[record.id] = record
        return record


def new_file_id() -> str:
    return uuid4().hex[:12]


file_repository: InMemoryFileRepository = InMemoryFileRepository()
