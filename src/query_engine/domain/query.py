"""Query and result models."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Query:
    query_type: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class QueryResult:
    data: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)
