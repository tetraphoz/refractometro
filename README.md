# Refractómetro

**Versión actual: v2.1**

Aplicación gráfica para controlar un refractómetro motorizado, adquirir datos experimentales y analizar mediciones de voltaje en función de la posición.

El sistema coordina:

- un **motor Zaber**, usado para desplazar la muestra;
- un **ESP32**, usado para leer la señal del sensor;
- una interfaz gráfica en **DearPyGui**;
- almacenamiento/importación de corridas en **CSV**;
- análisis básico de corridas, picos y correcciones por referencia.

![interface](./interface.jpg)

La aplicación también incluye un **modo de simulación** para probar la interfaz y el flujo experimental sin conectar el hardware real.

## Descargar y ejecutar

No es necesario instalar Python, Nix ni dependencias de desarrollo para usar una versión publicada.

Los ejecutables se publican en la sección **Releases** de GitHub.

### Windows

1. Descarga `refractometro-windows-x86_64.zip` desde la versión más reciente.
2. Extrae el contenido del archivo `.zip`.
3. Abre la carpeta extraída.
4. Ejecuta `refractometro.exe`.

### Linux

1. Descarga `refractometro-linux-x86_64.tar.gz`.
2. Extrae el archivo:

   ```bash
   tar -xzf refractometro-linux-x86_64.tar.gz
   cd refractometro
   ```

3. Ejecuta:

   ```bash
   ./refractometro
   ```

Si Linux indica que el archivo no tiene permisos de ejecución:

```bash
chmod +x refractometro
./refractometro
```

## Modo de simulación

El modo de simulación permite ejecutar la aplicación sin conectar el ESP32 ni el motor Zaber.

En Linux:

```bash
./refractometro --test
```

En Windows:

```bash
refractometro.exe --test
```

Desde el entorno de desarrollo:

```bash
uv run python main.py --test
```

En este modo se puede:

- ejecutar un **Barrido**;
- ejecutar una **Calibración**;
- mover un motor simulado;
- consultar corridas en el **Historial**;
- calcular y visualizar picos;
- importar/exportar corridas CSV;
- exportar gráficas PNG asociadas a una corrida.

## Uso con el refractómetro

### 1. Conectar el equipo

Conecta al ordenador:

- el ESP32 del sensor;
- el motor Zaber.

### 2. Seleccionar puertos

1. Abre la aplicación.
2. Pulsa **Actualizar puertos**.
3. Selecciona el puerto correspondiente al ESP32.
4. Selecciona el puerto correspondiente al motor Zaber.
5. Pulsa **Conectar** para el ESP32.
6. Pulsa **Conectar motor** para el motor Zaber.

Las operaciones de movimiento, barrido y calibración se habilitan solamente cuando ambos dispositivos están conectados y no hay una operación en curso. Los botones de conexión se muestran en verde cuando el dispositivo está conectado; **Cancelar** usa rojo para indicar una acción de seguridad. La leyenda de la gráfica puede ocultarse. Los parámetros del barrido se muestran con etiquetas visibles y la selección de una corrida de referencia usa una lista visible en lugar de un menú desplegable.

### 3. Configurar una corrida

En la sección **Barrido** define:

- posición inicial;
- posición final;
- cantidad de puntos;
- tiempo de estabilización.

### 4. Ejecutar una operación

La interfaz permite:

- **Mover**: desplaza el motor a una posición absoluta.
- **Barrido**: mide voltaje vs posición en el intervalo configurado.
- **Calibración**: adquiere una corrida de referencia, por ejemplo con el portamuestras vacío.

Durante una operación larga, los botones de operación se deshabilitan para evitar solicitudes superpuestas. El botón **Cancelar** solicita la detención de la operación, conserva las mediciones parciales y devuelve el motor a la posición inicial. Si una operación falla, la corrida se marca como fallida y los botones vuelven a su estado correcto.

### 5. Trabajar con el historial

Cada barrido, calibración, corrida importada o corrida corregida queda registrada en el **Historial**.

Desde cada fila del historial se puede:

- mostrar u ocultar la curva;
- seleccionar indirectamente curvas para el promedio manteniéndolas visibles;
- guardar la corrida como CSV;
- corregirla usando otra corrida como referencia;
- calcular/mostrar picos;
- exportar la gráfica como PNG;
- eliminar la corrida.

## Corrección por referencia

La corrección permite restar una corrida de referencia, o blanco, a una corrida experimental.

La referencia se interpola linealmente para poder corregir corridas con distinta cantidad de puntos o posiciones no idénticas.

El historial también permite promediar las curvas visibles y completas. El promedio se calcula sobre el rango de posiciones común y usa interpolación lineal cuando las corridas tienen diferentes puntos; las curvas ocultas, fallidas, canceladas o interrumpidas se excluyen. Si el promedio falla, los controles de barrido y calibración recuperan su estado inmediatamente.

