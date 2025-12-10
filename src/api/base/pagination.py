from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import List, Sequence, Tuple, TypeVar

from sqlalchemy.orm import Query

T = TypeVar("T")


@dataclass
class PaginationMeta:
    total: int
    limit: int
    offset: int
    count: int

    def to_dict(self) -> dict:
        return asdict(self)


def paginate_query(query: Query, limit: int, offset: int) -> Tuple[int, List[T]]:
    """
    对 SQLAlchemy 查询应用 limit/offset，并返回总数与结果列表。
    """
    total = query.order_by(None).count()
    records = query.offset(offset).limit(limit).all()
    return total, records


def paginate_sequence(
    items: Sequence[T], limit: int, offset: int
) -> Tuple[List[T], PaginationMeta]:
    """
    对内存序列应用分页，返回切片和元数据。
    """
    total = len(items)
    sliced = list(items[offset : offset + limit])
    meta = PaginationMeta(total=total, limit=limit, offset=offset, count=len(sliced))
    return sliced, meta


def build_pagination_payload(items: List[dict], meta: PaginationMeta, **extra) -> dict:
    """
    构建标准分页响应 payload。
    """
    payload = {"items": items, "meta": meta.to_dict()}
    payload.update(extra)
    return payload
