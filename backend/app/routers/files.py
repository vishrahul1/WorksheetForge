from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.file import ProjectFile
from app.models.project import Project
from app.models.user import User
from app.schemas.file import ProjectFileList, ProjectFileRead
from app.services.extraction import extract_text
from app.services.storage import delete_source_file, upload_source_file

router = APIRouter(tags=["files"])

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "text/plain",
    "text/markdown",
    "text/x-markdown",
}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


async def _get_project_or_404(
    project_id: str, user_id: str, db: AsyncSession
) -> Project:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/projects/{project_id}/files", response_model=ProjectFileList)
async def list_files(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_project_or_404(project_id, current_user.id, db)
    result = await db.execute(
        select(ProjectFile)
        .where(ProjectFile.project_id == project_id)
        .order_by(ProjectFile.created_at.desc())
    )
    files = result.scalars().all()
    return ProjectFileList(
        files=[ProjectFileRead.model_validate(f) for f in files],
        total=len(files),
    )


@router.post(
    "/projects/{project_id}/files",
    response_model=ProjectFileRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_file(
    project_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_project_or_404(project_id, current_user.id, db)

    mime_type = file.content_type or "application/octet-stream"
    if mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {mime_type}. Allowed: PDF, DOCX, TXT, MD",
        )

    content_bytes = await file.read()
    if len(content_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024 * 1024)} MB",
        )

    # Upload to Supabase
    storage_path = upload_source_file(
        project_id, file.filename or "upload", content_bytes, mime_type
    )

    # Extract text for use in generation
    try:
        extracted = extract_text(content_bytes, mime_type)
    except Exception as exc:
        extracted = None

    pf = ProjectFile(
        project_id=project_id,
        filename=file.filename or "upload",
        mime_type=mime_type,
        size_bytes=len(content_bytes),
        storage_path=storage_path,
        extracted_text=extracted,
    )
    db.add(pf)
    await db.commit()
    await db.refresh(pf)
    return ProjectFileRead.model_validate(pf)


@router.delete(
    "/projects/{project_id}/files/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_file(
    project_id: str,
    file_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_project_or_404(project_id, current_user.id, db)

    result = await db.execute(
        select(ProjectFile).where(
            ProjectFile.id == file_id, ProjectFile.project_id == project_id
        )
    )
    pf = result.scalar_one_or_none()
    if not pf:
        raise HTTPException(status_code=404, detail="File not found")

    delete_source_file(pf.storage_path)
    await db.delete(pf)
    await db.commit()
