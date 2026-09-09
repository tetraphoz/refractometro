from __future__ import annotations

from datetime import UTC, datetime


def run_filename(kind: str, started_at: float, uid: str) -> str:
    """Return a collision-resistant filename based on the run start time."""
    timestamp = datetime.fromtimestamp(
        started_at,
        tz=UTC,
    ).strftime("%Y%m%d_%H%M%S_%f")
    return f"{kind}_{timestamp}_{uid[:8]}.csv"
