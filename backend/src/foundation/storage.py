import os
import uuid
from abc import ABC, abstractmethod
from pathlib import Path


class StorageBackend(ABC):
    """Common interface for any file storage implementation."""

    @abstractmethod
    def save(self, case_id: int, filename: str, content: bytes) -> str:
        """Saves file content, returns the path to store in the DB."""

    @abstractmethod
    def read(self, file_path: str) -> bytes:
        """Reads back file content given its stored path.

        Ingestion needs the original bytes to parse; uploading only ever wrote
        them. Raises FileNotFoundError if the file is gone.
        """

    @abstractmethod
    def delete(self, file_path: str) -> None:
        """Deletes a stored file given its stored path."""


class LocalDiskStorage(StorageBackend):
    """Stores files on the local server disk, organized by case_id."""

    def __init__(self, base_dir: str = "storage/documents"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, case_id: int, filename: str, content: bytes) -> str:
        case_dir = self.base_dir / str(case_id)
        case_dir.mkdir(parents=True, exist_ok=True)

        safe_name = f"{uuid.uuid4()}_{filename}"
        full_path = case_dir / safe_name
        full_path.write_bytes(content)

        # Store a relative path in the DB, not an absolute one
        return str(full_path.relative_to(self.base_dir))

    def read(self, file_path: str) -> bytes:
        full_path = self.base_dir / file_path
        return full_path.read_bytes()

    def delete(self, file_path: str) -> None:
        full_path = self.base_dir / file_path
        if full_path.exists():
            os.remove(full_path)


# Single shared instance the rest of the app will import and use
storage = LocalDiskStorage()
