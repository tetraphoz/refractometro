from __future__ import annotations

import dearpygui.dearpygui as dpg
import serial.tools.list_ports

from experiments.voltage_sweep import MeasurementPoint


class ControlInterface:
    """
    Recibe un controlador de aplicación
    y solamente solicita acciones.
    """


    def __init__(
        self,
        controller,
    ):

        self.controller = controller



    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def log(
        self,
        message: str,
    ) -> None:

        current = dpg.get_value("registro",)

        lines = (current.splitlines())

        lines.append(message)


        if len(lines) > 300:
            lines = lines[-300:]


        dpg.set_value(
            "registro",
            "\n".join(lines),
        )



    def actualizar_puertos(
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


        dpg.configure_item(
            "puerto_esp32",
            items=ports,
        )


        dpg.configure_item(
            "puerto_motor",
            items=ports,
        )



    # ------------------------------------------------------------------
    # Callbacks ESP32
    # ------------------------------------------------------------------

    def conectar_esp32(
        self,
    ):

        try:

            self.controller.connect_sensor(
                dpg.get_value(
                    "puerto_esp32"
                ),

                dpg.get_value(
                    "baudrate"
                ),
            )


            dpg.set_value(
                "estado_esp32",
                "Conectado",
            )


            self.log(
                "[ESP32] Conectado"
            )


        except Exception as exc:

            self.log(
                f"[ESP32 ERROR] {exc}"
            )



    def desconectar_esp32(
        self,
    ):

        self.controller.disconnect_sensor()


        dpg.set_value(
            "estado_esp32",
            "Desconectado",
        )


    # ------------------------------------------------------------------
    # Callbacks motor
    # ------------------------------------------------------------------

    def conectar_motor(
        self,
    ):

        try:

            self.controller.connect_motor(
                dpg.get_value(
                    "puerto_motor"
                )
            )


            dpg.set_value(
                "estado_motor",
                "Conectado",
            )


            self.log(
                "[MOTOR] Conectado"
            )


        except Exception as exc:

            self.log(
                f"[MOTOR ERROR] {exc}"
            )



    def mover_motor(
        self,
    ):

        self.controller.move_motor(
            dpg.get_value(
                "posicion_objetivo"
            )
        )



    # ------------------------------------------------------------------
    # Barrido
    # ------------------------------------------------------------------

    def iniciar_barrido(
        self,
    ):


        self.controller.start_voltage_sweep(

            start_position_mm=
            dpg.get_value(
                "posicion_inicio"
            ),

            end_position_mm=
            dpg.get_value(
                "posicion_final"
            ),

            number_of_points=
            dpg.get_value(
                "cantidad_puntos"
            ),

            stabilization_time_s=
            dpg.get_value(
                "tiempo_estabilizacion"
            ),

            csv_filename=
            dpg.get_value(
                "archivo_csv"
            ),

            on_progress=
            self.actualizar_barrido,

            on_finished=
            self.mostrar_pico,
        )


        self.log("[BARRIDO] Iniciado")


    def actualizar_barrido(
        self,
        measurements,
    ):

        if not measurements:
            return


        latest = measurements[-1]


        dpg.set_value(
            "voltaje_actual",
            f"{latest.voltage_v:.4f} V",
        )


        self.actualizar_grafica(
            measurements
        )


    def iniciar_calibracion(
        self,
    ):

        try:

            self.controller.start_calibration(

                start_position_mm=
                dpg.get_value(
                    "posicion_inicio"
                ),

                end_position_mm=
                dpg.get_value(
                    "posicion_final"
                ),

                number_of_points=
                dpg.get_value(
                    "cantidad_puntos"
                ),

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


    def calibracion_finalizada(
        self,
        measurements,
    ):

        self.log(
            "[CALIBRACIÓN] Finalizada"
        )


        self.log(
            (
                "[CALIBRACIÓN] "
                f"{len(measurements)} puntos almacenados"
            )
        )


    def mostrar_pico(
        self,
        peak: MeasurementPoint,
    ):

        dpg.set_value(
            "resultado_maximo",
            (
                "Máximo encontrado:\n"
                f"{peak.voltage_v:.4f} V\n"
                f"Posición: {peak.position_mm:.4f} mm"
            ),
        )


    # ------------------------------------------------------------------
    # Construcción UI
    # ------------------------------------------------------------------

    def construir(
        self,
    ):


        dpg.create_context()


        dpg.create_viewport(
            title="Refractometro",
            width=950,
            height=700,
        )


        with dpg.window(
            tag="ventana_principal",
        ):


            with dpg.group(
                horizontal=True,
            ):


                # ======================================================
                # ESP32
                # ======================================================

                with dpg.child_window(
                    width=450,
                ):

                    dpg.add_text(
                        "Sensor ESP32",
                    )


                    dpg.add_combo(
                        tag="puerto_esp32",
                        label="Puerto ESP32",
                        items=[],
                    )


                    dpg.add_input_int(
                        tag="baudrate",
                        label="Velocidad de comunicación",
                        default_value=115200,
                    )


                    dpg.add_button(
                        label="Conectar ESP32",
                        callback=self.conectar_esp32,
                    )


                    dpg.add_button(
                        label="Desconectar ESP32",
                        callback=self.desconectar_esp32,
                    )


                    dpg.add_text(
                        "Desconectado",
                        tag="estado_esp32",
                    )


                    dpg.add_separator()


                    dpg.add_text(
                        "Voltaje medido:",
                    )


                    dpg.add_text(
                        "-- V",
                        tag="voltaje_actual",
                    )



                # ======================================================
                # MOTOR
                # ======================================================

                with dpg.child_window(
                    width=450,
                ):

                    dpg.add_text(
                        "Motor Zaber",
                    )


                    dpg.add_combo(
                        tag="puerto_motor",
                        label="Puerto motor",
                        items=[],
                    )


                    dpg.add_button(
                        label="Conectar motor",
                        callback=self.conectar_motor,
                    )


                    dpg.add_text(
                        "Desconectado",
                        tag="estado_motor",
                    )


                    dpg.add_input_float(
                        tag="posicion_objetivo",
                        label="Posición objetivo (mm)",
                    )


                    dpg.add_button(
                        label="Mover",
                        callback=self.mover_motor,
                    )


                    dpg.add_separator()


                    dpg.add_text(
                        "Barrido de voltaje",
                    )


                    dpg.add_input_float(
                        tag="posicion_inicio",
                        label="Posición inicial (mm)",
                        default_value=0,
                    )


                    dpg.add_input_float(
                        tag="posicion_final",
                        label="Posición final (mm)",
                        default_value=12,
                    )


                    dpg.add_input_int(
                        tag="cantidad_puntos",
                        label="Número de puntos",
                        default_value=50,
                    )


                    dpg.add_input_float(
                        tag="tiempo_estabilizacion",
                        label="Tiempo estabilización (s)",
                        default_value=0.2,
                    )


                    dpg.add_input_text(
                        tag="archivo_csv",
                        label="Archivo CSV",
                        default_value="barrido_potencia.csv",
                    )


                    dpg.add_button(
                        label="Iniciar barrido",
                        callback=self.iniciar_barrido,
                    )

                    dpg.add_button(
                        label="Calibrar sin muestra",
                        callback=self.iniciar_calibracion,
                    )

                    dpg.add_button(
                        label="Medición corregida",
                        callback=self.iniciar_medicion_corregida,
                    )


                    dpg.add_text(
                        "",
                        tag="resultado_maximo",
                    )



            dpg.add_separator()


            with dpg.plot(
                label="Voltaje vs Posición",
                height=300,
                width=850,
            ):

                dpg.add_plot_axis(
                    dpg.mvXAxis,
                    label="Posición (mm)",
                )

                dpg.add_plot_axis(
                    dpg.mvYAxis,
                    label="Voltaje (V)",
                    tag="voltage_axis",
                )

                dpg.add_line_series(
                    [],
                    [],
                    parent="voltage_axis",
                    tag="voltage_curve",
                )

                dpg.add_line_series(
                    [],
                    [],
                    label="Calibración",
                    parent="voltage_axis",
                    tag="calibration_curve",
                )

                dpg.add_line_series(
                    [],
                    [],
                    label="Corregido",
                    parent="voltage_axis",
                    tag="corrected_curve",
                )


            dpg.add_button(
                label="Actualizar puertos",
                callback=self.actualizar_puertos,
            )


            dpg.add_input_text(
                tag="registro",
                label="Registro",
                multiline=True,
                readonly=True,
                height=180,
            )



        dpg.setup_dearpygui()

        dpg.show_viewport()


        dpg.set_primary_window(
            "ventana_principal",
            True,
        )


        self.actualizar_puertos()

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



    def actualizar_grafica(
        self,
        measurements: list[MeasurementPoint],
    ):

        self.actualizar_curva(
            "voltage_curve",
            measurements,
        )



    def actualizar_grafica_corregida(
        self,
        raw_measurements,
        corrected_measurements,
    ):

        self.actualizar_curva(
            "voltage_curve",
            raw_measurements,
        )


        self.actualizar_curva(
            "corrected_curve",
            corrected_measurements,
        )


        if self.controller.calibration:

            self.actualizar_curva(
                "calibration_curve",
                self.controller.calibration.measurements,
            )

    def iniciar_medicion_corregida(
        self,
    ):

        try:

            self.controller.start_corrected_measurement(

                start_position_mm=
                dpg.get_value(
                    "posicion_inicio"
                ),

                end_position_mm=
                dpg.get_value(
                    "posicion_final"
                ),

                number_of_points=
                dpg.get_value(
                    "cantidad_puntos"
                ),

                stabilization_time_s=
                dpg.get_value(
                    "tiempo_estabilizacion"
                ),

                on_progress=
                self.actualizar_barrido,

                on_finished=
                self.medicion_corregida_finalizada,
            )


            self.log(
                "[MEDICIÓN] Iniciada"
            )


        except Exception as exc:

            self.log(
                f"[MEDICIÓN ERROR] {exc}"
            )

    def medicion_corregida_finalizada(
        self,
        raw_measurements,
        corrected_measurements,
    ):

        self.actualizar_grafica_corregida(
            raw_measurements,
            corrected_measurements,
        )


        self.log(
            "[MEDICIÓN] Finalizada"
        )

    def ejecutar(
        self,
    ):

        while dpg.is_dearpygui_running():

            dpg.render_dearpygui_frame()



    def cerrar(
        self,
    ):

        dpg.destroy_context()
