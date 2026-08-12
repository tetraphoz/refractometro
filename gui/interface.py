from __future__ import annotations

import bisect
import os
from collections import deque

import dearpygui.dearpygui as dpg
import serial.tools.list_ports

from storage.csv import save_measurements_csv, import_measurements_csv
from experiments.voltage_sweep import MeasurementPoint
from app.models import RunRecord


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
    ):

        self.controller = controller

        # Track device connection state so operation buttons are only enabled
        # when both sensor and motor are connected.
        self._sensor_connected: bool = False
        self._motor_connected: bool = False

        # deque con límite: evita reconstruir la lista completa de líneas
        # (splitlines + join) en cada llamada a log().
        self._log_lines: deque[str] = deque(maxlen=300)

        # Historial de corridas (barrido / calibración / corregido). Cada
        # una queda como su propia curva en el gráfico -en vez de
        # reemplazar siempre las mismas curvas- para poder comparar varias
        # mediciones entre sí, incluso si tienen distinta cantidad de
        # puntos.
        # History stored as typed RunRecord instances (gradual migration).
        # Keep using mapping-style access (run["label"], ...) since RunRecord
        # implements __getitem__/__setitem__ for compatibility.
        self._history: list[RunRecord] = []
        self._history_by_id: dict[int, RunRecord] = {}
        self._run_counter = 0

        # Corrida en curso (None si no hay ninguna). Los callbacks de
        # progreso/finalización escriben sobre esta corrida.
        self._active_run: RunRecord | None = None

        # Corrida seleccionada para guardar, mientras el diálogo de
        # guardado está abierto.
        self._run_a_guardar: RunRecord | None = None

        # Corrida seleccionada para corregir, mientras el modal de
        # selección de blanco está abierto.
        self._run_a_corregir: RunRecord | None = None

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

    def _set_run_buttons_enabled(self, run_id: int, enabled: bool) -> None:
        # Configure the three buttons of a history row
        tags = [
            f"hist_guardar_{run_id}",
            f"hist_corregir_{run_id}",
            f"hist_eliminar_{run_id}",
        ]
        for tag in tags:
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, enabled=enabled)

    def _update_operation_buttons_state(self) -> None:
        """
        Enable operation buttons only when both sensor and motor are connected.
        Call whenever connection state changes.
        """
        enabled = bool(self._sensor_connected and self._motor_connected)
        self._set_operation_buttons_enabled(enabled)

    # Historial de corridas
    def create_live_run(
        self,
        kind: str,
        label: str,
    ) -> RunRecord:
        """Crea una nueva corrida EN VIVO: reserva un id, agrega su curva
        vacía al gráfico y una fila en el panel de historial. Queda como
        la corrida activa hasta que termine o falle; los callbacks de
        progreso van llenando measurements/curva a medida que llegan.
        """

        self._run_counter += 1
        run_id = self._run_counter

        curve_tag = f"curva_{kind}_{run_id}"

        dpg.add_line_series(
            [],
            [],
            label=label,
            parent="voltage_axis",
            tag=curve_tag,
        )

        run = self.register_run(run_id, kind, label, curve_tag)
        run["measurements"] = []

        self._active_run = run

        return run

    def create_computed_run(
        self,
        kind: str,
        label: str,
        measurements: list[MeasurementPoint],
    ) -> RunRecord:
        """Crea una corrida ya resuelta (p. ej. el resultado de restar un
        blanco a otra corrida): la curva se dibuja de una sola vez con
        los datos ya calculados, sin pasar por el mecanismo de
        progreso/corrida activa.
        """

        self._run_counter += 1
        run_id = self._run_counter

        curve_tag = f"curva_{kind}_{run_id}"

        dpg.add_line_series(
            [m.position_mm for m in measurements],
            [m.voltage_v for m in measurements],
            label=label,
            parent="voltage_axis",
            tag=curve_tag,
        )

        run = self.register_run(run_id, kind, label, curve_tag)
        run["measurements"] = measurements

        return run

    def register_run(
        self,
        run_id: int,
        kind: str,
        label: str,
        curve_tag: str,
    ) -> RunRecord:

        # Create a typed RunRecord (preferred) and store it in history.
        run = RunRecord(
            id=run_id,
            kind=kind,
            label=label,
            curve_tag=curve_tag,
            measurements=[],
            peak=None,
            peaks=[],
            csv_filename=None,
            row_tag=f"historial_fila_{run_id}",
            text_tag=f"historial_texto_{run_id}",
        )

        self._history.append(run)
        self._history_by_id[run_id] = run

        self.add_history_row(run)

        return run

    def add_history_row(self, run: RunRecord) -> None:

        with dpg.group(
            tag=run["row_tag"],
            parent="historial_lista",
        ):

            with dpg.group(horizontal=True):

                dpg.add_checkbox(
                    default_value=True,
                    callback=self.toggle_run_visibility,
                    user_data=run["id"],
                )

                dpg.add_text(
                    run["label"],
                    tag=run["texto_tag"],
                )

            with dpg.group(horizontal=True):

                dpg.add_button(
                    label="Guardar",
                    tag=f"hist_guardar_{run['id']}",
                    callback=self.on_click_save_run,
                    user_data=run["id"],
                    width=70,
                )

                dpg.add_button(
                    label="Corregir",
                    tag=f"hist_corregir_{run['id']}",
                    callback=self.on_click_correct_run,
                    user_data=run["id"],
                    width=70,
                )

                dpg.add_button(
                    label="✕",
                    tag=f"hist_eliminar_{run['id']}",
                    callback=self.on_click_delete_run,
                    user_data=run["id"],
                    width=30,
                )

            dpg.add_separator()

    def update_history_text(self, run: RunRecord) -> None:

        texto = run["label"]

        peak = run.get("peak")
        if peak is not None:
            texto += (
                f" — pico {peak.voltage_v:.4f}V"
                f" @ {peak.position_mm:.2f}mm"
            )

        if dpg.does_item_exist(run["texto_tag"]):
            dpg.set_value(run["texto_tag"], texto)

    def toggle_run_visibility(self, sender, value, user_data) -> None:

        run = self._history_by_id.get(user_data)

        if run is None:
            return

        if dpg.does_item_exist(run["curve_tag"]):
            dpg.configure_item(run["curve_tag"], show=value)

    def delete_run(self, run: RunRecord) -> None:

        if dpg.does_item_exist(run["curve_tag"]):
            dpg.delete_item(run["curve_tag"])

        if dpg.does_item_exist(run["row_tag"]):
            dpg.delete_item(run["row_tag"])

        self._history_by_id.pop(run["id"], None)

        if run in self._history:
            self._history.remove(run)

    def on_click_delete_run(self, sender, app_data, user_data) -> None:

        run = self._history_by_id.get(user_data)

        if run is None:
            return

        if self._active_run is run:
            self.log(
                "[HISTORIAL] No se puede eliminar una corrida en curso"
            )
            return

        self._eliminar_run(run)

    def clear_history(self) -> None:

        if self._active_run is not None:
            self.log(
                "[HISTORIAL] No se puede limpiar mientras hay una "
                "corrida en curso"
            )
            return

        for run in list(self._history):
            self.delete_run(run)

        dpg.set_value("resultado_maximo", "")

    # Guardado individual
    def on_click_save_run(self, sender, app_data, user_data) -> None:

        run = self._history_by_id.get(user_data)

        if run is None:
            return

        self._run_a_guardar = run

        # Los barridos ya quedan guardados automáticamente por el
        # controlador en runs/barrido_<id>.csv (ver iniciar_barrido);
        # se usa el mismo nombre como sugerencia acá para no terminar
        # con dos archivos distintos para la misma corrida, a menos que
        # el usuario elija explícitamente otro nombre o carpeta.
        csv_filename = run.get("csv_filename")

        if csv_filename:
            nombre_sugerido = os.path.splitext(
                os.path.basename(csv_filename)
            )[0]
        else:
            nombre_sugerido = f"{run['kind']}_{run['id']}"

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
            self.export_run_csv(run, path)
            self.log(f"[HISTORIAL] Guardado: {path}")

        except Exception as exc:
            self.log(f"[HISTORIAL ERROR] {exc}")

    def file_picker_import(self, sender, file_data) -> None:

        if not file_data or "file_path_name" not in file_data:
            return

        path = file_data["file_path_name"]

        try:
            measurements, metadata = import_measurements_csv(path)
        except Exception as exc:
            self.log(f"[IMPORT ERROR] {exc}")
            return

        label = metadata.get("label") or os.path.splitext(os.path.basename(path))[0]
        kind = "importado"

        nuevo = self._crear_run_calculado(
            kind,
            f"Importado: {label}",
            measurements,
        )

        # store the source filename in the run for potential saving suggestions
        nuevo["csv_filename"] = path

        # copy stabilization time (and keep any other useful metadata if present)
        nuevo["stabilization_time_s"] = metadata.get("stabilization_time_s", "")

        self.log(f"[IMPORT] {path} importado como {nuevo['label']}")

    def export_run_csv(self, run: RunRecord, path: str) -> None:

        measurements = run.get("measurements") or []

        metadata = {
            "kind": run.get("kind", ""),
            "label": run.get("label", ""),
            "id": str(run.get("id", "")),
            "stabilization_time_s": str(run.get("stabilization_time_s", "") or ""),
        }

        # Delegate to storage layer (which will write metadata header)
        save_measurements_csv(path, measurements, metadata=metadata)

    # Corrección por sustracción de blanco
    def on_click_correct_run(self, sender, app_data, user_data) -> None:

        run = self._history_by_id.get(user_data)

        if run is None:
            return

        if not run.get("measurements"):
            self.log(
                "[CORRECCIÓN] Esa corrida todavía no tiene mediciones"
            )
            return

        opciones = [
            r["label"]
            for r in self._history
            if r["id"] != run["id"]
            and r is not self._active_run
            and r.get("measurements")
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
            f"Corrida a corregir: {run['label']}",
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
            (r for r in self._history if r["label"] == etiqueta_blanco),
            None,
        )

        if blanco is None:
            self.log(
                "[CORRECCIÓN ERROR] No se encontró la corrida de "
                "referencia elegida"
            )
            return

        try:
            corregidos = self.subtract_reference(run, blanco)

        except Exception as exc:
            self.log(f"[CORRECCIÓN ERROR] {exc}")
            return

        nuevo = self._crear_run_calculado(
            "corregido",
            f"Corregido #{self._run_counter + 1}: "
            f"{run['label']} − {blanco['label']}",
            corregidos,
        )

        self.log(f"[CORRECCIÓN] {nuevo['label']} calculado")

    def subtract_reference(
        self,
        run: RunRecord,
        blanco: RunRecord,
    ) -> list[MeasurementPoint]:
        """Resta, punto a punto, el voltaje de una corrida de referencia
        (blanco: una corrida limpia, sin muestra en el portamuestras) al
        voltaje de la corrida real, para eliminar el ruido/offset propio
        del sistema. Como las dos corridas pueden tener distinta cantidad
        de puntos, el voltaje del blanco se interpola linealmente a cada
        posición de la corrida real.
        """

        measurements = run.get("measurements") or []
        referencia = sorted(
            blanco.get("measurements") or [],
            key=lambda m: m.position_mm,
        )

        if not measurements or not referencia:
            raise ValueError(
                "Ambas corridas necesitan mediciones para poder restar"
            )

        posiciones_ref = [m.position_mm for m in referencia]
        voltajes_ref = [m.voltage_v for m in referencia]

        corregidos = []

        for m in measurements:

            v_ref = self.interpolate(
                posiciones_ref,
                voltajes_ref,
                m.position_mm,
            )

            corregidos.append(
                MeasurementPoint(
                    position_mm=m.position_mm,
                    voltage_v=m.voltage_v - v_ref,
                )
            )

        return corregidos

    @staticmethod
    def interpolate(
        posiciones: list[float],
        voltajes: list[float],
        x: float,
    ) -> float:

        n = len(posiciones)

        if n == 0:
            return 0.0

        if n == 1:
            return voltajes[0]

        if x <= posiciones[0]:
            return voltajes[0]

        if x >= posiciones[-1]:
            return voltajes[-1]

        i = bisect.bisect_left(posiciones, x)

        x0, x1 = posiciones[i - 1], posiciones[i]
        y0, y1 = voltajes[i - 1], voltajes[i]

        if x1 == x0:
            return y0

        t = (x - x0) / (x1 - x0)

        return y0 + t * (y1 - y0)

    def update_ports(
        self,
    ) -> None:

        ports = [
            port.device
            for port
            in serial.tools.list_ports.comports()
        ]

        if not ports:
            ports = [
                "Sin puertos"
            ]
            self.log("[PUERTOS] No se encontraron puertos seriales")
        else:
            self.log(
                f"[PUERTOS] Encontrados: {', '.join(ports)}"
            )

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
            self._sensor_connected = True
            self._update_operation_buttons_state()

            self.log("[ESP32] Conectado")

        except Exception as exc:
            # Ensure flag is false on failure and update buttons
            self._sensor_connected = False
            self._update_operation_buttons_state()
            dpg.set_value("estado_esp32", "Desconectado")
            self.log(f"[ESP32 ERROR] {exc}")

    # Callbacks motor
    def connect_motor(self):

        try:
            self.controller.connect_motor(
                dpg.get_value("puerto_motor")
            )

            dpg.set_value("estado_motor", "Conectado")
            self._motor_connected = True
            self._update_operation_buttons_state()

            self.log("[MOTOR] Conectado")

        except Exception as exc:
            # Ensure flag is false on failure and update buttons
            self._motor_connected = False
            self._update_operation_buttons_state()
            dpg.set_value("estado_motor", "Desconectado")
            self.log(f"[MOTOR ERROR] {exc}")

    def move_motor(
        self,
    ):

        try:
            self._set_operation_buttons_enabled(False)

            self.controller.move_motor(
                dpg.get_value(
                    "posicion_objetivo"
                )
            )

            self.log("[MOTOR] Movimiento completado")

        except Exception as exc:

            self.log(f"[MOTOR ERROR] {exc}")

        finally:
            self._set_operation_buttons_enabled(True)

    # Barrido
    def start_sweep(self,):

        cantidad_puntos = dpg.get_value("cantidad_puntos")

        if cantidad_puntos < 1:
            self.log(
                "[BARRIDO ERROR] La cantidad de puntos debe ser mayor a 0"
            )
            return

        run = None

        try:
            self._set_operation_buttons_enabled(False)

            dpg.set_value("resultado_maximo", "Midiendo...")

            run = self._crear_run(
                "barrido",
                f"Barrido #{self._run_counter + 1} "
                f"({cantidad_puntos} pts)",
            )

            # start_voltage_sweep guarda a CSV incondicionalmente
            # (ver ApplicationController), así que esto es un respaldo
            # automático, no una elección del usuario. Se guarda la
            # ruta en el run para sugerirla como nombre por defecto si
            # el usuario después usa "Guardar" en el historial, en vez
            # de terminar con dos archivos distintos para la misma
            # corrida.
            os.makedirs(self.RUNS_DIR, exist_ok=True)
            csv_filename = os.path.join(
                self.RUNS_DIR,
                f"barrido_{run['id']}.csv",
            )
            run["csv_filename"] = csv_filename

            # store stabilization time for this run so exports include it
            run["stabilization_time_s"] = dpg.get_value("tiempo_estabilizacion")

            # mark expected points for the run (used for progress)
            run["expected_points"] = cantidad_puntos

            # disable row buttons while run is active
            self._set_run_buttons_enabled(run["id"], False)

            self.controller.start_voltage_sweep(

                start_position_mm=
                dpg.get_value(
                    "posicion_inicio"
                ),

                end_position_mm=
                dpg.get_value(
                    "posicion_final"
                ),

                number_of_points=cantidad_puntos,

                stabilization_time_s=
                dpg.get_value(
                    "tiempo_estabilizacion"
                ),

                csv_filename=csv_filename,

                on_progress=
                self.actualizar_barrido,

                on_finished=
                self.show_peaks,
            )

            self.log("[BARRIDO] Iniciado")

        except Exception as exc:

            self.log(f"[BARRIDO ERROR] {exc}")

            if run is not None:
                self._eliminar_run(run)

            self._active_run = None
            self._set_operation_buttons_enabled(True)

    def update_sweep(
        self,
        measurements,
    ):

        if not measurements:
            return

        run = self._active_run

        if run is None:
            return

        latest = measurements[-1]

        # dpg.mutex() for thread safety with DearPyGui
        with dpg.mutex():

            run["measurements"] = list(measurements)

            dpg.set_value(
                "voltaje_actual",
                f"{latest.voltage_v:.4f} V",
            )

            # update curve
            self.actualizar_curva(
                run["curve_tag"],
                measurements,
            )

            # update progress bar
            expected = run.get("expected_points") or len(measurements)
            if expected:
                progress = min(1.0, len(measurements) / expected)
                if dpg.does_item_exist("barrido_progress"):
                    dpg.set_value("barrido_progress", progress)

    def start_calibration(self,):

        run = None

        try:
            self._set_operation_buttons_enabled(False)

            cantidad_puntos = dpg.get_value("cantidad_puntos")

            run = self._crear_run(
                "calibracion",
                f"Calibración #{self._run_counter + 1} "
                f"({cantidad_puntos} pts)",
            )

            run["expected_points"] = cantidad_puntos

            # store stabilization time for this calibration run
            run["stabilization_time_s"] = dpg.get_value("tiempo_estabilizacion")

            self._set_run_buttons_enabled(run["id"], False)

            self.controller.start_calibration(

                start_position_mm=
                dpg.get_value(
                    "posicion_inicio"
                ),

                end_position_mm=
                dpg.get_value(
                    "posicion_final"
                ),

                number_of_points=cantidad_puntos,

                stabilization_time_s=
                dpg.get_value(
                    "tiempo_estabilizacion"
                ),

                on_progress=
                self.actualizar_barrido,

                on_finished=
                self.calibracion_finalizada,
            )

            self.log(
                "[CALIBRACIÓN] Iniciada"
            )

        except Exception as exc:

            self.log(
                f"[CALIBRACIÓN ERROR] {exc}"
            )

            if run is not None:
                self._eliminar_run(run)

            self._active_run = None
            self._set_operation_buttons_enabled(True)

    def calibration_finished(
        self,
        measurements,
    ):

        with dpg.mutex():

            run = self._active_run

            if run is not None:
                run["measurements"] = list(measurements)
                # enable row buttons once calibration finished
                self._set_run_buttons_enabled(run["id"], True)

            self.log(
                "[CALIBRACIÓN] Finalizada"
            )

            self.log(
                (
                    "[CALIBRACIÓN] "
                    f"{len(measurements)} puntos almacenados"
                )
            )

        self._active_run = None
        self._set_operation_buttons_enabled(True)

    def show_peaks(
        self,
        peaks: list[MeasurementPoint],
    ) -> None:
        """
        Handle the end of a sweep: receives a list of peaks (possibly empty).
        Updates the active run's metadata, the history text and the result widget.
        """

        with dpg.mutex():

            run = self._active_run

            primary = None
            if peaks:
                # choose highest-voltage peak as primary
                primary = peaks[0]

            if run is not None:
                # store peaks list and primary peak
                run["peaks"] = peaks
                run["peak"] = primary
                self.update_history_text(run)
                # enable row buttons now that run finished
                self._set_run_buttons_enabled(run["id"], True)

            if not peaks:
                dpg.set_value("resultado_maximo", "No se encontraron picos.")
            else:
                # Show top N peaks (up to 5) in result box
                lines = ["Picos encontrados:"]
                for idx, p in enumerate(peaks[:5], start=1):
                    lines.append(f"{idx}. {p.voltage_v:.4f} V @ {p.position_mm:.4f} mm")
                dpg.set_value("resultado_maximo", "\n".join(lines))

            self.log("[BARRIDO] Finalizado")

        self._active_run = None
        self._set_operation_buttons_enabled(True)

    def show_peak(self, peak: MeasurementPoint) -> None:
        # Compatibility wrapper: old callers pass a single MeasurementPoint
        self.show_peaks([peak] if peak is not None else [])

    # Construcción UI
    def build(self):

        dpg.create_context()

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

            dpg.add_text(
                "Corrida de referencia (blanco, sin muestra):"
            )

            dpg.add_combo(
                tag="combo_blanco",
                items=[],
                width=-1,
            )

            with dpg.group(horizontal=True):

                dpg.add_button(
                    label="Aplicar",
                    callback=self._aplicar_correccion,
                )

                dpg.add_button(
                    label="Cancelar",
                    callback=lambda: self._cancelar_correccion(),
                )

        with dpg.window(
            tag="ventana_principal",
        ):

            with dpg.group(horizontal=True):

                dpg.add_text("Refractómetro")

                dpg.add_button(
                    label="Actualizar puertos",
                    callback=self.actualizar_puertos,
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
                    callback=lambda:
                        dpg.hide_item(
                            "modal_info"
                        ),
                )

            with dpg.table(
                header_row=False,
                resizable=True,
                policy=dpg.mvTable_SizingStretchProp,
            ):

                dpg.add_table_column(
                    init_width_or_weight=0.28
                )

                dpg.add_table_column(
                    init_width_or_weight=0.72
                )

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
                                label="Conectar",
                                callback=self.connect_sensor,
                                width=-1,
                            )

                            dpg.add_separator()

                            dpg.add_text(
                                "--.-- V",
                                tag="voltaje_actual",
                            )

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

                            dpg.add_text("Puntos")

                            dpg.add_input_int(
                                tag="cantidad_puntos",
                                default_value=50,
                                min_value=1,
                                min_clamped=True,
                                width=-1,
                            )

                            dpg.add_text("Estabilización (s)")

                            dpg.add_input_float(
                                tag="tiempo_estabilizacion",
                                default_value=0.2,
                                min_value=0.0,
                                min_clamped=True,
                                width=-1,
                            )

                            dpg.add_button(
                                tag="barrido_btn",
                                label="▶ Barrido",
                                callback=self.start_sweep,
                                width=-1,
                            )

                            dpg.add_button(
                                tag="calibrar_btn",
                                label="⚙ Calibración",
                                callback=self.start_calibration,
                                width=-1,
                            )

                            dpg.add_progress_bar(
                                default_value=0.0,
                                tag="barrido_progress",
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

                            with dpg.child_window(
                                tag="historial_lista",
                                height=220,
                                border=True,
                            ):
                                pass

                            dpg.add_button(
                                label="Limpiar historial",
                                callback=self.clear_history,
                                width=-1,
                            )

                    with dpg.table_cell():

                        with dpg.plot(
                            label="Voltaje vs Posición",
                            height=600,
                            width=-1,
                        ):

                            dpg.add_plot_legend()

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
                            height=170,
                            border=True,
                        ):

                            dpg.add_input_text(
                                tag="registro",
                                multiline=True,
                                readonly=True,
                                width=-1,
                                height=-1,
                            )

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

        # Initialize operation buttons state (they should be disabled until both devices connect)
        self._update_operation_buttons_state()

        self.update_ports()

    def actualizar_curva(
        self,
        curve_tag: str,
        measurements: list[MeasurementPoint],
    ):

        if not measurements:
            return

        posiciones = [
            measurement.position_mm
            for measurement in measurements
        ]

        voltajes = [
            measurement.voltage_v
            for measurement in measurements
        ]

        dpg.set_value(
            curve_tag,
            [
                posiciones,
                voltajes,
            ],
        )

    def run(self):
        while dpg.is_dearpygui_running():
            dpg.render_dearpygui_frame()

    def close(self,):

        try:
            self.controller.disconnect_sensor()
            self._sensor_connected = False
            self._update_operation_buttons_state()
            self.log("[ESP32] Desconectado")
        except Exception as exc:
            self.log(f"[ESP32 ERROR] {exc}")

        if hasattr(self.controller, "disconnect_motor"):
            try:
                self.controller.disconnect_motor()
                self._motor_connected = False
                self._update_operation_buttons_state()
                self.log("[MOTOR] Desconectado")
            except Exception as exc:
                self.log(f"[MOTOR ERROR] {exc}")

        dpg.destroy_context()

    # ---------------------------
    # English API aliases (non-breaking)
    # ---------------------------
    # Prefer these English names in new code. Spanish names remain as wrappers.
    build = construir
    run = ejecutar
    close = cerrar
    connect_sensor = conectar_esp32
    connect_motor = conectar_motor
    move_motor = mover_motor
    start_sweep = iniciar_barrido
    update_sweep = actualizar_barrido
    start_calibration = iniciar_calibracion
    calibration_finished = calibracion_finalizada
    show_peaks = show_peaks  # already English; keep the reference
    show_peak = mostrar_pico  # compatibility wrapper exists
    create_live_run = _crear_run
    create_computed_run = _crear_run_calculado
    register_run = _registrar_run
    add_history_row = _agregar_fila_historial
    update_history_text = _actualizar_texto_historial
    toggle_run_visibility = _alternar_visibilidad_run
    delete_run = _eliminar_run
    on_click_delete_run = _click_eliminar_run
    clear_history = limpiar_historial
    on_click_save_run = _click_guardar_run
    file_picker_save_history = _file_picker_guardar_historial
    file_picker_import = _file_picker_import
    export_run_csv = _exportar_run_csv
    on_click_correct_run = _click_corregir_run
    cancel_correction = _cancelar_correccion
    apply_correction = _aplicar_correccion
    subtract_reference = _restar_blanco
    interpolate = _interpolar
    update_ports = actualizar_puertos
    set_operation_buttons_enabled = _set_operation_buttons_enabled
    set_run_buttons_enabled = _set_run_buttons_enabled
    update_operation_buttons_state = _update_operation_buttons_state
    # end aliases
