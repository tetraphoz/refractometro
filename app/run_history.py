from __future__ import annotations

from collections.abc import Iterable

from app.models import RunRecord, RunStatus
from app.run_repository import RunRepository
from experiments.voltage_sweep import MeasurementPoint


class RunHistory:
    """Business-side storage for runs shown by the GUI.

    This class owns run ids, the ordered run list, lookup by id, and the notion
    of an active run. It intentionally does not import DearPyGui or touch UI
    widgets.
    """

    def __init__(self, repository: RunRepository | None = None) -> None:
        self._runs: list[RunRecord] = []
        self._by_id: dict[int, RunRecord] = {}
        self._by_uid: dict[str, RunRecord] = {}
        self._counter = 0
        self._active_run: RunRecord | None = None
        self._repository = repository

        if repository is not None:
            for run in repository.list_runs():
                self._add_in_memory(run)
                if run.status in {RunStatus.PENDING, RunStatus.RUNNING}:
                    run.status = RunStatus.INTERRUPTED
                    run.failure_reason = "Adquisición interrumpida al reiniciar"
                    repository.save(run)

    @property
    def counter(self) -> int:
        return self._counter

    @property
    def next_id(self) -> int:
        return self._counter + 1

    @property
    def runs(self) -> list[RunRecord]:
        return list(self._runs)

    @property
    def active_run(self) -> RunRecord | None:
        return self._active_run

    def reserve_id(self) -> int:
        self._counter += 1
        return self._counter

    def create_run(
        self,
        *,
        run_id: int,
        kind: str,
        label: str,
        curve_tag: str,
        measurements: Iterable[MeasurementPoint] | None = None,
        source_uids: Iterable[str] | None = None,
        analysis_kind: str | None = None,
        analysis_parameters: dict[str, object] | None = None,
    ) -> RunRecord:
        run = RunRecord(
            id=run_id,
            kind=kind,
            label=label,
            curve_tag=curve_tag,
            measurements=list(measurements) if measurements is not None else [],
            peaks=[],
            filename=None,
            status=RunStatus.PENDING,
            source_uids=list(source_uids) if source_uids is not None else [],
            analysis_kind=analysis_kind,
            analysis_parameters=analysis_parameters or {},
            row_tag=f"historial_fila_{run_id}",
            text_tag=f"historial_texto_{run_id}",
        )
        self.add(run)
        return run

    def add(self, run: RunRecord) -> None:
        if run.id in self._by_id:
            raise ValueError(f"Ya existe una corrida con id {run.id}")
        if run.uid in self._by_uid:
            raise ValueError(f"Ya existe una corrida con uid {run.uid}")

        self._add_in_memory(run)
        if self._repository is not None:
            self._repository.save(run)

    def save(self, run: RunRecord) -> None:
        """Persist changes made to a run already present in the history."""
        if self._by_id.get(run.id) is not run:
            raise ValueError(f"La corrida {run.id} no pertenece al historial")
        if self._repository is not None:
            self._repository.save(run)

    def _add_in_memory(self, run: RunRecord) -> None:
        run.row_tag = run.row_tag or f"historial_fila_{run.id}"
        run.text_tag = run.text_tag or f"historial_texto_{run.id}"
        self._runs.append(run)
        self._by_id[run.id] = run
        self._by_uid[run.uid] = run
        self._counter = max(self._counter, run.id)

    def get(self, run_id: int) -> RunRecord | None:
        return self._by_id.get(run_id)

    def get_by_uid(self, run_uid: str) -> RunRecord | None:
        """Return a run by its persistent provenance identifier."""
        return self._by_uid.get(run_uid)

    def set_active(self, run: RunRecord | None) -> None:
        self._active_run = run

    def clear_active(self, run: RunRecord | None = None) -> None:
        if run is None or self._active_run is run:
            self._active_run = None

    def remove(self, run: RunRecord) -> None:
        self._by_id.pop(run.id, None)
        self._by_uid.pop(run.uid, None)

        if run in self._runs:
            self._runs.remove(run)

        if self._repository is not None:
            self._repository.delete(run.id)

        self.clear_active(run)
