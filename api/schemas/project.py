from pydantic import BaseModel
from typing import Optional


class ProjectResponse(BaseModel):
    project_id: str
    project_name: Optional[str] = None
    state: Optional[str] = None
    sector: Optional[str] = None
    original_cost: Optional[float] = None
    revised_cost: Optional[float] = None
    physical_progress: Optional[float] = None


class ProjectListResponse(BaseModel):
    projects: list[ProjectResponse]
    total: int
    page: int
    page_size: int