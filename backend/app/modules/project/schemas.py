"""项目管理入参模型（B5 CSV 31）。"""

from pydantic import Field

from app.core.schemas import CamelModel, OptionalDate


class ProjectIn(CamelModel):
    name: str = Field(..., min_length=1, max_length=255)
    customer_id: int | None = None
    customer_name: str = Field("", max_length=128)
    contract_id: int | None = None
    contract_no: str = Field("", max_length=32)
    manager_id: int | None = None
    manager_name: str = Field("", max_length=64)
    dept_id: int | None = None
    dept_name: str = Field("", max_length=64)
    start_date: OptionalDate = None
    end_date: OptionalDate = None
    status: str = Field("draft", max_length=16)
    budget_amount: float | None = None
    description: str = Field("", max_length=4000)
    remark: str = Field("", max_length=500)
    version: int | None = None


class ProjectTaskIn(CamelModel):
    task_id: int | None = None
    task_no: str = Field("", max_length=32)
    task_name: str = Field("", max_length=255)
    seq: int = 1
    group_code: str = Field("", max_length=32)
    owner_id: int | None = None
    owner_name: str = Field("", max_length=64)
    start_date: OptionalDate = None
    end_date: OptionalDate = None
    progress: int = Field(0, ge=0, le=100)
    milestone: int = 0
    weight: float = 0
    status: str = Field("pending", max_length=16)
    depends_on: str = Field("", max_length=255)
    remark: str = Field("", max_length=500)


class GenerateTasksIn(CamelModel):
    """从任务与排期自动生成项目任务（甘特图）。"""

    task_ids: list[int] = Field(default_factory=list)
    project_id: int | None = None
    group_code: str = Field("", max_length=32)
    overwrite: int = 0
