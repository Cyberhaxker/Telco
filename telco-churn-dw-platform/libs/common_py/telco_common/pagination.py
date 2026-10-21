from __future__ import annotations

from typing import Annotated, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel

T = TypeVar("T")


class PageParams(BaseModel):
    limit: int = 50
    offset: int = 0


def page_params(
    limit: Annotated[int, Query(ge=1, le=500, description="Page size")] = 50,
    offset: Annotated[int, Query(ge=0, description="Rows to skip")] = 0,
) -> PageParams:
    return PageParams(limit=limit, offset=offset)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int
