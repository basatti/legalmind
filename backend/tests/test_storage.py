"""Tests for the file storage backend."""

import pytest

from foundation.storage import LocalDiskStorage, StorageBackend


@pytest.fixture
def files(tmp_path):
    """Storage rooted in a temp directory, so tests never touch real uploads."""
    return LocalDiskStorage(base_dir=str(tmp_path))


def test_local_disk_storage_satisfies_the_interface(files):
    assert isinstance(files, StorageBackend)


def test_save_then_read_returns_the_same_bytes(files):
    """Background ingestion runs long after the upload request has finished, so
    it can only work if the bytes come back out intact."""
    content = b"%PDF-1.4 fake pdf bytes"
    path = files.save(case_id=1, filename="ruling.pdf", content=content)

    assert files.read(path) == content


def test_saved_path_is_relative_not_absolute(files):
    """The path goes into the database, so it must not embed a machine-specific
    absolute path."""
    path = files.save(case_id=7, filename="a.pdf", content=b"x")

    assert not path.startswith(str(files.base_dir))
    assert "7" in path


def test_files_are_separated_by_case(files):
    one = files.save(case_id=1, filename="same-name.pdf", content=b"first")
    two = files.save(case_id=2, filename="same-name.pdf", content=b"second")

    assert one != two
    assert files.read(one) == b"first"
    assert files.read(two) == b"second"


def test_same_filename_twice_does_not_overwrite(files):
    first = files.save(case_id=1, filename="dup.pdf", content=b"original")
    second = files.save(case_id=1, filename="dup.pdf", content=b"replacement")

    assert first != second
    assert files.read(first) == b"original"


def test_reading_a_missing_file_raises(files):
    """Ingestion needs a real error here — a missing file must surface as a
    failed job, not as a silent success with no content."""
    with pytest.raises(FileNotFoundError):
        files.read("1/does-not-exist.pdf")


def test_reading_a_deleted_file_raises(files):
    path = files.save(case_id=1, filename="gone.pdf", content=b"bye")
    files.delete(path)

    with pytest.raises(FileNotFoundError):
        files.read(path)


def test_deleting_a_missing_file_is_harmless(files):
    """delete() is idempotent on purpose — cleanup paths shouldn't explode."""
    files.delete("1/never-existed.pdf")
