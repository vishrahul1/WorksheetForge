from datetime import datetime
from pydantic import BaseModel, computed_field
from zoneinfo import ZoneInfo


class DocumentVersionRead(BaseModel):
    id: str
    document_id: str
    version_number: int
    storage_path: str
    size_bytes: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentRead(BaseModel):
    id: str
    run_id: str
    project_id: str
    title: str
    current_version: int
    expires_at: datetime
    created_at: datetime
    updated_at: datetime
    versions: list[DocumentVersionRead] = []

    @computed_field
    @property
    def time_remaining_seconds(self) -> int:
        from datetime import timezone

        now = datetime.now(timezone.utc)
        expires = self.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        delta = (expires - now).total_seconds()
        return max(0, int(delta))

    @computed_field
    @property
    def is_expired(self) -> bool:
        return self.time_remaining_seconds == 0

    model_config = {"from_attributes": True}


class DocumentSaveRequest(BaseModel):
    content_html: str
    title: str | None = None
