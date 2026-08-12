from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from experiments.voltage_sweep import MeasurementPoint


@dataclass
class RunRecord:
    """
    Typed record for a run (barrido / calibración / corregido / importado).
    This dataclass is provided as a typed model for future refactors.
    It implements mapping-style accessors (__getitem__/__setitem__) so it can
    be used as a drop-in replacement for the current dict-based code while
    incrementally migrating code to attribute access.
    """

    id: int
    kind: str
    label: str
    curve_tag: str
    measurements: List[MeasurementPoint] = field(default_factory=list)
    peak: Optional[MeasurementPoint] = None
    peaks: List[MeasurementPoint] = field(default_factory=list)
    csv_filename: Optional[str] = None
    row_tag: Optional[str] = None
    text_tag: Optional[str] = None  # new canonical name (was texto_tag)
    expected_points: Optional[int] = None
    stabilization_time_s: Optional[str] = ""
    created_at: float = field(default_factory=time.time)

    # Mapping-like access for compatibility with existing dict-based code:

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunRecord":
        return cls(
            id=data.get("id", 0),
            kind=data.get("kind", ""),
            label=data.get("label", ""),
            curve_tag=data.get("curve_tag", ""),
            measurements=(data.get("measurements") or []),
            peak=data.get("peak"),
            peaks=(data.get("peaks") or []),
            csv_filename=data.get("csv_filename"),
            row_tag=data.get("row_tag"),
            text_tag=data.get("texto_tag") or data.get("text_tag"),
            expected_points=data.get("expected_points"),
            stabilization_time_s=data.get("stabilization_time_s", ""),
        )
