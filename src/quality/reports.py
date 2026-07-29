"""Quality report dataclasses + JSON serialization.

Originally harvested from the legacy ``src/datagen/reports.py``; kept as a standalone copy
(not an import) so the quality layer has no cross-module dependency.
These are pure internal result objects: stdlib frozen dataclasses, no validation,
no scipy, no domain coupling.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Violation:
    kind: str
    field: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "field": self.field, "detail": self.detail}


@dataclass(frozen=True)
class SchemaCheck:
    passed: bool
    violations: list[Violation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "violations": [v.to_dict() for v in self.violations]}


@dataclass(frozen=True)
class DistributionCheck:
    observed: dict[str, Any]
    expected: dict[str, Any]
    chi2: float | None
    p_value: float | None
    passed: bool
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "observed": self.observed,
            "expected": self.expected,
            "chi2": self.chi2,
            "p_value": self.p_value,
            "passed": self.passed,
        }
        out.update(self.extra)
        return out


@dataclass(frozen=True)
class QualityReport:
    summary: dict[str, Any]
    schema: SchemaCheck
    distributions: dict[str, DistributionCheck]
    config_hash: str
    # Descriptive per-table/per-column profile (see quality/profiler.py). A plain
    # JSON-ready dict like `summary` — not a DistributionCheck — because it carries
    # no pass/fail verdict; it *describes* the data rather than gating it. Defaults
    # empty so a bare QualityReport (e.g. in older callers/tests) still constructs.
    profile: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": dict(self.summary),
            "schema": self.schema.to_dict(),
            "distributions": {k: v.to_dict() for k, v in self.distributions.items()},
            "profile": dict(self.profile),
            "config_hash": self.config_hash,
        }


def write_report(report: QualityReport, path: Path | str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return target


def compute_config_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
