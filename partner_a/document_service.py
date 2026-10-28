import hashlib
import hmac
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_DOCUMENT_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
_CHUNK_SIZE = 1024 * 1024


class DocumentServiceError(Exception):
	"""Base exception for document service failures."""


class InvalidInputError(DocumentServiceError, ValueError):
	"""Raised when an input is invalid."""


class DocumentNotFoundError(DocumentServiceError, FileNotFoundError):
	"""Raised when a required document does not exist."""


class DocumentStorageError(DocumentServiceError, OSError):
	"""Raised when a document cannot be stored or accessed."""


class DocumentAlreadyExistsError(DocumentServiceError, FileExistsError):
	"""Raised when a destination document already exists."""


class UnsafePathError(DocumentServiceError, ValueError):
	"""Raised when a path or identifier is unsafe."""


def _validate_identifier(value: str, field_name: str) -> str:
	if not isinstance(value, str) or not value.strip():
		raise InvalidInputError(f"{field_name} must be a non-empty string.")

	if value != value.strip() or not _IDENTIFIER_PATTERN.fullmatch(value):
		raise UnsafePathError(f"{field_name} contains invalid characters.")

	return value


def _validate_document_type(document_type: str) -> str:
	if not isinstance(document_type, str) or not document_type.strip():
		raise InvalidInputError("document_type must be a non-empty string.")

	if not _DOCUMENT_TYPE_PATTERN.fullmatch(document_type):
		raise InvalidInputError(
			"document_type must start with a lowercase letter and contain "
			"only lowercase letters, digits, and underscores."
		)

	return document_type


def _resolve_file_path(file_path: str, field_name: str = "file_path") -> Path:
	if not isinstance(file_path, (str, Path)) or not str(file_path).strip():
		raise InvalidInputError(f"{field_name} must be a non-empty path.")

	try:
		path = Path(file_path).resolve(strict=True)
	except FileNotFoundError as exc:
		raise DocumentNotFoundError(f"{field_name} does not exist.") from exc
	except (OSError, RuntimeError) as exc:
		raise DocumentStorageError(f"{field_name} could not be resolved.") from exc

	if not path.is_file():
		raise InvalidInputError(f"{field_name} must refer to a regular file.")

	return path


def _validate_expected_hash(expected_hash: str) -> str:
	if not isinstance(expected_hash, str):
		raise InvalidInputError("expected_hash must be a string.")

	if not _SHA256_PATTERN.fullmatch(expected_hash):
		raise InvalidInputError(
			"expected_hash must contain exactly 64 hexadecimal characters."
		)

	return expected_hash.lower()


def calculate_sha256(file_path: str) -> str:
	"""Calculate the SHA-256 hash of a file's exact bytes."""
	path = _resolve_file_path(file_path)
	digest = hashlib.sha256()

	try:
		with path.open("rb") as file:
			while True:
				chunk = file.read(_CHUNK_SIZE)
				if not chunk:
					break
				digest.update(chunk)
	except OSError as exc:
		raise DocumentStorageError("The document could not be read.") from exc

	return digest.hexdigest()


def store_document(
	source_path: str,
	case_id: str,
	artifact_id: str,
	document_type: str,
	storage_dir: str,
) -> dict[str, Any]:
	"""Store a document locally and return its proof metadata."""
	case_id = _validate_identifier(case_id, "case_id")
	artifact_id = _validate_identifier(artifact_id, "artifact_id")
	document_type = _validate_document_type(document_type)
	source = _resolve_file_path(source_path, "source_path")

	if not isinstance(storage_dir, (str, Path)) or not str(storage_dir).strip():
		raise InvalidInputError("storage_dir must be a non-empty path.")

	try:
		root = Path(storage_dir).resolve()
		root.mkdir(parents=True, exist_ok=True)
		root = root.resolve(strict=True)
	except (OSError, RuntimeError) as exc:
		raise DocumentStorageError(
			"The storage directory could not be created or accessed."
		) from exc

	if not root.is_dir():
		raise DocumentStorageError("The storage root must be a directory.")

	case_directory = root / case_id
	artifact_directory = case_directory / artifact_id
	destination = artifact_directory / f"original_{source.name}"

	try:
		case_directory.mkdir(exist_ok=True)
		artifact_directory.mkdir(exist_ok=True)

		resolved_case = case_directory.resolve(strict=True)
		resolved_artifact = artifact_directory.resolve(strict=True)

		if not resolved_case.is_relative_to(root):
			raise UnsafePathError("The case directory escapes the storage root.")

		if not resolved_artifact.is_relative_to(root):
			raise UnsafePathError("The artifact directory escapes the storage root.")

		destination = resolved_artifact / destination.name

		if any(artifact_directory.iterdir()):
			raise DocumentAlreadyExistsError(
				"A document already exists for this artifact identifier."
			)

		with source.open("rb") as source_file:
			with destination.open("xb") as destination_file:
				shutil.copyfileobj(
					source_file,
					destination_file,
					length=_CHUNK_SIZE,
				)

		document_hash = calculate_sha256(str(destination))
		storage_reference = destination.relative_to(root).as_posix()
		created_at = (
			datetime.now(timezone.utc)
			.isoformat(timespec="seconds")
			.replace("+00:00", "Z")
		)

		return {
			"case_id": case_id,
			"artifact_id": artifact_id,
			"document_hash": document_hash,
			"document_type": document_type,
			"created_at": created_at,
			"status": "STORED",
			"storage_reference": storage_reference,
		}

	except DocumentServiceError:
		raise
	except FileExistsError as exc:
		raise DocumentAlreadyExistsError(
			"The destination already exists; no document was overwritten."
		) from exc
	except (OSError, RuntimeError, ValueError) as exc:
		try:
			if destination.is_file():
				destination.unlink()
		except OSError:
			pass

		raise DocumentStorageError(
			"The document could not be stored successfully."
		) from exc


def verify_document(file_path: str, expected_hash: str) -> bool:
	"""Return True if the document matches its expected SHA-256 hash."""
	expected = _validate_expected_hash(expected_hash)
	actual = calculate_sha256(file_path)
	return hmac.compare_digest(actual, expected)
