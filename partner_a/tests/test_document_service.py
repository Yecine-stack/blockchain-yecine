import hashlib
import re
from datetime import datetime
from pathlib import Path

import pytest

from document_service import (
	DocumentAlreadyExistsError,
	DocumentNotFoundError,
	DocumentStorageError,
	InvalidInputError,
	UnsafePathError,
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


def test_hash_valid_file_returns_sha256(source_file: Path) -> None:
	result = calculate_sha256(str(source_file))
	assert len(result) == 64
	assert re.fullmatch(r"[0-9a-f]{64}", result)
	assert result == hashlib.sha256(source_file.read_bytes()).hexdigest()


def test_hashing_same_file_twice_is_deterministic(source_file: Path) -> None:
	assert calculate_sha256(str(source_file)) == calculate_sha256(str(source_file))


def test_identical_files_have_identical_hashes(tmp_path: Path) -> None:
	first = tmp_path / "first.txt"
	second = tmp_path / "second.txt"
	first.write_bytes(b"Fictional report")
	second.write_bytes(b"Fictional report")
	assert calculate_sha256(str(first)) == calculate_sha256(str(second))


def test_changing_one_byte_changes_hash(source_file: Path) -> None:
	original_hash = calculate_sha256(str(source_file))
	original_content = source_file.read_bytes()
	source_file.write_bytes(original_content[:-1] + bytes([original_content[-1] ^ 1]))
	assert calculate_sha256(str(source_file)) != original_hash


def test_verify_unchanged_document(source_file: Path) -> None:
	assert verify_document(str(source_file), calculate_sha256(str(source_file))) is True


def test_verify_modified_document_returns_false(source_file: Path) -> None:
	expected_hash = calculate_sha256(str(source_file))
	source_file.write_bytes(b"Modified fictional report")
	assert verify_document(str(source_file), expected_hash) is False


@pytest.mark.parametrize(
	"invalid_hash",
	["", "abc", "g" * 64, "a" * 63, "a" * 65, None, 123],
)
def test_malformed_hash_is_rejected(source_file: Path, invalid_hash: object) -> None:
	with pytest.raises(InvalidInputError):
		verify_document(str(source_file), invalid_hash)  # type: ignore[arg-type]


def test_hash_missing_file_raises_clear_exception(tmp_path: Path) -> None:
	with pytest.raises(DocumentNotFoundError):
		calculate_sha256(str(tmp_path / "missing.txt"))


def test_verify_missing_file_raises_clear_exception(tmp_path: Path) -> None:
	with pytest.raises(DocumentNotFoundError):
		verify_document(str(tmp_path / "missing.txt"), "a" * 64)


def test_store_document_creates_copy_and_metadata(
	source_file: Path,
	storage_dir: Path,
) -> None:
	metadata = store_document(
		str(source_file), "CASE-001", "DOC-001", "lab_report", str(storage_dir)
	)
	stored_file = storage_dir / metadata["storage_reference"]
	assert stored_file.is_file()
	assert stored_file.read_bytes() == source_file.read_bytes()
	assert source_file.is_file()


def test_stored_hash_matches_stored_bytes(
	source_file: Path,
	storage_dir: Path,
) -> None:
	metadata = store_document(
		str(source_file), "CASE-001", "DOC-001", "lab_report", str(storage_dir)
	)
	stored_file = storage_dir / metadata["storage_reference"]
	assert metadata["document_hash"] == calculate_sha256(str(stored_file))


def test_metadata_contains_required_fields(
	source_file: Path,
	storage_dir: Path,
) -> None:
	metadata = store_document(
		str(source_file), "CASE-001", "DOC-001", "lab_report", str(storage_dir)
	)
	assert set(metadata) == {
		"case_id",
		"artifact_id",
		"document_hash",
		"document_type",
		"created_at",
		"status",
		"storage_reference",
	}
	assert metadata["case_id"] == "CASE-001"
	assert metadata["artifact_id"] == "DOC-001"
	assert metadata["document_type"] == "lab_report"
	assert metadata["status"] == "STORED"
	assert re.fullmatch(r"[0-9a-f]{64}", metadata["document_hash"])
	assert metadata["storage_reference"] == (
		"CASE-001/DOC-001/original_fictional_report.txt"
	)
	timestamp = metadata["created_at"]
	assert timestamp.endswith("Z")
	assert datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


def test_metadata_contains_no_document_content_or_absolute_paths(
	source_file: Path,
	storage_dir: Path,
) -> None:
	metadata = store_document(
		str(source_file), "CASE-001", "DOC-001", "lab_report", str(storage_dir)
	)
	serialized = repr(metadata)
	assert source_file.read_text() not in serialized
	assert str(storage_dir.resolve()) not in serialized
	assert Path(metadata["storage_reference"]).is_absolute() is False


@pytest.mark.parametrize(
	("case_id", "artifact_id", "document_type"),
	[
		("", "DOC-001", "lab_report"),
		("CASE-001", "", "lab_report"),
		("CASE-001", "DOC-001", ""),
		("../outside", "DOC-001", "lab_report"),
		("CASE-001", "../outside", "lab_report"),
		("CASE-001", "DOC-001", "../invalid"),
		("CASE-001", "DOC-001", "Lab Report"),
	],
)
def test_invalid_identifiers_and_document_types_are_rejected(
	source_file: Path,
	storage_dir: Path,
	case_id: str,
	artifact_id: str,
	document_type: str,
) -> None:
	exception = UnsafePathError if ".." in case_id or ".." in artifact_id else InvalidInputError
	with pytest.raises(exception):
		store_document(
			str(source_file), case_id, artifact_id, document_type, str(storage_dir)
		)


def test_path_traversal_cannot_escape_storage_root(
	source_file: Path,
	storage_dir: Path,
	tmp_path: Path,
) -> None:
	outside_file = tmp_path / "outside" / "original_fictional_report.txt"
	with pytest.raises(UnsafePathError):
		store_document(
			str(source_file), "../outside", "DOC-001", "lab_report", str(storage_dir)
		)
	assert not outside_file.exists()


def test_duplicate_artifact_does_not_overwrite_original(
	source_file: Path,
	storage_dir: Path,
) -> None:
	metadata = store_document(
		str(source_file), "CASE-001", "DOC-001", "lab_report", str(storage_dir)
	)
	stored_file = storage_dir / metadata["storage_reference"]
	original_bytes = stored_file.read_bytes()
	replacement_source = source_file.parent / "replacement.txt"
	replacement_source.write_bytes(b"Different fictional content")

	with pytest.raises(DocumentAlreadyExistsError):
		store_document(
			str(replacement_source),
			"CASE-001",
			"DOC-001",
			"lab_report",
			str(storage_dir),
		)

	assert stored_file.read_bytes() == original_bytes


def test_storage_failure_raises_clear_exception(
	source_file: Path,
	tmp_path: Path,
) -> None:
	storage_path_is_file = tmp_path / "not_a_directory"
	storage_path_is_file.write_text("not a directory")
	with pytest.raises(DocumentStorageError):
		store_document(
			str(source_file),
			"CASE-001",
			"DOC-001",
			"lab_report",
			str(storage_path_is_file),
		)


def test_nonexistent_source_does_not_create_stored_document(tmp_path: Path) -> None:
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


def test_storage_reference_uses_forward_slashes(
	source_file: Path,
	storage_dir: Path,
) -> None:
	metadata = store_document(
		str(source_file), "CASE-001", "DOC-001", "lab_report", str(storage_dir)
	)
	assert metadata["storage_reference"] == (
		"CASE-001/DOC-001/original_fictional_report.txt"
	)
	assert "\\" not in metadata["storage_reference"]


def test_hash_is_case_insensitive_during_verification(source_file: Path) -> None:
	expected_hash = calculate_sha256(str(source_file)).upper()
	assert verify_document(str(source_file), expected_hash) is True
