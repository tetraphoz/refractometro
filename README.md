Project title and short description
Refractometer GUI and data acquisition for a motorized refractometer. Provides:
- interactive GUI (DearPyGui) to control motor position and read a voltage sensor,
- sweep and calibration workflows,
- CSV import/export with per-file metadata,
- per-run history with peak extraction and plot markers,
- typed RunRecord model for history entries.

Requirements
- Python 3.13+
- Dependencies (install via pip): dearpygui, pyserial, zaber-motion
  Example:
    python -m pip install "dearpygui>=2.3.1" "pyserial>=3.5" "zaber-motion>=10.0.0"

Quick start (simulated hardware)
1. Run app using simulated hardware (no devices required):
    python main.py --test
2. Use the UI to run sweeps and calibrations, export/import CSVs, compute peaks.

Running with real hardware
- Connect your ESP32 device and Zaber motor ports in the UI.
- Use the "Actualizar puertos" button to refresh serial port lists.
- Press "Conectar" for the ESP32 and "Conectar motor" for the motor.
- When both devices are connected, sweep/calibrate buttons become enabled.

Project layout (important modules)
- gui/interface.py — DearPyGui interface and UI logic
- app/application.py — high-level application controller coordinating hardware and experiments
- app/models.py — RunRecord dataclass (history entries)
- experiments/ — measurement logic (VoltageSweep, CalibrationCurve)
- hardware/ — hardware drivers and simulated devices
- storage/csv.py — CSV import/export with metadata header

Development
- Run tests:
    pytest -q
- Format and lint (recommended pre-commit):
    pip install pre-commit black ruff isort
    pre-commit install
    pre-commit run --all-files
- If you use Nix, a dev shell is provided via flake.nix.

CSV metadata
- CSV files exported by the app include commented metadata header lines ("# key: value") that store run details (start/end position, number of points, stabilization time, label, kind, id). The import routine parses these metadata lines and provides sensible defaults when metadata is absent.

Next recommended improvements
- Add unit tests for VoltageSweep.find_peaks (edge cases: plateaus, endpoints) and for storage/csv import/export round-trips.
- Remove the RunRecord mapping-compatibility helpers once the codebase fully uses attribute access (run.field).
- Add a CI workflow (GitHub Actions) to run tests and linters on PRs.
- Consider a small UI test or integration test strategy for core workflows.

Contributing
- Create a feature branch, run linters and tests locally, and open a pull request.
- Coordinate with the maintainer before any git history rewrite; backups and force-pushes will disrupt collaborators.

License
- Add a LICENSE file (MIT recommended) if you intend to publish the project.

----