Estos cálculos viven en `app/run_processing.py` y reutilizan la lógica de interpolación de `experiments/calibration.py`.

## Datos y archivos CSV

Los resultados se almacenan en archivos CSV con dos tipos de información:

1. metadatos opcionales en líneas comentadas;
2. mediciones de posición y voltaje.

Ejemplo de metadato:

```text
# clave: valor
```

Las mediciones usan las columnas:

```text
position_mm,voltage_v
```

Los metadatos pueden incluir:

- `label`
- `kind`
- `id`
- `start_position_mm`
- `end_position_mm`
- `number_of_points`
- `stabilization_time_s`
- `laser_on_time_s`: tiempo transcurrido desde el inicio de la aplicación, usado como referencia del tiempo de encendido del láser.

Al importar un CSV, el sistema recupera las mediciones y los metadatos disponibles. Si faltan algunos metadatos, se infieren valores razonables, como la etiqueta a partir del nombre del archivo o el número de puntos a partir de las filas de medición.

Los barridos se respaldan automáticamente en `runs/barrido_<id>.csv`. El botón **Guardar** permite exportar cualquier corrida del historial a una ubicación elegida por el usuario.

Además, la aplicación mantiene un índice local SQLite en `runs/refractometro.sqlite3`. La base de datos conserva el historial de corridas y sus mediciones para restaurarlo al abrir la aplicación. Las etiquetas visuales y los picos se reconstruyen al iniciar; los picos se calculan nuevamente a partir de las mediciones guardadas. Una corrida que estaba pendiente o en curso cuando la aplicación se cerró se marca como interrumpida al volver a abrirla.

Cada corrida recibe un `uid` SHA-256 generado a partir de su instante de inicio. Los nombres temporales usan la forma `tipo_YYYYMMDD_HHMMSS_microsegundos_uid.csv`, evitando que dos corridas nuevas compartan el mismo nombre. Las corridas derivadas guardan los UID de origen, el tipo de análisis utilizado y sus parámetros. Los promedios y correcciones también pueden exportarse como PNG aunque todavía no tengan un CSV asociado; el archivo se crea automáticamente en `runs/`.

## Desarrollo

Esta sección está destinada a quienes quieran modificar o contribuir al proyecto.

El entorno de desarrollo usa **Nix + uv** para mantener dependencias reproducibles.

### Requisitos

- Python 3.13+
- Nix
- uv

Las dependencias de Python están declaradas en `pyproject.toml` y sus versiones exactas se registran en `uv.lock`.

### Dependencias principales

- `dearpygui` >= 2.3.1
- `pyserial` >= 3.5
- `zaber-motion` >= 10.0.0
- `matplotlib` >= 3.11.1

### Cambios destacados de v2.1

- historial persistente en SQLite con recuperación de bases creadas por versiones anteriores;
- procedencia y parámetros de análisis para corridas derivadas;
- exportación PNG robusta para corridas promedio y corregidas;
- anotaciones de picos dentro del área de la gráfica, sin invadir las etiquetas de los ejes;
- controles de la interfaz con etiquetas visibles y selección de referencias mediante lista.

### Configurar el entorno

Desde una copia del repositorio:

```bash
nix develop
uv sync
```

### Ejecutar la aplicación

Con hardware simulado:

```bash
uv run python main.py --test
```

Con hardware real:

```bash
uv run python main.py
```

### Ejecutar tests

```bash
uv run pytest -q
```

### Formatear y lintear

El proyecto usa `pre-commit` para ejecutar herramientas de formato y análisis estático.

Instalar hooks:

```bash
uv run pre-commit install
```

Ejecutar todos los hooks manualmente:

```bash
uv run pre-commit run --all-files
```

### Añadir dependencias

Dependencia de ejecución:

```bash
uv add <paquete>
```

Dependencia solo de desarrollo:

```bash
uv add --dev <paquete>
```

Después de modificar dependencias, `uv` actualizará `pyproject.toml` y `uv.lock`.

## Arquitectura del proyecto

La aplicación está organizada para separar responsabilidades entre interfaz, coordinación de aplicación, dominio experimental, hardware y almacenamiento.

### Entrada principal

- `main.py`
  - punto de entrada;
  - parsea argumentos;
  - selecciona hardware real o simulado;
  - crea el controlador y la interfaz.

### Capa `gui/`

- `gui/interface.py`
  - construcción de ventanas y widgets DearPyGui;
  - callbacks de botones y diálogos;
  - coordinación del historial, progreso y logs;
  - traducción de acciones del usuario hacia servicios de aplicación.

