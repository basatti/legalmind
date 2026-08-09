import os
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

# The backend package root — the directory holding `src/`, `migrations/` and
# `storage/`. Derived from this file's own location so it is the same answer in
# every process, whatever directory that process was started from.
BACKEND_ROOT = Path(__file__).resolve().parents[2]


def default_storage_dir() -> Path:
    """Where uploaded documents live, as an absolute path.

    Deliberately not relative to the current working directory. The API and the
    ingestion worker are started from different directories — and under compose,
    from different containers — so a cwd-relative root silently gives them two
    different trees: the upload lands in one, the worker looks in the other and
    the job fails with a file-not-found it cannot explain.

    `STORAGE_DIR` overrides the location (compose points it at a mounted
    volume). A relative override is anchored to the backend root, never to cwd,
    so it cannot reintroduce the same split.
    """
    configured = os.environ.get("STORAGE_DIR")
    if not configured:
        return BACKEND_ROOT / "storage" / "documents"

    override = Path(configured)
    return override if override.is_absolute() else BACKEND_ROOT / override


class StorageBackend(ABC):
    """Common interface for any file storage implementation."""

    @abstractmethod
    def save(self, case_id: int, filename: str, content: bytes) -> str:
        """Saves file content, returns the path to store in the DB."""

    @abstractmethod
    def delete(self, file_path: str) -> None:
        """Deletes a stored file given its stored path."""

    @abstractmethod
    def read(self, file_path: str) -> bytes:
        """Reads back a stored file given its stored path.

        Needed by background ingestion, which runs long after the upload
        request has finished and so has no access to the original bytes.
        """


class LocalDiskStorage(StorageBackend):
    """Stores files on the local server disk, organized by case_id."""

    def __init__(self, base_dir: str | Path | None = None):
        self.base_dir = Path(base_dir) if base_dir is not None else default_storage_dir()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, case_id: int, filename: str, content: bytes) -> str:
        case_dir = self.base_dir / str(case_id)
        case_dir.mkdir(parents=True, exist_ok=True)

        safe_name = f"{uuid.uuid4()}_{filename}"
        full_path = case_dir / safe_name
        full_path.write_bytes(content)

        # Store a relative path in the DB, not an absolute one
        return str(full_path.relative_to(self.base_dir))

    def delete(self, file_path: str) -> None:
        full_path = self.base_dir / file_path
        if full_path.exists():
            os.remove(full_path)

    def read(self, file_path: str) -> bytes:
        full_path = self.base_dir / file_path
        if not full_path.exists():
            # The resolved path, not just the stored fragment: when this fires
            # the useful question is almost always "which root was it looking
            # in", and the fragment alone cannot answer it.
            raise FileNotFoundError(f"No stored file at {full_path}")
        return full_path.read_bytes()


# Single shared instance the rest of the app will import and use
storage = LocalDiskStorage()
