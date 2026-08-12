from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Any, Dict
import time

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
    def __getitem__(self, key: str) -> Any:
        mapping = {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "curve_tag": self.curve_tag,
            "measurements": self.measurements,
            "peak": self.peak,
            "peaks": self.peaks,
            "csv_filename": self.csv_filename,
            "row_tag": self.row_tag,
            "texto_tag": self.text_tag,  # compatibility key
            "text_tag": self.text_tag,
            "expected_points": self.expected_points,
            "stabilization_time_s": self.stabilization_time_s,
        }
        return mapping.get(key)

    def __setitem__(self, key: str, value: Any) -> None:
        if key == "id":
            self.id = value
        elif key == "kind":
            self.kind = value
        elif key == "label":
            self.label = value
        elif key == "curve_tag":
            self.curve_tag = value
        elif key == "measurements":
            self.measurements = value
        elif key == "peak":
            self.peak = value
        elif key == "peaks":
            self.peaks = value
        elif key == "csv_filename":
            self.csv_filename = value
        elif key == "row_tag":
            self.row_tag = value
        elif key in ("texto_tag", "text_tag"):
            self.text_tag = value
        elif key == "expected_points":
            self.expected_points = value
        elif key == "stabilization_time_s":
            self.stabilization_time_s = value
        else:
            setattr(self, key, value)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # include legacy key name expected by existing code
        d["texto_tag"] = d.get("text_tag") or d.get("text_tag")
        return d

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
