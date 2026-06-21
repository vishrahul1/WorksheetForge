from datetime import datetime
from pydantic import BaseModel


class RunCreate(BaseModel):
    selected_file_ids: list[str] | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    parallel_sections: int = 1        # how many sections to generate simultaneously


class RunPhaseRead(BaseModel):
    id: str
    run_id: str
    phase_name: str
    phase_order: int
    status: str
    output: str | None
    prompt_sent: str | None = None
    tokens_in: int
    tokens_out: int
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class RunRead(BaseModel):
    id: str
    project_id: str
    status: str
    selected_file_ids: list[str] | None
    llm_provider: str | None = None
    llm_model: str | None = None
    parallel_sections: int = 1
    total_tokens_in: int
    total_tokens_out: int
    estimated_cost_usd: float | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    phases: list[RunPhaseRead] = []

    model_config = {"from_attributes": True}
