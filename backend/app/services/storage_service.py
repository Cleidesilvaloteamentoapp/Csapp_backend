
"""Supabase Storage service for file upload / download / delete."""

import uuid as uuid_mod
from pathlib import PurePosixPath

from supabase import create_client

from app.core.config import settings
from app.utils.exceptions import StorageError
from app.utils.logging import get_logger

logger = get_logger(__name__)

ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png", "doc", "docx"}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


def _get_supabase():
    """Create a Supabase client using the secret key (server-side)."""
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SECRET_KEY)


def _sanitize_filename(original: str) -> str:
    """Generate a safe unique filename preserving the extension."""
    ext = PurePosixPath(original).suffix.lower().lstrip(".")
    if ext not in ALLOWED_EXTENSIONS:
        raise StorageError(f"File type '.{ext}' is not allowed. Allowed: {ALLOWED_EXTENSIONS}")
    return f"{uuid_mod.uuid4().hex}.{ext}"


def validate_file(filename: str, size: int) -> None:
    """Validate file type and size before upload."""
    ext = PurePosixPath(filename).suffix.lower().lstrip(".")
    if ext not in ALLOWED_EXTENSIONS:
        raise StorageError(f"File type '.{ext}' not allowed. Allowed: {ALLOWED_EXTENSIONS}")
    if size > MAX_FILE_SIZE_BYTES:
        raise StorageError(f"File exceeds maximum size of {MAX_FILE_SIZE_BYTES // (1024*1024)} MB")


async def upload_file(
    file_bytes: bytes,
    original_filename: str,
    company_id: str,
    subfolder: str = "documents",
) -> str:
    """Upload a file to Supabase Storage and return the storage path.

    File is stored under:
      {bucket}/companies/{company_id}/{subfolder}/{unique_name}
    """
    validate_file(original_filename, len(file_bytes))
    safe_name = _sanitize_filename(original_filename)
    storage_path = f"companies/{company_id}/{subfolder}/{safe_name}"

    try:
        supabase = _get_supabase()
        supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET).upload(
            path=storage_path,
            file=file_bytes,
            file_options={"content-type": "application/octet-stream"},
        )
    except Exception as exc:
        logger.error("storage_upload_failed", path=storage_path, error=str(exc))
        raise StorageError(f"Upload failed: {exc}") from exc

    logger.info("storage_uploaded", path=storage_path)
    return storage_path


def get_public_url(storage_path: str, expires_in: int = 3600) -> str:
    """Return a signed URL for an uploaded file (expires in 1 hour by default)."""
    try:
        supabase = _get_supabase()
        data = supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET).create_signed_url(
            storage_path, expires_in
        )
        if isinstance(data, dict) and "signedURL" in data:
            return data["signedURL"]
        return data
    except Exception as exc:
        raise StorageError(f"Failed to get URL: {exc}") from exc


async def delete_file(storage_path: str) -> None:
    """Delete a file from Supabase Storage."""
    try:
        supabase = _get_supabase()
        supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET).remove([storage_path])
        logger.info("storage_deleted", path=storage_path)
    except Exception as exc:
        logger.error("storage_delete_failed", path=storage_path, error=str(exc))
        raise StorageError(f"Delete failed: {exc}") from exc


async def list_files(company_id: str, subfolder: str = "documents") -> list[dict]:
    """List files in a company's subfolder."""
    prefix = f"companies/{company_id}/{subfolder}"
    try:
        supabase = _get_supabase()
        files = supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET).list(prefix)
        return files
    except Exception as exc:
        raise StorageError(f"List failed: {exc}") from exc
