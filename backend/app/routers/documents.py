from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.jwt import get_current_user
from app.config import settings
from app.database import get_db
from app.models.document import Document, DocumentVersion
from app.models.project import Project
from app.models.user import User
from app.schemas.document import DocumentRead, DocumentSaveRequest, DocumentVersionRead
from app.services.storage import get_document_download_url, upload_document

router = APIRouter(prefix="/documents", tags=["documents"])


async def _get_document_or_404(doc_id: str, user_id: str, db: AsyncSession) -> Document:
    result = await db.execute(
        select(Document)
        .join(Project, Document.project_id == Project.id)
        .where(Document.id == doc_id, Project.owner_id == user_id)
        .options(selectinload(Document.versions))
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.get("/{doc_id}", response_model=DocumentRead)
async def get_document(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = await _get_document_or_404(doc_id, current_user.id, db)
    return DocumentRead.model_validate(doc)


@router.get("/{doc_id}/download")
async def download_document(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns a signed Supabase Storage URL for the latest document version.
    Returns 410 Gone if the document has expired.
    """
    doc = await _get_document_or_404(doc_id, current_user.id, db)

    now = datetime.now(timezone.utc)
    expires_at = doc.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Document has expired and is no longer available for download.",
        )

    # Find the current version
    current_version = next(
        (v for v in doc.versions if v.version_number == doc.current_version), None
    )
    if not current_version:
        raise HTTPException(status_code=404, detail="Document version not found")

    signed_url = get_document_download_url(current_version.storage_path)
    time_remaining = int((expires_at - now).total_seconds())

    return JSONResponse({
        "download_url": signed_url,
        "filename": f"{doc.title.replace(' ', '_')}_v{doc.current_version}.docx",
        "expires_at": expires_at.isoformat(),
        "time_remaining_seconds": time_remaining,
    })


@router.post("/{doc_id}/save", response_model=DocumentRead)
async def save_document(
    doc_id: str,
    body: DocumentSaveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Save a new version of the document from HTML content.
    Converts HTML -> DOCX via Pandoc and uploads to Supabase.
    Resets expires_at to now + TTL (extends the document's life).
    """
    doc = await _get_document_or_404(doc_id, current_user.id, db)

    now = datetime.now(timezone.utc)
    expires_at = doc.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Document has expired. Cannot save.",
        )

    from app.services.editor import html_to_docx

    docx_bytes = html_to_docx(body.content_html)
    new_version = doc.current_version + 1
    storage_path = upload_document(doc.id, new_version, docx_bytes)

    doc_version = DocumentVersion(
        document_id=doc.id,
        version_number=new_version,
        storage_path=storage_path,
        size_bytes=len(docx_bytes),
    )
    db.add(doc_version)

    if body.title:
        doc.title = body.title
    doc.current_version = new_version
    # Reset TTL — saving extends the document's life
    doc.expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.document_ttl_hours)

    await db.commit()
    await db.refresh(doc)

    # Reload versions
    result = await db.execute(
        select(Document)
        .where(Document.id == doc_id)
        .options(selectinload(Document.versions))
    )
    doc = result.scalar_one()
    return DocumentRead.model_validate(doc)


@router.get("/{doc_id}/content")
async def get_document_content(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Download the current DOCX from Supabase, convert to HTML via mammoth,
    and return it so the browser editor can display the document.
    """
    import httpx
    import mammoth

    doc = await _get_document_or_404(doc_id, current_user.id, db)

    now = datetime.now(timezone.utc)
    expires_at = doc.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < now:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Document has expired.")

    current_version = next(
        (v for v in doc.versions if v.version_number == doc.current_version), None
    )
    if not current_version:
        raise HTTPException(status_code=404, detail="Document version not found")

    # Get a short-lived signed URL and download the DOCX bytes
    signed_url = get_document_download_url(current_version.storage_path)
    async with httpx.AsyncClient() as client:
        response = await client.get(signed_url)
        response.raise_for_status()
        docx_bytes = response.content

    # Convert DOCX → HTML
    import io
    result = mammoth.convert_to_html(io.BytesIO(docx_bytes))
    html = result.value

    return JSONResponse({"html": html, "title": doc.title})


@router.get("/{doc_id}/versions", response_model=list[DocumentVersionRead])
async def list_versions(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = await _get_document_or_404(doc_id, current_user.id, db)
    return [DocumentVersionRead.model_validate(v) for v in sorted(doc.versions, key=lambda v: v.version_number)]


@router.post("/{doc_id}/ai-edit")
async def ai_edit_document(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Placeholder for AI-assisted editing of document content."""
    doc = await _get_document_or_404(doc_id, current_user.id, db)

    now = datetime.now(timezone.utc)
    expires_at = doc.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Document has expired.",
        )

    return {"message": "AI edit feature — provide instruction in request body", "doc_id": doc_id}


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document_endpoint(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = await _get_document_or_404(doc_id, current_user.id, db)

    from app.services.storage import delete_document

    for version in doc.versions:
        try:
            delete_document(version.storage_path)
        except Exception:
            pass

    await db.delete(doc)
    await db.commit()
