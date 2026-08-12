# Refractómetro

Interfaz gráfica y adquisición de datos para un refractómetro motorizado.

Permite controlar un motor Zaber, leer un sensor conectado a un ESP32, ejecutar barridos y calibraciones, extraer picos, y guardar e importar resultados en CSV con metadatos.

## Requisitos

- Python 3.13+
- [Nix](https://nixos.org/) — recomendado para el entorno de desarrollo
- [uv](https://docs.astral.sh/uv/) — gestión de dependencias y entornos Python

Las dependencias de Python se declaran en `pyproject.toml` y las versiones exactas se registran en `uv.lock`.

### Dependencias principales

- `dearpygui >= 2.3.1`
- `pyserial >= 3.5`
- `zaber-motion >= 10.0.0`

## Inicio rápido

### Hardware simulado

Es posible ejecutar la aplicación sin dispositivos físicos utilizando hardware simulado.

1. Entrar al entorno de desarrollo:

   ```bash
   nix develop
   ```

2. Instalar las dependencias:

   ```bash
   uv sync
   ```

3. Ejecutar la aplicación:

   ```bash
   uv run python main.py --test
   ```

En la interfaz puedes:

- Ejecutar un barrido (**Barrido**) o una calibración (**Calibración**).
- Ver las corridas en el **Historial**.
- Calcular y mostrar picos por corrida.
- Exportar e importar corridas en CSV con metadatos.

## Uso con hardware real

1. Conectar el ESP32 (sensor) y el motor Zaber al equipo.
2. Pulsar **Actualizar puertos** en la UI y seleccionar los puertos correspondientes.
3. Presionar **Conectar** para el ESP32 y **Conectar motor** para Zaber.
4. Cuando ambos dispositivos estén conectados, los botones de barrido y calibración se habilitan.

## Estructura del proyecto

Módulos principales:

- `gui/interface.py` — Interfaz DearPyGui y lógica de la UI.
- `app/application.py` — Controlador de alto nivel que orquesta hardware y experimentos.
- `app/models.py` — `RunRecord`: modelo tipado para entradas del historial.
- `experiments/` — Lógica de experimentos (`VoltageSweep`, `CalibrationCurve`).
- `hardware/` — Drivers y simuladores (ESP32, Zaber, simulados).
- `storage/csv.py` — Importación y exportación CSV con cabecera de metadatos.
- `tests/` — Pruebas automatizadas.

## Desarrollo

El proyecto utiliza **Nix + uv** para proporcionar un entorno de desarrollo reproducible.

### Configurar el entorno

Desde una copia del repositorio:

```bash
nix develop
uv sync
```

Esto crea el entorno virtual de Python y sincroniza las dependencias especificadas en `pyproject.toml` y `uv.lock`.

### Ejecutar la aplicación

Con el entorno configurado:

```bash
uv run python main.py --test
```

### Ejecutar tests

```bash
uv run pytest -q
```

### Formatear y lintear

El proyecto utiliza `pre-commit` para ejecutar automáticamente las herramientas de formato y análisis estático.

Instalar los hooks:

```bash
uv run pre-commit install
```

Ejecutar todos los hooks manualmente:

```bash
uv run pre-commit run --all-files
```

### Añadir dependencias

Las dependencias deben gestionarse con `uv` y no instalarse manualmente dentro del entorno:

```bash
uv add <paquete>
```

Para dependencias exclusivamente de desarrollo:

```bash
uv add --dev <paquete>
```

Por ejemplo:

```bash
uv add --dev pytest
```

Después de modificar las dependencias, `uv` actualizará `pyproject.toml` y `uv.lock`.

## CSV y metadatos

Los CSV exportados por la aplicación incluyen líneas de cabecera comentadas con metadatos en el formato:

```text
# clave: valor
```

Los metadatos incluyen, cuando están disponibles:

- `label`
- `kind`
- `id`
- `start_position_mm`
- `end_position_mm`
- `number_of_points`
- `stabilization_time_s`

El importador analiza estas líneas y devuelve tanto las mediciones como los metadatos.

Si faltan metadatos, se rellenan valores por defecto, como la etiqueta derivada del nombre de archivo o el recuento inferido.

## Contribuir

- Crea una rama nueva para cada feature o cambio independiente.
- Ejecuta los tests y los hooks de `pre-commit` antes de abrir un PR.
- Mantén `pyproject.toml` y `uv.lock` sincronizados con los cambios de dependencias.
- Coordina con el mantenedor antes de reescribir el historial de Git.
- Haz siempre una copia de seguridad antes de realizar operaciones destructivas sobre el historial.
