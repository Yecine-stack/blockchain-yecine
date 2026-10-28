# Partner A: Medical Document Security and Integrity Module

## Purpose

Partner A is a standalone Python module for storing fictional medical documents outside the blockchain, calculating SHA-256 hashes, generating proof metadata, and verifying document integrity.

## Role in the Corda-Hedera project

1. Partner A stores a document locally and calculates its SHA-256 hash.
2. Partner A returns proof metadata.
3. Partner B uses the agreed identifiers and hash to record proof on Corda.
4. The wider integration layer handles any required Hedera interaction.
5. A document can later be verified against its reference hash.

Partner A does not implement blockchain connections, transactions, wallets, middleware, or a web interface.

## Requirements

- Python 3.10 or newer.
- `pytest` for testing.
- No other external runtime dependencies.

## Project structure

	partner_a/
	├── document_service.py
	├── README.md
	├── requirements.txt
	├── storage/
	│   └── .gitkeep
	└── tests/
		└── test_document_service.py

## Installation on Windows

Run these commands from the `partner_a` directory:

	python -m venv .venv
	.venv\Scripts\activate
	python -m pip install -r requirements.txt

Run automated tests:

	python -m pytest -v

Tests use temporary directories and fictional data.

## Public functions

### calculate_sha256(file_path)

Calculates the SHA-256 hash of a file's exact bytes and returns a lowercase hexadecimal string of 64 characters. The file is read in chunks.

	from document_service import calculate_sha256

	document_hash = calculate_sha256("fictional_report.txt")
	print(document_hash)

### store_document(source_path, case_id, artifact_id, document_type, storage_dir)

Copies a document into local storage and returns proof metadata. The original file is not deleted or modified. Existing destination files are not silently overwritten.

	from document_service import store_document

	metadata = store_document(
		source_path="fictional_report.txt",
		case_id="CASE-001",
		artifact_id="DOC-001",
		document_type="lab_report",
		storage_dir="storage",
	)

	print(metadata)

The stored file uses this layout:

	storage/CASE-001/DOC-001/original_fictional_report.txt

### verify_document(file_path, expected_hash)

Calculates the current hash and compares it with the expected hash. Returns `True` for a match and `False` for a mismatch. Invalid hashes, missing files, and unreadable files raise exceptions.

	from document_service import verify_document

	valid = verify_document(
		"storage/CASE-001/DOC-001/original_fictional_report.txt",
		metadata["document_hash"],
	)

	print(valid)

## Metadata schema

A successful storage operation returns:

	{
		"case_id": "CASE-001",
		"artifact_id": "DOC-001",
		"document_hash": "<64-character-lowercase-sha256-hash>",
		"document_type": "lab_report",
		"created_at": "2026-10-11T10:00:00Z",
		"status": "STORED",
		"storage_reference": "CASE-001/DOC-001/original_fictional_report.txt"
	}

Fields:

- `case_id`: Identifies a fictional case.
- `artifact_id`: Identifies a document within that case.
- `document_hash`: SHA-256 hash of the stored bytes.
- `document_type`: A short document category.
- `created_at`: UTC ISO 8601 timestamp ending in `Z`.
- `status`: `STORED` after successful storage.
- `storage_reference`: Relative path using forward slashes.

Identifiers must start with a letter or digit and contain only letters, digits, hyphens, or underscores, with a maximum length of 64 characters. Document types must start with a lowercase letter and contain only lowercase letters, digits, and underscores.

## Error handling

The module defines:

- `DocumentServiceError`: Base exception.
- `InvalidInputError`: Invalid arguments or malformed hashes.
- `DocumentNotFoundError`: Required file does not exist.
- `DocumentStorageError`: Storage or file-access failure.
- `DocumentAlreadyExistsError`: Destination already exists.
- `UnsafePathError`: Unsafe identifier or path.

Errors must not expose document contents. Callers should handle expected failures explicitly.

## Security limitations

SHA-256 is a fingerprint, not encryption. It does not hide document contents.

A matching hash shows that file bytes match a reference hash. It does not prove that a medical report is truthful, legally authentic, or medically correct. The reference hash must come from a trusted process; replacing both a document and its reference hash defeats a simple comparison.

The module does not implement encryption at rest, access-control management, backup protection, or complete protection against concurrent filesystem manipulation. Storage permissions and reference metadata must be protected by the surrounding application and operating system.

All sample data must be fictional. Metadata must not contain document contents, absolute storage paths, or patient-identifying information.

## Automated tests

The test suite covers hashing, identical and modified files, verification, invalid hashes, missing files, storage, metadata, path traversal, duplicate destinations, and storage failures.

Run:

	python -m pytest -v

Do not claim the tests pass unless the command has actually completed successfully.

## Integration with Partner B

Partner B can import the storage function and pass the relevant fields to its Corda integration:

	from document_service import store_document

	metadata = store_document(
		source_path="fictional_report.txt",
		case_id="CASE-001",
		artifact_id="DOC-001",
		document_type="lab_report",
		storage_dir="storage",
	)

	proof_for_partner_b = {
		"case_id": metadata["case_id"],
		"artifact_id": metadata["artifact_id"],
		"document_hash": metadata["document_hash"],
	}

This example only prepares a Python dictionary. It does not submit a blockchain transaction.

Both partners must agree on field names, identifier conventions, timestamp format, and error behavior before integration. Partner A ends its responsibility at local storage, hashing, verification, and metadata generation.

## Acceptance criteria

- The module works on Python 3.10 or newer.
- Stored bytes match the source bytes.
- The original file remains unchanged.
- Hashes are valid and deterministic.
- Modified documents fail verification against their original hash.
- Missing files and malformed hashes raise clear errors.
- Unsafe paths are rejected.
- Existing documents are not silently overwritten.
- Metadata follows the agreed schema and excludes document contents and absolute paths.
- No Corda or Hedera dependency is introduced.
- Automated tests pass.
