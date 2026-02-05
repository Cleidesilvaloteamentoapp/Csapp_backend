"""Tests for storage service validations."""

import pytest

from app.services.storage_service import validate_file
from app.utils.exceptions import StorageError


def test_valid_pdf():
    """PDF files should pass validation."""
    validate_file("contract.pdf", 1024)


def test_valid_jpg():
    """JPG files should pass validation."""
    validate_file("photo.jpg", 2048)


def test_valid_png():
    """PNG files should pass validation."""
    validate_file("document.png", 500)


def test_invalid_extension():
    """Unsupported extensions should raise StorageError."""
    with pytest.raises(StorageError, match="not allowed"):
        validate_file("script.exe", 100)


def test_file_too_large():
    """Files exceeding 10MB should raise StorageError."""
    with pytest.raises(StorageError, match="maximum size"):
        validate_file("big.pdf", 11 * 1024 * 1024)


def test_valid_docx():
    """DOCX files should pass validation."""
    validate_file("report.docx", 5000)


def test_invalid_svg():
    """SVG is not in the allowed list."""
    with pytest.raises(StorageError, match="not allowed"):
        validate_file("image.svg", 100)
