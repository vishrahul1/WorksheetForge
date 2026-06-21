from datetime import datetime
from pydantic import BaseModel


class ProjectFileRead(BaseModel):
    id: str
    project_id: str
    filename: str
    mime_type: str
    size_bytes: int
    storage_path: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ProjectFileList(BaseModel):
    files: list[ProjectFileRead]
    total: int
