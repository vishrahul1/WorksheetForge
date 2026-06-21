from datetime import datetime
from pydantic import BaseModel


class ChatMessageCreate(BaseModel):
    content: str


class ChatMessageRead(BaseModel):
    id: str
    project_id: str
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}
