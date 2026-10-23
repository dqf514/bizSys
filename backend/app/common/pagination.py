"""分页参数与返回结构。"""

from dataclasses import dataclass

from pydantic import BaseModel, Field

MAX_PAGE_SIZE = 200
# page 上限：防 OFFSET bigint 溢出（MySQL OFFSET 上限约 2^64-1，过大值直接 500）
PAGE_MAX = 10**9


class PageParams(BaseModel):
    page: int = Field(1, ge=1, le=PAGE_MAX)
    size: int = Field(20, ge=1, le=MAX_PAGE_SIZE)


class PageResult(BaseModel):
    items: list = []
    total: int = 0
    page: int = 1
    size: int = 20


@dataclass
class Page:
    items: list
    total: int
    page: int
    size: int

    def dict(self) -> dict:
        return {"items": self.items, "total": self.total, "page": self.page, "size": self.size}


def page_result(items: list, total: int, page: int, size: int) -> dict:
    return {"items": items, "total": total, "page": page, "size": size}
