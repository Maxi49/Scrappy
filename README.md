# Scrappy

Scrappy descarga y organiza materiales de Moodle UCC. La interfaz visual se mantiene en PyQt6 y el núcleo de autenticación, detección, sincronización y descarga está implementado en Go.

## Qué cambió en la versión Go

El endpoint `core_course_get_contents` no representa por sí solo todos los archivos de un curso. Scrappy ahora combina esa respuesta con las APIs específicas que Moodle habilita para tareas, recursos, páginas, etiquetas, URLs, foros y otros tipos de actividad.

El catálogo resultante:

- procesa tanto `contents.type=file` como `contents.type=url`;
- incorpora `introfiles` y `contentfiles` de las actividades;
- detecta archivos y enlaces embebidos en HTML;
- conserva subcarpetas de recursos `folder`;
- deduplica las diferentes URLs que Moodle entrega para un mismo archivo;
- incluye todas las secciones por defecto;
- identifica módulos visibles pero inaccesibles sin intentar descargarlos;
- informa descargas parciales o fallidas en vez de finalizar silenciosamente.

El análisis técnico de la respuesta real y de los fallos anteriores está en [docs/api-response-analysis.md](docs/api-response-analysis.md).

## Arquitectura

```text
Scrappy/
├── cmd/scrappy-core/       # protocolo JSON del ejecutable Go
├── internal/moodle/        # autenticación, API y catálogo unificado
├── internal/syncer/        # manifiesto, rutas, descargas y reportes
├── gui/                    # UI PyQt6 y puente al proceso Go
├── scripts/                # build del core y de la app de escritorio
├── tests/                  # pruebas de UI y contrato Python/Go
├── go.mod
└── main.py
```

Python envía las solicitudes al core por `stdin` y recibe eventos JSON por `stdout`. Usuario, contraseña y token no se incluyen en argumentos de proceso ni en logs. En una build distribuida, `scrappy-core` queda dentro del bundle de la aplicación.

## Requisitos de desarrollo

- Go 1.23 o posterior.
- Python 3.11 recomendado.
- Dependencias de `requirements.txt`.

Chrome y ChromeDriver ya no son necesarios.

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-build.txt
python scripts/build_core.py
```

En Windows, activar el entorno con `\.venv\Scripts\Activate.ps1`.

## Ejecución

Interfaz gráfica:

```bash
python main.py
```

CLI:

```bash
python main.py --username USUARIO --output output
```

La contraseña se pide por consola sin mostrarse, o se toma de la variable `UCC_PASSWORD`. No se acepta como argumento porque quedaría visible para otros procesos y en el historial de la terminal.

Si `bin/scrappy-core` no existe durante el desarrollo, el puente usa `go run ./cmd/scrappy-core`. Las builds publicadas siempre incluyen el binario precompilado.

Variables opcionales:

```env
UCC_USERNAME=
UCC_PASSWORD=
MOODLE_BASE_URL=https://presencial.ucc.edu.ar
SCRAPPY_CORE_PATH=
```

`SCRAPPY_CORE_PATH` permite probar la UI con otro binario del core.

## Uso

1. Ingresar las credenciales de Moodle UCC.
2. Elegir las materias.
3. Seleccionar el modo de sincronización.
4. Elegir la carpeta de destino.
5. Iniciar la descarga y revisar el registro.

Los modos disponibles son:

- **Actualizar:** descarga recursos nuevos, cambiados o ausentes en disco.
- **Solo módulos nuevos:** omite secciones ya conocidas por el manifiesto.
- **Forzar descarga completa:** vuelve a descargar todo usando destinos determinísticos, sin crear copias `_1`, `_2` en cada ejecución.

## Salida

```text
<destino>/
├── <Materia>/
│   └── <Módulo>/
│       ├── archivo.pdf
│       ├── subcarpeta/archivo.h
│       └── enlace.url
└── .scrappy/
    ├── manifest.json
    ├── recursos_encontrados.json
    ├── recursos_encontrados.txt
    └── sync-report.json
```

Los archivos internos de Scrappy viven en la carpeta oculta `.scrappy/`, así el destino (por defecto `~/Downloads`) sólo muestra las materias. Si una versión anterior dejó `config/manifest.json` en el destino, se migra automáticamente sin volver a descargar nada.

`manifest.json` sólo marca un recurso como completo después de guardarlo correctamente. En modo actualizar, Scrappy también comprueba que el archivo local siga existiendo y que su tamaño coincida con el informado por Moodle.

`sync-report.json` contiene cantidades detectadas, descargadas, sin cambios, inaccesibles y fallidas, junto con errores por recurso. Las escrituras usan archivos temporales y reemplazo atómico para no dejar descargas truncadas como válidas.

## Pruebas

```bash
go test -race ./...
QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q
```

Las pruebas Go cubren respuestas `visible` como `0/1`, archivos de carpetas anidadas, contenidos URL, adjuntos de tareas, deduplicación, reintento de archivos borrados y fallos que no deben contaminar el manifiesto.

## Build de escritorio

```bash
python scripts/build_core.py
python scripts/build_desktop.py
python scripts/package_artifact.py
```

GitHub Actions ejecuta tests de Go y Python, compila un core nativo por plataforma, lo incorpora a PyInstaller y valida que el binario incluido arranque en macOS, Linux y Windows.

## Seguridad y alcance

- Scrappy sólo consulta materiales a los que la cuenta ya tiene acceso.
- Las credenciales se envían únicamente a la instancia Moodle configurada.
- El recordatorio opcional usa el keychain del sistema mediante `keyring`.
- El token Moodle se agrega sólo a URLs del host exacto de Moodle y sólo a endpoints de archivos de Web Services.
- Los enlaces externos conservan sus parámetros y se guardan como accesos directos `.url`.
- No se descargan entregas de estudiantes ni adjuntos privados de discusiones; se indexan materiales publicados como contenido de las actividades.

## Distribución

El workflow `.github/workflows/build-binaries.yml` genera:

- `Scrappy-windows.zip`
- `Scrappy-linux.zip`
- `Scrappy-macos-apple-silicon.zip`
- `Scrappy-macos-apple-silicon.dmg`

La app de macOS continúa con firma ad-hoc y no está notarizada con Apple Developer ID.
