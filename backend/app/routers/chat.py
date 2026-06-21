from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import anthropic

from app.auth.jwt import get_current_user
from app.config import settings
from app.database import get_db
from app.models.chat import ChatMessage
from app.models.project import Project
from app.models.user import User
from app.schemas.chat import ChatMessageCreate, ChatMessageRead

router = APIRouter(tags=["chat"])


async def _get_project_or_404(project_id: str, user_id: str, db: AsyncSession) -> Project:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/projects/{project_id}/chat", response_model=list[ChatMessageRead])
async def get_chat_history(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_project_or_404(project_id, current_user.id, db)

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.project_id == project_id)
        .order_by(ChatMessage.created_at.asc())
    )
    messages = result.scalars().all()
    return [ChatMessageRead.model_validate(m) for m in messages]


@router.post("/projects/{project_id}/chat", response_model=ChatMessageRead)
async def send_chat_message(
    project_id: str,
    body: ChatMessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(project_id, current_user.id, db)

    # Save user message
    user_msg = ChatMessage(
        project_id=project_id,
        role="user",
        content=body.content,
    )
    db.add(user_msg)
    await db.commit()

    # Fetch full conversation history for context
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.project_id == project_id)
        .order_by(ChatMessage.created_at.asc())
    )
    history = result.scalars().all()

    # Build messages for Claude API
    claude_messages = [
        {"role": m.role, "content": m.content}
        for m in history
    ]

    system_text = (
        "You are a helpful assistant for an AI worksheet generation platform. "
        "You help educators understand their generated worksheets, suggest improvements, "
        "and answer questions about the content.\n\n"
        f"Project: {project.name}\n"
        f"Subject: {project.subject or 'Not specified'}\n"
        f"Grade Level: {project.grade_level or 'Not specified'}\n"
        f"Instructions: {project.system_instructions or 'None'}"
    )

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=2048,
        system=[
            {
                "type": "text",
                "text": system_text,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=claude_messages,
    )

    assistant_content = response.content[0].text

    # Save assistant message
    assistant_msg = ChatMessage(
        project_id=project_id,
        role="assistant",
        content=assistant_content,
    )
    db.add(assistant_msg)
    await db.commit()
    await db.refresh(assistant_msg)

    return ChatMessageRead.model_validate(assistant_msg)
