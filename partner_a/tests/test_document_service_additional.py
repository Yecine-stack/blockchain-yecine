from datetime import datetime, timezone
from pathlib import Path

import pytest

import document_service
from document_service import (
	DocumentAlreadyExistsError,
	DocumentNotFoundError,
	DocumentStorageError,
	InvalidInputError,
	calculate_sha256,
	store_document,
	verify_document,
)


@pytest.fixture
def source_file(tmp_path: Path) -> Path:
	path = tmp_path / "fictional_report.txt"
	path.write_bytes(b"FICTIONAL MEDICAL REPORT\nTest data only.\n")
	return path


@pytest.fixture
def storage_dir(tmp_path: Path) -> Path:
	return tmp_path / "storage"


def test_store_document_does_not_modify_original(
	source_file: Path,
	storage_dir: Path,
) -> None:
	original_bytes = source_file.read_bytes()

	store_document(
		str(source_file),
		"CASE-001",
		"DOC-001",
		"lab_report",
		str(storage_dir),
	)

	assert source_file.read_bytes() == original_bytes


def test_duplicate_artifact_with_different_filename_is_rejected(
	source_file: Path,
	storage_dir: Path,
) -> None:
	store_document(
		str(source_file),
		"CASE-001",
		"DOC-001",
		"lab_report",
		str(storage_dir),
	)

	replacement = source_file.parent / "replacement.txt"
	replacement.write_bytes(b"Different fictional content")

	with pytest.raises(DocumentAlreadyExistsError):
		store_document(
			str(replacement),
			"CASE-001",
			"DOC-001",
			"lab_report",
			str(storage_dir),
		)

	artifact_directory = storage_dir / "CASE-001" / "DOC-001"
	assert sorted(path.name for path in artifact_directory.iterdir()) == [
		"original_fictional_report.txt"
	]


def test_failed_copy_removes_partial_destination(
	source_file: Path,
	storage_dir: Path,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	def fail_during_copy(source, destination, length=0):
		destination.write(b"PARTIAL")
		raise OSError("Simulated copy failure")

	monkeypatch.setattr(
		document_service.shutil,
		"copyfileobj",
		fail_during_copy,
	)

	with pytest.raises(DocumentStorageError):
		store_document(
			str(source_file),
			"CASE-001",
			"DOC-001",
			"lab_report",
			str(storage_dir),
		)

	artifact_directory = storage_dir / "CASE-001" / "DOC-001"
	assert not (artifact_directory / "original_fictional_report.txt").exists()


def test_empty_file_can_be_hashed_and_verified(tmp_path: Path) -> None:
	empty_file = tmp_path / "empty.txt"
	empty_file.write_bytes(b"")

	expected_hash = (
		"e3b0c44298fc1c149afbf4c8996fb924"
		"27ae41e4649b934ca495991b7852b855"
	)

	assert calculate_sha256(str(empty_file)) == expected_hash
	assert verify_document(str(empty_file), expected_hash) is True


def test_large_file_hash_matches_standard_library(tmp_path: Path) -> None:
	large_file = tmp_path / "large_fictional_report.bin"
	content = b"FICTIONAL-DATA-" * 200000
	large_file.write_bytes(content)

	assert calculate_sha256(str(large_file)) == (
		__import__("hashlib").sha256(content).hexdigest()
	)


def test_directory_is_rejected_as_document(tmp_path: Path) -> None:
	with pytest.raises(InvalidInputError):
		calculate_sha256(str(tmp_path))


def test_missing_source_does_not_create_storage_directory(
	tmp_path: Path,
) -> None:
	storage_dir = tmp_path / "storage"

	with pytest.raises(DocumentNotFoundError):
		store_document(
			str(tmp_path / "missing.txt"),
			"CASE-001",
			"DOC-001",
			"lab_report",
			str(storage_dir),
		)

	assert not storage_dir.exists()


def test_storage_path_that_is_a_file_is_rejected(
	source_file: Path,
	tmp_path: Path,
) -> None:
	storage_path = tmp_path / "not_a_directory"
	storage_path.write_text("fictional test data", encoding="utf-8")

	with pytest.raises(DocumentStorageError):
		store_document(
			str(source_file),
			"CASE-001",
			"DOC-001",
			"lab_report",
			str(storage_path),
		)


def test_timestamp_is_utc_and_has_expected_format(
	source_file: Path,
	storage_dir: Path,
) -> None:
	metadata = store_document(
		str(source_file),
		"CASE-001",
		"DOC-001",
		"lab_report",
		str(storage_dir),
	)

	timestamp = metadata["created_at"]
	assert timestamp.endswith("Z")

	parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
	assert parsed.tzinfo == timezone.utc


def test_stored_document_can_be_verified_using_returned_hash(
	source_file: Path,
	storage_dir: Path,
) -> None:
	metadata = store_document(
		str(source_file),
		"CASE-001",
		"DOC-001",
		"lab_report",
		str(storage_dir),
	)

	stored_file = storage_dir / metadata["storage_reference"]

	assert verify_document(
		str(stored_file),
		metadata["document_hash"],
	) is True

