import logging
from supabase import create_client, Client

from app.config import settings

logger = logging.getLogger(__name__)

_client: Client | None = None


def get_supabase_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_service_key)
    return _client


def upload_source_file(
    project_id: str,
    filename: str,
    content_bytes: bytes,
    mime_type: str,
) -> str:
    """Upload a source file to the source-files bucket. Returns storage path."""
    client = get_supabase_client()
    storage_path = f"{project_id}/{filename}"
    client.storage.from_(settings.supabase_source_bucket).upload(
        path=storage_path,
        file=content_bytes,
        file_options={"content-type": mime_type, "upsert": "true"},
    )
    logger.info("Uploaded source file to %s/%s", settings.supabase_source_bucket, storage_path)
    return storage_path


def get_source_file_url(storage_path: str) -> str:
    """Generate a signed URL for a source file, valid for 1 hour."""
    client = get_supabase_client()
    response = client.storage.from_(settings.supabase_source_bucket).create_signed_url(
        storage_path, expires_in=3600
    )
    return response["signedURL"]


def upload_document(doc_id: str, version: int, docx_bytes: bytes) -> str:
    """Upload a generated DOCX to the generated-docs bucket. Returns storage path."""
    client = get_supabase_client()
    storage_path = f"{doc_id}/v{version}.docx"
    client.storage.from_(settings.supabase_docs_bucket).upload(
        path=storage_path,
        file=docx_bytes,
        file_options={
            "content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "upsert": "true",
        },
    )
    logger.info("Uploaded document to %s/%s", settings.supabase_docs_bucket, storage_path)
    return storage_path


def get_document_download_url(storage_path: str) -> str:
    """Generate a signed URL for a generated document, valid for 2 hours."""
    client = get_supabase_client()
    response = client.storage.from_(settings.supabase_docs_bucket).create_signed_url(
        storage_path, expires_in=7200  # 2 hours
    )
    return response["signedURL"]


def delete_document(storage_path: str) -> None:
    """Delete a generated document from Supabase Storage."""
    client = get_supabase_client()
    try:
        client.storage.from_(settings.supabase_docs_bucket).remove([storage_path])
        logger.info("Deleted document %s from storage", storage_path)
    except Exception as exc:
        logger.warning("Failed to delete document %s: %s", storage_path, exc)


def delete_source_file(storage_path: str) -> None:
    """Delete a source file from Supabase Storage."""
    client = get_supabase_client()
    try:
        client.storage.from_(settings.supabase_source_bucket).remove([storage_path])
        logger.info("Deleted source file %s from storage", storage_path)
    except Exception as exc:
        logger.warning("Failed to delete source file %s: %s", storage_path, exc)
