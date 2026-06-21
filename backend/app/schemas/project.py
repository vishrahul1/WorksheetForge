from datetime import datetime
from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    system_instructions: str | None = None
    subject: str | None = None
    grade_level: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    system_instructions: str | None = None
    subject: str | None = None
    grade_level: str | None = None


class ProjectRead(BaseModel):
    id: str
    owner_id: str
    name: str
    description: str | None
    system_instructions: str | None
    subject: str | None
    grade_level: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectList(BaseModel):
    id: str
    name: str
    description: str | None
    subject: str | None
    grade_level: str | None
    created_at: datetime
    updated_at: datetime
    last_run_status: str | None = None

    model_config = {"from_attributes": True}
