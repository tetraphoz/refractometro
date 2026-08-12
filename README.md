#Refractómetro 
interfaz gráfica y adquisición de datos para un refractómetro motorizado. 
Permite controlar un motor Zaber, leer un sensor conectado a un ESP32, ejecutar barridos y calibraciones, extraer picos, y guardar/importar resultados en CSV con metadatos.

#Requisitos
- Python 3.13+
- Dependencias (instalar con pip o correr con nix):
    python -m pip install "dearpygui>=2.3.1" "pyserial>=3.5" "zaber-motion>=10.0.0"

#Inicio rápido (hardware simulado)
1. Ejecutar la aplicación usando hardware simulado (no se requieren dispositivos físicos):
    python main.py --test
2. En la UI puede:
   - Ejecutar un barrido (Barrido) o una calibración (Calibración),
   - Ver las corridas en el Historial,
   - Calcular y mostrar picos por corrida,
   - Exportar / importar corridas en CSV (con metadatos).

Uso con hardware real
- Conectar el ESP32 (sensor) y el motor Zaber al equipo.
- Pulsar "Actualizar puertos" en la UI y seleccionar los puertos correspondientes.
- Presionar "Conectar" (ESP32) y "Conectar motor" (Zaber).
- Cuando ambos dispositivos estén conectados, los botones de barrido/calibración se habilitan.

#Estructura del proyecto (módulos principales)
- gui/interface.py — Interfaz DearPyGui y lógica de la UI
- app/application.py — Controlador de alto nivel que orquesta hardware y experimentos
- app/models.py — RunRecord: modelo tipado para entradas de historial
- experiments/ — Lógica de experimentos (VoltageSweep, CalibrationCurve)
- hardware/ — Drivers y simuladores (ESP32, Zaber, simulados)
- storage/csv.py — Importación/exportación CSV con cabecera de metadatos
- tests/ — Pruebas unitarias (si existen)

#Desarrollo
- Ejecutar tests:
    pytest -q
- Formatear y lintear (recomendado, con pre-commit):
    pip install pre-commit black ruff isort
    pre-commit install
    pre-commit run --all-files
- Si usas Nix, hay un flake (flake.nix) para un entorno de desarrollo reproducible.

#CSV y metadatos
- Los CSV exportados por la aplicación llevan líneas de cabecera comentadas con metadatos (formato: "# clave: valor"). Los metadatos incluyen, cuando están disponibles: label, kind, id, start_position_mm, end_position_mm, number_of_points, stabilization_time_s.
- El importador analiza esas líneas y devuelve tanto las mediciones como los metadatos; si faltan metadatos se rellenan valores por defecto (etiqueta derivada del nombre de archivo, recuento inferido, etc.).

#Contribuir
- Crea una rama nueva por feature.
- Ejecuta linters y tests localmente antes de abrir PR.
- Coordina con el mantenedor antes de reescribir el historial git; haz siempre una copia de seguridad del repositorio.

