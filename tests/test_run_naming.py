from __future__ import annotations

import re

from app.run_naming import run_filename


def test_run_filename_contains_start_time_and_uid():
    filename = run_filename("barrido", 0.0, "abcdef1234567890")

    assert re.fullmatch(
        r"barrido_\d{8}_\d{6}_\d{6}_abcdef12\.csv",
        filename,
    )
