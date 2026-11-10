from collections.abc import Iterable
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from fastapi_filter.base.filter import BaseFilterModel
from qdrant_client import models

from src.db.qdrant.schemas import QdrantPayload
from src.enums import Modality, Platform

_RANGE_OPERATORS = frozenset({"gt", "gte", "lt", "lte"})
_SUPPORTED_OPERATORS = frozenset({"", "in", "neq", "not_in", "isnull"}) | _RANGE_OPERATORS


def _payload_value(value: Any) -> Any:
    """Match the JSON form `QdrantPayload.model_dump(mode="json")` stored in the point."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    return value


def _split(field_name: str) -> tuple[str, str]:
    key, _, operator = field_name.partition("__")
    return key, operator


class QdrantFilter(BaseFilterModel):
    """fastapi-filter model translated to a Qdrant payload filter instead of a SQL query.

    Field names follow fastapi-filter's Django style (`platform`, `platform__in`,
    `created_at__gte`, ...); the part before `__` must be a field of `Constants.model`,
    which is checked when a subclass is defined. Supported operators: eq (no suffix),
    `in`, `neq`, `not_in`, `gt`/`gte`/`lt`/`lte` and `isnull`. `__nin` is deliberately
    unsupported: fastapi-filter splits it but no backend maps it.

    Ordering and free-text search do not apply (Qdrant ranks by score), so subclasses
    declare neither `order_by` nor `search`.
    """

    class Constants(BaseFilterModel.Constants):
        model = QdrantPayload

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        payload_fields = cls.Constants.model.model_fields
        for field_name in cls.model_fields:
            key, operator = _split(field_name)
            if key not in payload_fields:
                raise TypeError(f"{cls.__name__}.{field_name}: {key!r} is not a payload field")
            if operator not in _SUPPORTED_OPERATORS:
                raise TypeError(f"{cls.__name__}.{field_name}: unsupported operator {operator!r}")

    def filter_qdrant(self, must: Iterable[models.Condition] = ()) -> models.Filter:
        """Build the Qdrant filter; `must` (e.g. user scoping) is always applied first."""
        must = list(must)
        must_not: list[models.Condition] = []
        ranges: dict[str, dict[str, Any]] = {}

        for field_name, value in self.filtering_fields:
            key, operator = _split(field_name)
            match operator:
                case "":
                    must.append(self._match_value(key, value))
                case "in":
                    must.append(self._match_any(key, value))
                case "neq":
                    must_not.append(self._match_value(key, value))
                case "not_in":
                    must_not.append(self._match_any(key, value))
                case "isnull":
                    condition = models.IsNullCondition(is_null=models.PayloadField(key=key))
                    (must if value else must_not).append(condition)
                case op if op in _RANGE_OPERATORS:
                    ranges.setdefault(key, {})[op] = value
                case _:  # unreachable: rejected in __pydantic_init_subclass__
                    raise ValueError(f"Unsupported filter operator {operator!r}")

        for key, bounds in ranges.items():
            range_cls = (
                models.DatetimeRange
                if any(isinstance(v, datetime) for v in bounds.values())
                else models.Range
            )
            must.append(models.FieldCondition(key=key, range=range_cls(**bounds)))

        return models.Filter(must=must or None, must_not=must_not or None)

    @staticmethod
    def _match_value(key: str, value: Any) -> models.FieldCondition:
        return models.FieldCondition(key=key, match=models.MatchValue(value=_payload_value(value)))

    @staticmethod
    def _match_any(key: str, values: list[Any]) -> models.FieldCondition:
        return models.FieldCondition(
            key=key, match=models.MatchAny(any=[_payload_value(v) for v in values])
        )


class PointFilter(QdrantFilter):
    """Query-string filters for `GET /search`. No `user_id`: scoping is applied server-side."""

    platform: Platform | None = None
    platform__in: list[Platform] | None = None
    modality: Modality | None = None
    modality__in: list[Modality] | None = None
    post_id__in: list[UUID] | None = None
    created_at__gte: datetime | None = None
    created_at__lte: datetime | None = None
