from __future__ import annotations

import json
import os
from collections import deque

import dearpygui.dearpygui as dpg
import serial.tools.list_ports

from app.errors import OPERATION_ERRORS
from app.models import (
    MeasurementSession,
    RunRecord,
    RunStatus,
    SessionKind,
    SessionStatus,
    SweepProtocol,
)
from app.operation_state import OperationState
from app.run_history import RunHistory
from app.run_io import export_run_csv, import_run_csv
from app.run_naming import run_filename
from app.run_processing import (
    average_runs,
    averageable_runs,
    format_peak_summary,
    subtract_reference,
)
from app.run_repository import RunRepository
from experiments.voltage_sweep import BatchProgress, MeasurementPoint
from gui.plot_view import update_curve
from gui.themes import DANGER_THEME, create_button_themes, set_connection_button_visual
from storage.image_plot import export_run_plot_png


class ControlInterface:
    """
    Recibe un controlador de aplicación
    y solamente solicita acciones.
    """

    # Rango fijo del eje horizontal del gráfico (mm)
    X_AXIS_MIN = 0
    X_AXIS_MAX = 12

    # Carpeta donde se escriben los CSV que el controlador genera durante
    # una corrida en curso (registro en vivo). El guardado que el usuario
    # controla explícitamente ocurre por separado, desde el botón
    # "Guardar" de cada fila del historial.
    RUNS_DIR = "runs"
    DATABASE_PATH = os.path.join(RUNS_DIR, "refractometro.sqlite3")

    # Botones que disparan operaciones de hardware bloqueantes/largas.
    # Se deshabilitan mientras una operación está en curso para evitar
    # solicitudes superpuestas (p. ej. iniciar un barrido mientras otro
    # sigue corriendo, o mover el motor a mitad de una calibración).
    OPERATION_BUTTONS = (
        "barrido_btn",
        "calibrar_btn",
        "mover_btn",
    )

    def __init__(
        self,
        controller,
        repository: RunRepository | None = None,
    ):
        self.controller = controller
        self._repository = repository or RunRepository(self.DATABASE_PATH)
        self._owns_repository = repository is None

        # Track device connection state so operation buttons are only enabled
        # when both sensor and motor are connected.
        self._operation_state = OperationState()

        # deque con límite: evita reconstruir la lista completa de líneas
        # (splitlines + join) en cada llamada a log().
        self._log_lines: deque[str] = deque(maxlen=300)

        # Historial de corridas (barrido / calibración / corregido). Cada
        # una queda como su propia curva en el gráfico.
        self._run_history = RunHistory(repository=self._repository)

        # Corrida seleccionada para guardar, mientras el diálogo de
        # guardado está abierto.
        self._run_a_guardar: RunRecord | None = None

        # Corrida seleccionada para corregir, mientras el modal de
        # selección de blanco está abierto.
        self._run_a_corregir: RunRecord | None = None

        # Estado transitorio de la adquisición de un lote. Las corridas y la
        # sesión se persisten inmediatamente; estos mapas solo conectan los
        # callbacks del controlador con las curvas mostradas en vivo.
        self._active_batch_session: MeasurementSession | None = None
        self._batch_runs: dict[int, RunRecord] = {}

    # Helpers
    def log(
        self,
        message: str,
    ) -> None:
        self._log_lines.append(message)

        dpg.set_value(
            "registro",
            "\n".join(self._log_lines),
        )

    def _set_operation_buttons_enabled(self, enabled: bool) -> None:
        for tag in self.OPERATION_BUTTONS:
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, enabled=enabled)

    def _set_cancel_button_enabled(self, enabled: bool) -> None:
        if dpg.does_item_exist("cancelar_btn"):
            dpg.configure_item("cancelar_btn", enabled=enabled)

    def toggle_plot_legend(self, sender, value, user_data) -> None:
        if dpg.does_item_exist("plot_legend"):
            dpg.configure_item("plot_legend", show=value)

    def _set_run_buttons_enabled(self, run_id: int, enabled: bool) -> None:
        # Configure the buttons of a history row (do not touch peak labels here).
        tags = [
            f"hist_guardar_{run_id}",
            f"hist_corregir_{run_id}",
            f"hist_eliminar_{run_id}",
            f"hist_peaks_{run_id}",
            f"hist_exportar_{run_id}",
        ]
        for tag in tags:
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, enabled=enabled)

    def _set_failed_run_buttons_state(self, run: RunRecord) -> None:
        """Leave a failed run removable and enable data actions only when useful."""
        has_measurements = bool(run.measurements)
        states = {
            f"hist_guardar_{run.id}": has_measurements,
            f"hist_corregir_{run.id}": has_measurements,
            f"hist_peaks_{run.id}": has_measurements,
            f"hist_exportar_{run.id}": has_measurements,
            f"hist_eliminar_{run.id}": True,
        }

        for tag, enabled in states.items():
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, enabled=enabled)

    def _update_operation_buttons_state(self) -> None:
        """
        Enable operation buttons only when both sensor and motor are connected.
        Call whenever connection state changes.
        """
        enabled = (
            self._operation_state.operations_enabled
            and self._run_history.active_run is None
            and not self.controller.sweep_running
        )
        self._set_operation_buttons_enabled(enabled)
        self._set_cancel_button_enabled(self.controller.sweep_running)

    # Historial de corridas
    def create_live_run(
        self,
        kind: str,
        label: str,
        *,
        set_active: bool = True,
    ) -> RunRecord:
        """Crea una nueva corrida EN VIVO: reserva un id, agrega su curva
        vacía al gráfico y una fila en el panel de historial. Queda como
        la corrida activa hasta que termine o falle; los callbacks de
        progreso van llenando measurements/curva a medida que llegan.
        """

        run_id = self._run_history.reserve_id()

        curve_tag = f"curva_{kind}_{run_id}"

        dpg.add_line_series(
            [],
            [],
            label=label,
            parent="voltage_axis",
            tag=curve_tag,
        )

        # create empty scatter series for visualizing peaks for this run
        peaks_tag = f"peaks_{run_id}"
        dpg.add_scatter_series(
            [],
            [],
            label=f"{label} peaks",
            parent="voltage_axis",
            tag=peaks_tag,
        )

        run = self.register_run(run_id, kind, label, curve_tag)
        run.measurements = []
        run.laser_on_time_s = self.controller.laser_on_time_s
        self._run_history.save(run)

        if set_active:
            self._run_history.set_active(run)

        return run

    def create_computed_run(
        self,
        kind: str,
        label: str,
        measurements: list[MeasurementPoint],
        source_uids: list[str] | None = None,
        analysis_kind: str | None = None,
        analysis_parameters: dict[str, object] | None = None,
    ) -> RunRecord:
        """Crea una corrida ya resuelta (p. ej. el resultado de restar un
        blanco a otra corrida): la curva se dibuja de una sola vez con
        los datos ya calculados, sin pasar por el mecanismo de
        progreso/corrida activa.
        """

        run_id = self._run_history.reserve_id()

        curve_tag = f"curva_{kind}_{run_id}"

        dpg.add_line_series(
            [m.position_mm for m in measurements],
            [m.voltage_v for m in measurements],
            label=label,
            parent="voltage_axis",
            tag=curve_tag,
        )

        # create empty scatter series for visualizing peaks for this run
        peaks_tag = f"peaks_{run_id}"
        dpg.add_scatter_series(
            [],
            [],
            label=f"{label} peaks",
            parent="voltage_axis",
            tag=peaks_tag,
        )

        run = self.register_run(
            run_id,
            kind,
            label,
            curve_tag,
            source_uids=source_uids,
            analysis_kind=analysis_kind,
            analysis_parameters=analysis_parameters,
        )
        run.measurements = measurements
        run.laser_on_time_s = self.controller.laser_on_time_s
        run.status = RunStatus.COMPLETED
        self._run_history.save(run)

        # Ensure peaks button is enabled for this precomputed run
        peaks_btn_tag = f"hist_peaks_{run_id}"
        if dpg.does_item_exist(peaks_btn_tag):
            dpg.configure_item(peaks_btn_tag, enabled=bool(measurements))

        # Precompute peaks for this computed run and populate the scatter + tooltip
        try:
            peaks = self.controller.sweep.find_peaks(measurements)
            run.peaks = peaks

            xs = [p.position_mm for p in peaks]
            ys = [p.voltage_v for p in peaks]

            if dpg.does_item_exist(peaks_tag):
                dpg.set_value(peaks_tag, [xs, ys])
                dpg.configure_item(peaks_tag, show=bool(peaks))

            # update history peaks label for this run
            peaks_label_tag = f"hist_peaks_text_{run_id}"
            if dpg.does_item_exist(peaks_label_tag):
                dpg.set_value(peaks_label_tag, format_peak_summary(peaks))
        except (ValueError, IndexError, KeyError, RuntimeError) as exc:
            # best-effort: don't break UI if peak finding fails; record for debugging
            self.log(f"[PEAKS ERROR] {exc}")

        self.update_history_text(run)
        return run

    def restore_persisted_runs(self) -> None:
        """Recreate graph series and history rows loaded from SQLite."""
        for run in self._run_history.runs:
            dpg.add_line_series(
                [m.position_mm for m in run.measurements],
                [m.voltage_v for m in run.measurements],
                label=run.label,
                parent="voltage_axis",
                tag=run.curve_tag,
            )
            dpg.add_scatter_series(
                [],
                [],
                label=f"{run.label} peaks",
                parent="voltage_axis",
                tag=f"peaks_{run.id}",
            )
            self.add_history_row(run)

            if not run.measurements:
                self.update_history_text(run)
                continue

            try:
                run.peaks = self.controller.sweep.find_peaks(run.measurements)
            except (ValueError, IndexError, RuntimeError) as exc:
                self.log(f"[PEAKS ERROR] {exc}")
                continue

            peaks_tag = f"peaks_{run.id}"
            dpg.set_value(
                peaks_tag,
                [
                    [peak.position_mm for peak in run.peaks],
                    [peak.voltage_v for peak in run.peaks],
                ],
            )
            dpg.configure_item(peaks_tag, show=bool(run.peaks))
            dpg.set_value(
                f"hist_peaks_text_{run.id}",
                format_peak_summary(run.peaks),
            )
            self.update_history_text(run)

    def register_run(
        self,
        run_id: int,
        kind: str,
        label: str,
        curve_tag: str,
        source_uids: list[str] | None = None,
        analysis_kind: str | None = None,
        analysis_parameters: dict[str, object] | None = None,
    ) -> RunRecord:
        run = self._run_history.create_run(
            run_id=run_id,
            kind=kind,
            label=label,
            curve_tag=curve_tag,
            source_uids=source_uids,
            analysis_kind=analysis_kind,
            analysis_parameters=analysis_parameters,
        )

        self.add_history_row(run)

        return run

    def add_history_row(self, run: RunRecord) -> None:
        with dpg.group(tag=run.row_tag, parent="historial_lista"):
            # Top row: checkbox + run label
            with dpg.group(horizontal=True):
                dpg.add_checkbox(
                    label="Mostrar",
                    default_value=True,
                    callback=self.toggle_run_visibility,
                    user_data=run.id,
                )

                dpg.add_text(
                    run.label,
                    tag=run.text_tag,
                )

            dpg.add_text(
                "",
                tag=f"hist_peaks_text_{run.id}",
            )
            dpg.add_text(
                "",
                tag=f"hist_laser_text_{run.id}",
            )

            # Buttons row (horizontal)
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Guardar",
                    tag=f"hist_guardar_{run.id}",
                    callback=self.on_click_save_run,
                    user_data=run.id,
                    width=70,
                )

                dpg.add_button(
                    label="Corregir",
                    tag=f"hist_corregir_{run.id}",
                    callback=self.on_click_correct_run,
                    user_data=run.id,
                    width=70,
                )

                dpg.add_button(
                    label="Picos",
                    tag=f"hist_peaks_{run.id}",
                    callback=self.on_click_peaks,
                    user_data=run.id,
                    width=60,
                )

                dpg.add_button(
                    label="Exportar",
                    tag=f"hist_exportar_{run.id}",
                    callback=self.on_click_export_run,
                    user_data=run.id,
                    width=60,
                )

                dpg.add_button(
                    label="X",
                    tag=f"hist_eliminar_{run.id}",
                    callback=self.on_click_delete_run,
                    user_data=run.id,
                    width=30,
                )

            # Ensure peaks button is enabled only if the run already has measurements
            peaks_tag = f"hist_peaks_{run.id}"
            if dpg.does_item_exist(peaks_tag):
                dpg.configure_item(peaks_tag, enabled=bool(run.measurements))

            dpg.add_separator()

    def update_history_text(self, run: RunRecord) -> None:
        status_suffix = {
            RunStatus.PENDING: " (pendiente)",
            RunStatus.RUNNING: " (en curso)",
            RunStatus.FAILED: " (fallida)",
            RunStatus.CANCELLED: " (cancelada)",
            RunStatus.INTERRUPTED: " (interrumpida)",
        }.get(run.status, "")
        texto = run.label + status_suffix

        if run.peaks:
            peak = run.peaks[0]
            texto += f" — pico {peak.voltage_v:.4f}V" f" @ {peak.position_mm:.2f}mm"

        if dpg.does_item_exist(run.text_tag):
            dpg.set_value(run.text_tag, texto)

        laser_text = ""
        if run.laser_on_time_s is not None:
            laser_text = f"Láser encendido: {run.laser_on_time_s:.2f}s"
        laser_tag = f"hist_laser_text_{run.id}"
        if dpg.does_item_exist(laser_tag):
            dpg.set_value(laser_tag, laser_text)

    def toggle_run_visibility(self, sender, value, user_data) -> None:
        run = self._run_history.get(user_data)

        if run is None:
            return

        # show/hide the curve and the peaks markers
        if dpg.does_item_exist(run.curve_tag):
            dpg.configure_item(run.curve_tag, show=value)

        peaks_tag = f"peaks_{run.id}"
        if dpg.does_item_exist(peaks_tag):
            dpg.configure_item(peaks_tag, show=value)

        # Manage tooltip text for peaks: clear when hiding, restore when showing
        tooltip_tag = f"{peaks_tag}_tooltip_text"
        if not dpg.does_item_exist(tooltip_tag):
            return

        try:
            if not value:
                # hide/clear tooltip when the series is hidden
                dpg.set_value(tooltip_tag, "")
            else:
                # restore tooltip content from stored peaks if present
                peaks = (run.peaks if run is not None else []) or []
                if peaks:
                    tooltip_lines = [
                        f"{idx}. {p.voltage_v:.4f} V @ {p.position_mm:.4f} mm"
                        for idx, p in enumerate(peaks[:10], start=1)
                    ]
                    dpg.set_value(tooltip_tag, "\n".join(tooltip_lines))
                else:
                    dpg.set_value(tooltip_tag, "")
        except RuntimeError as exc:
            # best-effort UI update; don't crash on tooltip failures — log for debugging
            self.log(f"[TOOLTIP ERROR] {exc}")

    def delete_run(self, run: RunRecord) -> None:
        if dpg.does_item_exist(run.curve_tag):
            dpg.delete_item(run.curve_tag)

        # remove peaks series if present
        peaks_tag = f"peaks_{run.id}"
        if dpg.does_item_exist(peaks_tag):
            dpg.delete_item(peaks_tag)

        if dpg.does_item_exist(run.row_tag):
            dpg.delete_item(run.row_tag)

        self._run_history.remove(run)

    def on_click_export_run(self, sender, app_data, user_data) -> None:
        run = self._run_history.get(user_data)

        if run is None:
            return

        if not run.measurements:
            self.log("[EXPORT] No hay mediciones para exportar")
            return

        # Computed runs (averages and corrections) do not have a CSV path yet.
        # Give their PNG export a stable default destination instead of
        # rejecting the export just because the user has not used "Guardar".
        if not run.filename:
            run.filename = os.path.join(
                self.RUNS_DIR,
                run_filename(run.kind, run.created_at, run.uid),
            )
            self._run_history.save(run)

        if export_run_plot_png(run):
            self.log(f"[EXPORT] {run.filename} exportado como png")
        else:
            self.log("[EXPORT] Error al exportar")

    def on_click_delete_run(self, sender, app_data, user_data) -> None:
        run = self._run_history.get(user_data)

        if run is None:
            return

        if self._run_history.active_run is run:
            self.log("[HISTORIAL] No se puede eliminar una corrida en curso")
            return

        self.delete_run(run)

    def on_click_peaks(self, sender, app_data, user_data) -> None:
        """
        Toggle plot markers for peaks for the selected run. The per-run
        history label shows the peak summary and remains unchanged by the toggle.
        """

        run = self._run_history.get(user_data)
        if run is None:
            return

        peaks_tag = f"peaks_{run.id}"
        peaks_label_tag = f"hist_peaks_text_{run.id}"

        # Determine current visibility of the peaks series
        visible = False
        if dpg.does_item_exist(peaks_tag):
            try:
                cfg = dpg.get_item_configuration(peaks_tag)
                visible = bool(cfg.get("show", True))
            except (RuntimeError, KeyError) as exc:
                # If we can't read configuration, assume visible and log for debugging.
                self.log(
                    f"[PEAKS ERROR] No se puede leer la visibilidad de los picos: {exc}"
                )
                visible = True

        if visible:
            # hide markers only
            if dpg.does_item_exist(peaks_tag):
                try:
                    dpg.configure_item(peaks_tag, show=False)
                except RuntimeError as exc:
                    self.log(f"[PEAKS ERROR] {exc}")
            self.log(f"[PEAKS] Ocultados picos de {run.label}")
            return

        # show markers: ensure measurements exist
        measurements = run.measurements
        if not measurements:
            self.log("[PEAKS] Esa corrida no tiene mediciones para calcular picos")
            return

        # Use precomputed peaks if present, otherwise compute them now.
        peaks = run.peaks or []
        if not peaks:
            try:
                peaks = self.controller.sweep.find_peaks(measurements)
            except (ValueError, IndexError, RuntimeError) as exc:
                self.log(f"[PEAKS ERROR] {exc}")
                return
            run.peaks = peaks

            # update history label because we just computed peaks
            if dpg.does_item_exist(peaks_label_tag):
                dpg.set_value(peaks_label_tag, format_peak_summary(peaks))

        # Update/create scatter series and show it
        xs = [p.position_mm for p in peaks]
        ys = [p.voltage_v for p in peaks]
        if dpg.does_item_exist(peaks_tag):
            try:
                dpg.set_value(peaks_tag, [xs, ys])
                dpg.configure_item(peaks_tag, show=bool(peaks))
            except RuntimeError as exc:
                self.log(f"[PEAKS ERROR] {exc}")
                try:
                    dpg.delete_item(peaks_tag)
                except RuntimeError as exc2:
                    self.log(f"[PEAKS ERROR] {exc2}")
                if peaks:
                    dpg.add_scatter_series(
                        xs,
                        ys,
                        label=f"{run.label} peaks",
                        parent="voltage_axis",
                        tag=peaks_tag,
                    )
        else:
            if peaks:
                dpg.add_scatter_series(
                    xs,
                    ys,
                    label=f"{run.label} peaks",
                    parent="voltage_axis",
                    tag=peaks_tag,
                )

        # Update history main label (shows primary peak)
        self.update_history_text(run)

        self.log(f"[PEAKS] Calculados/mostrados {len(peaks)} picos para {run.label}")

    def _run_curve_is_visible(self, run: RunRecord) -> bool:
        if not dpg.does_item_exist(run.curve_tag):
            return True
        try:
            return bool(dpg.get_item_configuration(run.curve_tag).get("show", True))
        except (KeyError, RuntimeError):
            return True

    def average_completed_runs(self) -> None:
        runs = [
            run
            for run in averageable_runs(self._run_history.runs)
            if run is not self._run_history.active_run
            and self._run_curve_is_visible(run)
        ]

        if len(runs) < 2:
            self.log("[PROMEDIO] Se necesitan al menos dos corridas visibles completas")
            self._update_operation_buttons_state()
            return

        try:
            measurements = average_runs(runs)
            averaged = self.create_computed_run(
                "promedio",
                f"Promedio #{self._run_history.next_id} ({len(runs)} corridas)",
                measurements,
                source_uids=[run.uid for run in runs],
                analysis_kind="average",
                analysis_parameters={
                    "interpolation": "linear",
                    "source_count": len(runs),
                },
            )
        except (ValueError, RuntimeError) as exc:
            self.log(f"[PROMEDIO ERROR] {exc}")
            return
        finally:
            # A failed analysis must not leave the hardware controls disabled.
            self._update_operation_buttons_state()

        self.log(f"[PROMEDIO] {averaged.label} calculado")

    def clear_history(self) -> None:
        if self._run_history.active_run is not None:
            self.log(
                "[HISTORIAL] No se puede limpiar mientras hay una " "corrida en curso"
            )
            return

        for run in self._run_history.runs:
            self.delete_run(run)

        dpg.set_value("resultado_maximo", "")

    # Guardado individual
    def on_click_save_run(self, sender, app_data, user_data) -> None:
        run = self._run_history.get(user_data)

        if run is None:
            return

        self._run_a_guardar = run

        # Los barridos ya quedan guardados automáticamente por el
        # controlador en runs/barrido_<id>.csv (ver iniciar_barrido);
        # se usa el mismo nombre como sugerencia acá para no terminar
        # con dos archivos distintos para la misma corrida, a menos que
        # el usuario elija explícitamente otro nombre o carpeta.
        filename = run.filename

        if filename:
            nombre_sugerido = os.path.splitext(os.path.basename(filename))[0]
        else:
            nombre_sugerido = os.path.splitext(
                run_filename(run.kind, run.created_at, run.uid)
            )[0]

        dpg.configure_item(
            "guardar_historial_dialog",
            default_filename=nombre_sugerido,
        )

        dpg.show_item("guardar_historial_dialog")

    def file_picker_save_history(self, sender, file_data) -> None:
        run = self._run_a_guardar
        self._run_a_guardar = None

        if run is None:
            return

        path = file_data["file_path_name"]

        if not path.lower().endswith(".csv"):
            path += ".csv"

        try:
            export_run_csv(run, path)
            self._run_history.save(run)
            self.log(f"[HISTORIAL] Guardado: {path}")

        except OSError as exc:
            self.log(f"[HISTORIAL ERROR] {exc}")

    def file_picker_import(self, sender, file_data) -> None:
        if not file_data:
            return

        for name, path in file_data["selections"].items():
            # print(f"{name} -> {path}")

            try:
                measurements, metadata = import_run_csv(path)
            except (OSError, ValueError, TypeError) as exc:
                self.log(f"[IMPORT ERROR] {exc}")
                return

            kind = "importado"
            try:
                source_uids = json.loads(metadata.get("source_uids", "[]"))
            except (TypeError, ValueError):
                source_uids = []
            if not isinstance(source_uids, list) or not all(
                isinstance(uid, str) for uid in source_uids
            ):
                source_uids = []
            try:
                analysis_parameters = json.loads(
                    metadata.get("analysis_parameters", "{}")
                )
            except (TypeError, ValueError):
                analysis_parameters = {}
            if not isinstance(analysis_parameters, dict):
                analysis_parameters = {}

            nuevo = self.create_computed_run(
                kind,
                f"Importado: {name}",
                measurements,
                source_uids=source_uids,
                analysis_kind=metadata.get("analysis_kind") or None,
                analysis_parameters=analysis_parameters,
            )

            # Keep the imported CSV path for future exports and plot generation.
            nuevo.filename = path

            # copy stabilization time (and keep any other useful metadata if present)
            nuevo.stabilization_time_s = metadata.get("stabilization_time_s", "")
            laser_time = metadata.get("laser_on_time_s", "")
            try:
                nuevo.laser_on_time_s = float(laser_time) if laser_time else None
            except ValueError:
                nuevo.laser_on_time_s = None
            self._run_history.save(nuevo)

            self.log(f"[IMPORT] {path} importado como {nuevo.label}")

    # Corrección por sustracción de blanco
    def on_click_correct_run(self, sender, app_data, user_data) -> None:
        run = self._run_history.get(user_data)

        if run is None:
            return

        if not run.measurements:
            self.log("[CORRECCIÓN] Esa corrida todavía no tiene mediciones")
            return

        opciones = [
            r.label
            for r in self._run_history.runs
            if (
                r.id != run.id
                and r is not self._run_history.active_run
                and r.measurements
            )
        ]

        if not opciones:
            self.log(
                "[CORRECCIÓN] No hay otra corrida disponible como "
                "referencia (blanco sin muestra)"
            )
            return

        self._run_a_corregir = run

        dpg.configure_item("combo_blanco", items=opciones)
        dpg.set_value("combo_blanco", opciones[0])

        dpg.set_value(
            "texto_corregir",
            f"Corrida a corregir: {run.label}",
        )

        dpg.show_item("modal_corregir")

    def cancel_correction(self) -> None:
        self._run_a_corregir = None
        dpg.hide_item("modal_corregir")

    def apply_correction(self, sender, app_data) -> None:
        run = self._run_a_corregir
        self._run_a_corregir = None

        dpg.hide_item("modal_corregir")

        if run is None:
            return

        etiqueta_blanco = dpg.get_value("combo_blanco")

        blanco = next(
            (r for r in self._run_history.runs if r.label == etiqueta_blanco),
            None,
        )

        if blanco is None:
            self.log(
                "[CORRECCIÓN ERROR] No se encontró la corrida de " "referencia elegida"
            )
            return

        try:
            corregidos = subtract_reference(run, blanco)

        except (ValueError, IndexError, RuntimeError) as exc:
            self.log(f"[CORRECCIÓN ERROR] {exc}")
            return

        nuevo = self.create_computed_run(
            "corregido",
            f"Corregido #{self._run_history.next_id}: {run.label} − {blanco.label}",
            corregidos,
            source_uids=[run.uid, blanco.uid],
            analysis_kind="reference_subtraction",
            analysis_parameters={"interpolation": "linear"},
        )

        self.log(f"[CORRECCIÓN] {nuevo.label} calculado")

    def update_ports(
        self,
    ) -> None:
        ports = [port.device for port in serial.tools.list_ports.comports()]

        if not ports:
            ports = ["Sin puertos"]
            self.log("[PUERTOS] No se encontraron puertos seriales")
        else:
            self.log(f"[PUERTOS] Encontrados: {', '.join(ports)}")

        dpg.configure_item(
            "puerto_esp32",
            items=ports,
        )

        dpg.configure_item(
            "puerto_motor",
            items=ports,
        )

    # Callbacks ESP32
    def connect_sensor(self):
        try:
            self.controller.connect_sensor(
                dpg.get_value("puerto_esp32"),
                dpg.get_value("baudrate"),
            )

            dpg.set_value("estado_esp32", "Conectado")
            set_connection_button_visual(
                "conectar_esp32_btn",
                True,
                "Conectado",
                "Conectar",
            )
            self._operation_state.sensor_connected = True
            self._update_operation_buttons_state()

            self.log("[ESP32] Conectado")

        except OPERATION_ERRORS as exc:
            # Ensure flag is false on failure and update buttons
            self._operation_state.sensor_connected = False
            self._update_operation_buttons_state()
            dpg.set_value("estado_esp32", "Desconectado")
            set_connection_button_visual(
                "conectar_esp32_btn",
                False,
                "Conectado",
                "Conectar",
            )
            self.log(f"[ESP32 ERROR] {exc}")

    # Callbacks motor
    def connect_motor(self):
        try:
            self.controller.connect_motor(dpg.get_value("puerto_motor"))

            dpg.set_value("estado_motor", "Conectado")
            set_connection_button_visual(
                "conectar_motor_btn",
                True,
                "Motor conectado",
                "Conectar motor",
            )
            self._operation_state.motor_connected = True
            self._update_operation_buttons_state()

            self.log("[MOTOR] Conectado")

        except OPERATION_ERRORS as exc:
            # Ensure flag is false on failure and update buttons
            self._operation_state.motor_connected = False
            self._update_operation_buttons_state()
            dpg.set_value("estado_motor", "Desconectado")
            set_connection_button_visual(
                "conectar_motor_btn",
                False,
                "Motor conectado",
                "Conectar motor",
            )
            self.log(f"[MOTOR ERROR] {exc}")

    def move_motor(
        self,
    ):
        try:
            self._set_operation_buttons_enabled(False)

            self.controller.move_motor(dpg.get_value("posicion_objetivo"))

            self.log("[MOTOR] Movimiento completado")

        except OPERATION_ERRORS as exc:
            self.log(f"[MOTOR ERROR] {exc}")

        finally:
            self._update_operation_buttons_state()

    # Barrido
    def start_batch(self, session_kind: SessionKind) -> None:
        """Start a repeated sample or blank acquisition as a v3 session."""
        if self._run_history.active_run is not None or self.controller.sweep_running:
            self.log("[LOTE] Ya hay una operación en curso")
            return

        number_of_runs = dpg.get_value("cantidad_barridos")
        number_of_points = dpg.get_value("cantidad_puntos")
        if number_of_runs < 2 or number_of_points < 2:
            self.log("[LOTE ERROR] Un lote necesita al menos dos barridos y puntos")
            return

        session = None
        batch_runs: dict[int, RunRecord] = {}
        try:
            self._set_operation_buttons_enabled(False)
            protocol = SweepProtocol(
                start_position_mm=dpg.get_value("posicion_inicio"),
                end_position_mm=dpg.get_value("posicion_final"),
                number_of_points=number_of_points,
                stabilization_time_s=dpg.get_value("tiempo_estabilizacion"),
            )
            purpose = "Blanco" if session_kind is SessionKind.CALIBRATION else "Muestra"
            session = MeasurementSession(
                label=f"{purpose} lote",
                kind=session_kind,
                expected_runs=number_of_runs,
            )
            session.set_sweep_protocol(protocol)
            self._repository.save_session(session)
            session.transition_to(SessionStatus.ACQUIRING)
            self._repository.save_session(session)

            os.makedirs(self.RUNS_DIR, exist_ok=True)
            for run_number in range(1, number_of_runs + 1):
                run = self.create_live_run(
                    "barrido",
                    f"{purpose} {session.uid[:8]} — barrido {run_number}/{number_of_runs}",
                    set_active=False,
                )
                run.filename = os.path.join(
                    self.RUNS_DIR,
                    run_filename(run.kind, run.created_at, run.uid),
                )
                run.expected_points = number_of_points
                run.stabilization_time_s = protocol.stabilization_time_s
                run.status = RunStatus.PENDING
                self._run_history.save(run)
                self._repository.attach_run_to_session(run, session)
                batch_runs[run_number] = run
                self._set_run_buttons_enabled(run.id, False)

            self._repository.save_session(session)
            self._active_batch_session = session
            self._batch_runs = batch_runs
            dpg.set_value("resultado_maximo", "Adquiriendo lote...")
            dpg.set_value("barrido_progress", 0.0)
            dpg.set_value("lote_progress", 0.0)

            self.controller.start_voltage_batch(
                start_position_mm=protocol.start_position_mm,
                end_position_mm=protocol.end_position_mm,
                number_of_points=protocol.number_of_points,
                stabilization_time_s=protocol.stabilization_time_s,
                number_of_runs=number_of_runs,
                filename_factory=lambda run_number: batch_runs[run_number].filename
                or "",
                metadata={
                    "session_uid": session.uid,
                    "session_kind": session.kind.value,
                },
                on_progress=self.update_batch_sweep,
                on_run_finished=self.batch_run_finished,
                on_finished=self.batch_finished,
                on_error=self.batch_failed,
                on_cancelled=self.batch_cancelled,
            )
            self._update_operation_buttons_state()
            self.log(f"[LOTE] {purpose} iniciado ({number_of_runs} barridos)")
        except OPERATION_ERRORS as exc:
            self.log(f"[LOTE ERROR] {exc}")
            for run in batch_runs.values():
                self.delete_run(run)
            if session is not None and session.status is SessionStatus.ACQUIRING:
                session.transition_to(SessionStatus.CANCELLED)
                self._repository.save_session(session)
            self._active_batch_session = None
            self._batch_runs = {}
            self._update_operation_buttons_state()

    def update_batch_sweep(self, progress: BatchProgress) -> None:
        run = self._batch_runs.get(progress.run_number)
        if run is None:
            return

        with dpg.mutex():
            run.measurements = list(progress.measurements)
            run.status = RunStatus.RUNNING
            self._run_history.save(run)
            update_curve(run.curve_tag, run.measurements)
            current_progress = len(run.measurements) / (run.expected_points or 1)
            dpg.set_value("barrido_progress", min(1.0, current_progress))
            total_progress = (
                progress.run_number - 1 + current_progress
            ) / progress.total_runs
            dpg.set_value("lote_progress", min(1.0, total_progress))
            self.update_history_text(run)

    def batch_run_finished(
        self,
        run_number: int,
        measurements: list[MeasurementPoint],
    ) -> None:
        run = self._batch_runs.get(run_number)
        if run is None:
            return

        with dpg.mutex():
            run.measurements = list(measurements)
            run.peaks = self.controller.sweep.find_peaks(run.measurements)
            run.status = RunStatus.COMPLETED
            self._run_history.save(run)
            update_curve(run.curve_tag, run.measurements)

            peaks_tag = f"peaks_{run.id}"
            dpg.set_value(
                peaks_tag,
                [
                    [peak.position_mm for peak in run.peaks],
                    [peak.voltage_v for peak in run.peaks],
                ],
            )
            dpg.configure_item(peaks_tag, show=bool(run.peaks))
            dpg.set_value(
                f"hist_peaks_text_{run.id}",
                format_peak_summary(run.peaks),
            )
            self.update_history_text(run)
            self._set_run_buttons_enabled(run.id, True)

    def _finish_batch(self, status: SessionStatus, message: str) -> None:
        session = self._active_batch_session
        with dpg.mutex():
            for run in self._batch_runs.values():
                if run.status in {RunStatus.PENDING, RunStatus.RUNNING}:
                    run.status = (
                        RunStatus.CANCELLED
                        if status is SessionStatus.CANCELLED
                        else RunStatus.FAILED
                    )
                    self._run_history.save(run)
                    self.update_history_text(run)
                    self._set_failed_run_buttons_state(run)
            if session is not None and session.status is SessionStatus.ACQUIRING:
                session.transition_to(status)
                self._repository.save_session(session)
            dpg.set_value("resultado_maximo", "")
            self.log(message)
            self._active_batch_session = None
            self._batch_runs = {}
            self._update_operation_buttons_state()

    def batch_finished(self, _results: list[list[MeasurementPoint]]) -> None:
        self._finish_batch(SessionStatus.COMPLETED, "[LOTE] Finalizado")

    def batch_cancelled(self, _results: list[list[MeasurementPoint]]) -> None:
        self._finish_batch(SessionStatus.CANCELLED, "[LOTE] Cancelado")

    def batch_failed(
        self,
        exc: Exception,
        _partial_results: list[list[MeasurementPoint]],
    ) -> None:
        self._finish_batch(SessionStatus.FAILED, f"[LOTE ERROR] {exc}")

    def start_sweep(
        self,
    ):
        if dpg.get_value("cantidad_barridos") > 1:
            self.start_batch(SessionKind.SAMPLE)
            return

        if self._run_history.active_run is not None or self.controller.sweep_running:
            self.log("[BARRIDO] Ya hay una operación en curso")
            return

        cantidad_puntos = dpg.get_value("cantidad_puntos")

        if cantidad_puntos < 1:
            self.log("[BARRIDO ERROR] La cantidad de puntos debe ser mayor a 0")
            return

        run = None

        try:
            self._set_operation_buttons_enabled(False)

            dpg.set_value("resultado_maximo", "Midiendo...")

            run = self.create_live_run(
                "barrido",
                f"Barrido #{self._run_history.next_id} " f"({cantidad_puntos} pts)",
            )

            # start_voltage_sweep guarda a CSV incondicionalmente
            # (ver ApplicationController), así que esto es un respaldo
            # automático, no una elección del usuario. Se guarda la
            # ruta en el run para sugerirla como nombre por defecto si
            # el usuario después usa "Guardar" en el historial, en vez
            # de terminar con dos archivos distintos para la misma
            # corrida.
            os.makedirs(self.RUNS_DIR, exist_ok=True)
            filename = os.path.join(
                self.RUNS_DIR,
                run_filename(run.kind, run.created_at, run.uid),
            )
            run.filename = filename

            # store metadata needed to resume and inspect the run later
            run.stabilization_time_s = dpg.get_value("tiempo_estabilizacion")
            run.expected_points = cantidad_puntos
            run.status = RunStatus.RUNNING
            self._run_history.save(run)

            # disable row buttons while run is active
            self._set_run_buttons_enabled(run.id, False)

            self.controller.start_voltage_sweep(
                start_position_mm=dpg.get_value("posicion_inicio"),
                end_position_mm=dpg.get_value("posicion_final"),
                number_of_points=cantidad_puntos,
                stabilization_time_s=dpg.get_value("tiempo_estabilizacion"),
                filename=filename,
                on_progress=self.update_sweep,
                on_finished=self.show_peaks,
                on_error=self.sweep_failed,
                on_cancelled=self.sweep_cancelled,
            )

            self._update_operation_buttons_state()
            self.log("[BARRIDO] Iniciado")

        except OPERATION_ERRORS as exc:
            self.log(f"[BARRIDO ERROR] {exc}")

            if run is not None:
                self.delete_run(run)

            self._run_history.clear_active()
            self._update_operation_buttons_state()

    def update_sweep(
        self,
        measurements,
    ):
        if not measurements:
            return

        run = self._run_history.active_run

        if run is None:
            return

        # dpg.mutex() for thread safety with DearPyGui
        with dpg.mutex():
            run.measurements = list(measurements)

            # update curve
            update_curve(
                run.curve_tag,
                measurements,
            )

            # update progress bar
            expected = run.expected_points or len(measurements)
            if expected:
                progress = min(1.0, len(measurements) / expected)
                if dpg.does_item_exist("barrido_progress"):
                    dpg.set_value("barrido_progress", progress)

    def sweep_failed(self, exc: Exception) -> None:
        self.operation_failed("BARRIDO", exc)

    def calibration_failed(self, exc: Exception) -> None:
        self.operation_failed("CALIBRACIÓN", exc)

    def cancel_operation(self) -> None:
        if self.controller.cancel_operation():
            self.log("[OPERACIÓN] Cancelación solicitada")
        else:
            self.log("[OPERACIÓN] No hay una operación en curso")

    def sweep_cancelled(self, measurements: list[MeasurementPoint]) -> None:
        self.operation_cancelled("BARRIDO", measurements)

    def calibration_cancelled(self, measurements: list[MeasurementPoint]) -> None:
        self.operation_cancelled("CALIBRACIÓN", measurements)

    def operation_cancelled(
        self,
        operation: str,
        measurements: list[MeasurementPoint],
    ) -> None:
        run = self._run_history.active_run
        self._run_history.clear_active()

        with dpg.mutex():
            if run is not None:
                run.measurements = list(measurements)
                run.status = RunStatus.CANCELLED
                self._run_history.save(run)
                self.update_history_text(run)
                self._set_failed_run_buttons_state(run)

            if dpg.does_item_exist("resultado_maximo"):
                dpg.set_value("resultado_maximo", "")

            self.log(f"[{operation}] Cancelada")
            self._update_operation_buttons_state()

    def operation_failed(self, operation: str, exc: Exception) -> None:
        run = self._run_history.active_run
        self._run_history.clear_active()

        with dpg.mutex():
            if run is not None:
                run.status = RunStatus.FAILED
                self._run_history.save(run)
                self.update_history_text(run)
                self._set_failed_run_buttons_state(run)

            if dpg.does_item_exist("resultado_maximo"):
                dpg.set_value("resultado_maximo", "")

            self.log(f"[{operation} ERROR] {exc}")
            self._update_operation_buttons_state()

    def start_calibration(
        self,
    ):
        if dpg.get_value("cantidad_barridos") > 1:
            self.start_batch(SessionKind.CALIBRATION)
            return

        if self._run_history.active_run is not None or self.controller.sweep_running:
            self.log("[CALIBRACIÓN] Ya hay una operación en curso")
            return

        run = None

        try:
            self._set_operation_buttons_enabled(False)

            cantidad_puntos = dpg.get_value("cantidad_puntos")

            run = self.create_live_run(
                "calibracion",
                f"Calibración #{self._run_history.next_id} " f"({cantidad_puntos} pts)",
            )

            run.expected_points = cantidad_puntos

            # store stabilization time for this calibration run
            run.stabilization_time_s = dpg.get_value("tiempo_estabilizacion")
            run.status = RunStatus.RUNNING
            self._run_history.save(run)

            self._set_run_buttons_enabled(run.id, False)

            self.controller.start_calibration(
                start_position_mm=dpg.get_value("posicion_inicio"),
                end_position_mm=dpg.get_value("posicion_final"),
                number_of_points=cantidad_puntos,
                stabilization_time_s=dpg.get_value("tiempo_estabilizacion"),
                on_progress=self.update_sweep,
                on_finished=self.calibration_finished,
                on_error=self.calibration_failed,
                on_cancelled=self.calibration_cancelled,
            )

            self._update_operation_buttons_state()
            self.log("[CALIBRACIÓN] Iniciada")

        except OPERATION_ERRORS as exc:
            self.log(f"[CALIBRACIÓN ERROR] {exc}")

            if run is not None:
                self.delete_run(run)

            self._run_history.clear_active()
            self._update_operation_buttons_state()

    def calibration_finished(
        self,
        measurements,
    ):
        with dpg.mutex():
            run = self._run_history.active_run

            if run is not None:
                run.measurements = list(measurements)
                run.status = RunStatus.COMPLETED
                self._run_history.save(run)
                # enable row buttons once calibration finished
                self._set_run_buttons_enabled(run.id, True)

            self.log("[CALIBRACIÓN] Finalizada")

            self.log("[CALIBRACIÓN] " f"{len(measurements)} puntos almacenados")

        self._run_history.clear_active()
        self._update_operation_buttons_state()

    def show_peaks(
        self,
        peaks: list[MeasurementPoint],
    ) -> None:
        """
        Handle the end of a sweep: receives a list of peaks (possibly empty).
        Updates the active run's metadata, the history text and the result widget.
        """

        with dpg.mutex():
            run = self._run_history.active_run

            if run is not None:
                run.peaks = peaks
                run.status = RunStatus.COMPLETED
                self._run_history.save(run)
                # update peaks scatter series for this run
                peaks_tag = f"peaks_{run.id}"
                xs = [p.position_mm for p in peaks]
                ys = [p.voltage_v for p in peaks]
                if peaks:
                    if dpg.does_item_exist(peaks_tag):
                        dpg.set_value(peaks_tag, [xs, ys])
                        dpg.configure_item(peaks_tag, show=True)
                    else:
                        dpg.add_scatter_series(
                            xs,
                            ys,
                            label=f"{run.label} peaks",
                            parent="voltage_axis",
                            tag=peaks_tag,
                        )
                else:
                    # no peaks: clear/hide existing series if any
                    if dpg.does_item_exist(peaks_tag):
                        dpg.set_value(peaks_tag, [[], []])
                        dpg.configure_item(peaks_tag, show=False)

                # update history peaks label for this run
                peaks_label_tag = f"hist_peaks_text_{run.id}"
                if dpg.does_item_exist(peaks_label_tag):
                    dpg.set_value(peaks_label_tag, format_peak_summary(peaks))

                self.update_history_text(run)
                # enable row buttons now that run finished
                self._set_run_buttons_enabled(run.id, True)

            # Clear the big result box — per-run labels hold peak summaries now.
            dpg.set_value("resultado_maximo", "")

            self.log("[BARRIDO] Finalizado")

        self._run_history.clear_active()
        self._update_operation_buttons_state()

    # Construcción UI
    def build(self):
        dpg.create_context()
        create_button_themes()

        # self.crear_temas()

        dpg.create_viewport(
            title="Refractómetro",
            width=1400,
            height=900,
        )

        with dpg.file_dialog(
            show=False,
            tag="guardar_historial_dialog",
            label="Guardar corrida",
            callback=self.file_picker_save_history,
            width=700,
            height=400,
        ):
            dpg.add_file_extension(".csv")

        with dpg.file_dialog(
            show=False,
            tag="import_dialog",
            label="Importar corrida CSV",
            callback=self.file_picker_import,
            width=700,
            height=400,
        ):
            dpg.add_file_extension(".csv")

        with dpg.window(
            label="Corregir corrida",
            modal=True,
            show=False,
            tag="modal_corregir",
            width=420,
            height=180,
            no_resize=True,
        ):
            dpg.add_text(
                "",
                tag="texto_corregir",
            )

            dpg.add_text("Corrida de referencia (blanco, sin muestra):")

            dpg.add_listbox(
                tag="combo_blanco",
                items=[],
                num_items=4,
                width=-1,
            )

            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Aplicar",
                    callback=self.apply_correction,
                )

                dpg.add_button(
                    label="Cancelar",
                    callback=lambda: self.cancel_correction(),
                )

        with dpg.window(
            tag="ventana_principal",
            width=-1,
            height=-1,
            no_collapse=True,
        ):
            with dpg.group(horizontal=True):
                dpg.add_text("Refractómetro")

                dpg.add_button(
                    label="Actualizar puertos",
                    callback=self.update_ports,
                )

                dpg.add_button(
                    label="Importar CSV",
                    callback=lambda: dpg.show_item("import_dialog"),
                )

                info_btn = dpg.add_button(
                    tag="info_btn",
                    label="ℹ Ayuda",
                    callback=lambda: dpg.show_item("modal_info"),
                )

            with dpg.popup(
                info_btn,
                modal=True,
                tag="modal_info",
            ):
                dpg.add_text(
                    "Cómo usar el refractómetro:\n\n"
                    "1. Conectar el ESP32 (sensor) eligiendo su puerto\n"
                    "   y baudrate, luego 'Conectar'.\n"
                    "2. Conectar el motor Zaber eligiendo su puerto y\n"
                    "   presionando 'Conectar motor'.\n"
                    "3. Si los puertos no aparecen en las listas,\n"
                    "   usar 'Actualizar puertos' (arriba).\n"
                    "4. Definir Inicio, Final, Puntos y tiempo de\n"
                    "   Estabilización para el barrido.\n"
                    "5. '▶ Barrido' mide voltaje vs posición.\n"
                    "   '⚙ Calibrar' mide una corrida de referencia,\n"
                    "   por ejemplo con el portamuestras vacío.\n"
                    "6. Cada corrida queda en el Historial:\n"
                    "   - la casilla muestra/oculta su curva, para\n"
                    "     comparar varias mediciones a la vez;\n"
                    "   - 'Guardar' exporta esa corrida a CSV;\n"
                    "   - 'Corregir' resta una corrida de referencia\n"
                    "     (blanco) a la corrida elegida, punto a\n"
                    "     punto, y agrega el resultado como una nueva\n"
                    "     curva corregida;\n"
                    "   - '✕' elimina esa corrida del historial."
                )

                dpg.add_button(
                    label="Cerrar",
                    callback=lambda: dpg.hide_item("modal_info"),
                )

            with dpg.table(
                header_row=False,
                resizable=True,
                policy=dpg.mvTable_SizingStretchProp,
            ):
                dpg.add_table_column(init_width_or_weight=0.34)

                dpg.add_table_column(init_width_or_weight=0.66)

                with dpg.table_row():
                    with dpg.table_cell():
                        with dpg.collapsing_header(
                            label="ESP32",
                            default_open=True,
                        ):
                            dpg.add_text(
                                "● Desconectado",
                                tag="estado_esp32",
                            )

                            dpg.add_combo(
                                tag="puerto_esp32",
                                label="Puerto",
                                items=[],
                                width=-1,
                            )

                            dpg.add_input_int(
                                tag="baudrate",
                                label="Baudrate",
                                default_value=115200,
                                width=-1,
                            )

                            dpg.add_button(
                                tag="conectar_esp32_btn",
                                label="Conectar",
                                callback=self.connect_sensor,
                                width=-1,
                            )

                            dpg.add_separator()

                        with dpg.collapsing_header(
                            label="Motor Zaber",
                            default_open=True,
                        ):
                            dpg.add_text(
                                "● Desconectado",
                                tag="estado_motor",
                            )

                            dpg.add_combo(
                                tag="puerto_motor",
                                label="Puerto",
                                items=[],
                                width=-1,
                            )

                            dpg.add_button(
                                tag="conectar_motor_btn",
                                label="Conectar motor",
                                callback=self.connect_motor,
                                width=-1,
                            )

                            dpg.add_input_float(
                                tag="posicion_objetivo",
                                label="Posición objetivo (mm)",
                                min_value=self.X_AXIS_MIN,
                                max_value=self.X_AXIS_MAX,
                                min_clamped=True,
                                max_clamped=True,
                                width=-1,
                            )

                            dpg.add_button(
                                tag="mover_btn",
                                label="Mover",
                                callback=self.move_motor,
                                width=-1,
                            )

                        with dpg.collapsing_header(
                            label="Barrido",
                            default_open=True,
                        ):
                            with dpg.table(
                                header_row=False,
                                borders_innerH=False,
                                borders_outerH=False,
                                policy=dpg.mvTable_SizingStretchProp,
                            ):
                                dpg.add_table_column(init_width_or_weight=0.42)
                                dpg.add_table_column(init_width_or_weight=0.58)

                                with dpg.table_row():
                                    dpg.add_text("Inicio (mm)")
                                    dpg.add_input_float(
                                        tag="posicion_inicio",
                                        default_value=self.X_AXIS_MIN,
                                        min_value=self.X_AXIS_MIN,
                                        max_value=self.X_AXIS_MAX,
                                        min_clamped=True,
                                        max_clamped=True,
                                        width=-1,
                                    )

                                with dpg.table_row():
                                    dpg.add_text("Final (mm)")
                                    dpg.add_input_float(
                                        tag="posicion_final",
                                        default_value=self.X_AXIS_MAX,
                                        min_value=self.X_AXIS_MIN,
                                        max_value=self.X_AXIS_MAX,
                                        min_clamped=True,
                                        max_clamped=True,
                                        width=-1,
                                    )

                                with dpg.table_row():
                                    dpg.add_text("Puntos")
                                    dpg.add_input_int(
                                        tag="cantidad_puntos",
                                        default_value=50,
                                        min_value=1,
                                        min_clamped=True,
                                        width=-1,
                                    )

                                with dpg.table_row():
                                    dpg.add_text("Repeticiones")
                                    dpg.add_input_int(
                                        tag="cantidad_barridos",
                                        default_value=1,
                                        min_value=1,
                                        min_clamped=True,
                                        width=-1,
                                    )

                                with dpg.table_row():
                                    dpg.add_text("Estabilización (s)")
                                    dpg.add_input_float(
                                        tag="tiempo_estabilizacion",
                                        default_value=0.2,
                                        min_value=0.0,
                                        min_clamped=True,
                                        width=-1,
                                    )

                            with dpg.group(horizontal=True):
                                dpg.add_button(
                                    tag="barrido_btn",
                                    label="Barrido / lote",
                                    callback=self.start_sweep,
                                    width=150,
                                )

                                dpg.add_button(
                                    tag="calibrar_btn",
                                    label="Calibración / lote",
                                    callback=self.start_calibration,
                                    width=150,
                                )

                            dpg.add_button(
                                tag="cancelar_btn",
                                label="Cancelar",
                                callback=self.cancel_operation,
                                enabled=False,
                                width=-1,
                            )

                            dpg.add_progress_bar(
                                default_value=0.0,
                                tag="barrido_progress",
                                width=-1,
                            )
                            dpg.add_text("Progreso total del lote")
                            dpg.add_progress_bar(
                                default_value=0.0,
                                tag="lote_progress",
                                width=-1,
                            )

                            dpg.add_text(
                                "",
                                tag="resultado_maximo",
                            )

                        with dpg.collapsing_header(
                            label="Historial",
                            default_open=True,
                        ):
                            dpg.add_checkbox(
                                label="Mostrar leyenda de la gráfica",
                                default_value=True,
                                callback=self.toggle_plot_legend,
                            )

                            with dpg.child_window(
                                tag="historial_lista",
                                height=400,
                                border=True,
                            ):
                                pass

                            dpg.add_button(
                                label="Promediar selección",
                                callback=self.average_completed_runs,
                                width=-1,
                            )

                            dpg.add_button(
                                label="Limpiar historial",
                                callback=self.clear_history,
                                width=-1,
                            )

                    with dpg.table_cell():
                        with dpg.plot(
                            label="Voltaje vs Posición",
                            height=800,
                            width=-1,
                        ):
                            dpg.add_plot_legend(tag="plot_legend")

                            dpg.add_plot_axis(
                                dpg.mvXAxis,
                                label="Posición (mm)",
                                tag="position_axis",
                            )

                            # Las curvas de cada corrida se crean
                            # dinámicamente en _crear_run/
                            # _crear_run_calculado — no hay curvas fijas
                            # acá, así se pueden acumular y comparar
                            # varias corridas (y sus correcciones) en
                            # simultáneo.
                            dpg.add_plot_axis(
                                dpg.mvYAxis,
                                label="Voltaje (V)",
                                tag="voltage_axis",
                            )

                        with dpg.child_window(
                            height=200,
                            border=True,
                        ):
                            dpg.add_input_text(
                                tag="registro",
                                multiline=True,
                                readonly=True,
                                width=-1,
                                height=-1,
                            )

        set_connection_button_visual(
            "conectar_esp32_btn",
            False,
            "Conectado",
            "Conectar",
        )
        set_connection_button_visual(
            "conectar_motor_btn",
            False,
            "Motor conectado",
            "Conectar motor",
        )
        dpg.bind_item_theme("cancelar_btn", DANGER_THEME)

        dpg.setup_dearpygui()

        dpg.show_viewport()

        dpg.set_primary_window(
            "ventana_principal",
            True,
        )

        # Fija el eje horizontal a 0-12mm desde el arranque, en vez de
        # dejar que autoajuste a un rango vacío (lo que hacía que el
        # gráfico se viera diminuto antes de la primera medición).
        dpg.set_axis_limits(
            "position_axis",
            self.X_AXIS_MIN,
            self.X_AXIS_MAX,
        )

        # Fix Y axis to 0–3 V
        dpg.set_axis_limits(
            "voltage_axis",
            0.0,
            3.0,
        )

        # Restore persisted runs after the graph and history widgets exist.
        self.restore_persisted_runs()

        # Initialize operation buttons state
        # (they should be disabled until both devices connect)
        self._update_operation_buttons_state()

        self.update_ports()

    def run(self):
        while dpg.is_dearpygui_running():
            dpg.render_dearpygui_frame()

    def close(
        self,
    ):
        try:
            self.controller.disconnect_sensor()
            self._operation_state.sensor_connected = False
            set_connection_button_visual(
                "conectar_esp32_btn",
                False,
                "Conectado",
                "Conectar",
            )
            self._update_operation_buttons_state()
            self.log("[ESP32] Desconectado")
        except OPERATION_ERRORS as exc:
            self.log(f"[ESP32 ERROR] {exc}")

        if hasattr(self.controller, "disconnect_motor"):
            try:
                self.controller.disconnect_motor()
                self._operation_state.motor_connected = False
                set_connection_button_visual(
                    "conectar_motor_btn",
                    False,
                    "Motor conectado",
                    "Conectar motor",
                )
                self._update_operation_buttons_state()
                self.log("[MOTOR] Desconectado")
            except OPERATION_ERRORS as exc:
                self.log(f"[MOTOR ERROR] {exc}")

        dpg.destroy_context()
        if self._owns_repository:
            self._repository.close()