- `gui/plot_view.py`
  - actualización de series de la gráfica.

- `gui/themes.py`
  - temas semánticos para botones y estados de conexión.

La GUI debe mantenerse lo más libre posible de reglas de negocio. Si una función puede probarse sin DearPyGui, probablemente pertenece a `app/`, `experiments/` o `storage/`.

### Capa `app/`

- `app/application.py`
  - controlador de alto nivel;
  - coordina hardware y experimentos;
  - ejecuta barridos/calibraciones en hilos de trabajo;
  - expone el estado `IDLE`/`RUNNING`/`CANCELLING`;
  - notifica progreso, finalización, cancelación y errores mediante callbacks.

- `app/models.py`
  - modelos compartidos de la aplicación;
  - incluye `RunRecord`, su estado persistente, el tiempo acumulado de láser y la procedencia de resultados derivados.

- `app/run_history.py`
  - administra IDs de corridas;
  - mantiene la lista ordenada de corridas;
  - permite buscar por ID;
  - mantiene la corrida activa.

- `app/run_processing.py`
  - contiene lógica de análisis de corridas;
  - resta referencias/blancos;
  - promedia corridas sobre un rango común;
  - formatea resúmenes de picos;
  - expone un wrapper de interpolación.

- `app/run_io.py`
  - adapta `RunRecord` a importación/exportación CSV;
  - construye metadatos de exportación;
  - actualiza el nombre asociado después de guardar;
  - delega lectura/escritura cruda a `storage/csv.py`.

- `app/run_naming.py`
  - genera nombres temporales basados en el instante de inicio y el `uid`.

- `app/run_repository.py`
  - persiste corridas, estado, tiempo de láser, procedencia, parámetros de análisis y mediciones en SQLite;
  - reemplaza las mediciones de una corrida de forma atómica;
  - no almacena estado específico de la interfaz.

- `app/operation_state.py`
  - define el ciclo de vida de una operación de hardware;
  - mantiene el estado de conexión de sensor y motor;
  - calcula si las operaciones pueden estar habilitadas.

- `app/errors.py`
  - centraliza los tipos de error esperados;
  - evita capturas amplias como `except Exception`;
  - incluye errores de IO, validación, CSV y Zaber.

### Capa `experiments/`

- `experiments/voltage_sweep.py`
  - define `MeasurementPoint`;
  - ejecuta el barrido punto a punto;
  - permite cancelación cooperativa durante el movimiento/estabilización;
  - calcula picos locales.

- `experiments/calibration.py`
  - define `CalibrationCurve`;
  - ordena mediciones de referencia;
  - interpola linealmente;
  - resta una curva de referencia a mediciones experimentales.

### Capa `hardware/`

- `hardware/esp32.py`
  - comunicación serial con el ESP32 real.

- `hardware/zaber.py`
  - control del motor Zaber real mediante `zaber-motion`.

- `hardware/simulated_motor.py`
  - motor simulado para desarrollo;
  - implementa detención cooperativa.

- `hardware/protocols.py`
  - define las interfaces mínimas de motor y sensor;
  - exige `stop()` para cancelar movimientos de forma segura.

- `hardware/simulated_sensor.py`
  - sensor ESP32 simulado para desarrollo.

### Capa `storage/`

- `storage/csv.py`
  - lectura y escritura de CSV con metadatos;
  - escritura atómica para evitar archivos parciales.

- `storage/image_plot.py`
  - exportación de gráficas PNG usando `matplotlib`.

## Convenciones de desarrollo

- No usar capturas amplias como `except Exception` salvo que sea una frontera claramente justificada y documentada.
- Usar `app/errors.py` para compartir los tipos de excepción esperados entre capas.
- Mantener DearPyGui dentro de `gui/`.
- Mantener reglas de negocio y funciones testeables fuera de `gui/interface.py`.
- Añadir pruebas cuando se agregue lógica a `app/`, `experiments/` o `storage/`.
- Evitar cambiar el formato CSV sin actualizar tests y documentación.
- No editar artefactos generados en `build/`, `dist/`, `.venv/`, `runs/` o `calibraciones/` salvo que el cambio lo requiera explícitamente.

## Contribuir

1. Crea una rama nueva para cada feature o cambio independiente.
2. Realiza los cambios y añade pruebas cuando sea necesario.
3. Ejecuta los tests:

   ```bash
   uv run pytest -q
   ```

4. Ejecuta los hooks de pre-commit:

   ```bash
   uv run pre-commit run --all-files
   ```

5. Mantén `pyproject.toml` y `uv.lock` sincronizados con los cambios de dependencias.
6. Abre un Pull Request describiendo los cambios realizados.

Evita reescribir el historial de Git compartido sin coordinarlo previamente con los demás colaboradores.
