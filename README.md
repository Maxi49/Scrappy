# Scrappy

Scrappy es una aplicación de escritorio para descargar y organizar recursos de Moodle UCC. Está pensada para estudiantes que quieren mantener sus materiales locales ordenados por materia y módulo, sin tener que entrar curso por curso buscando PDFs, presentaciones, documentos, carpetas o enlaces.

El proyecto combina dos caminos de extracción:

- **Moodle Web Services**, cuando la plataforma entrega token de API. Es el camino principal, más rápido y sin navegador.
- **Selenium con Chrome**, como fallback cuando la API no está disponible o no alcanza para resolver un caso puntual.

La app incluye una GUI en PyQt6, persistencia de configuración local, recordatorio opcional de credenciales mediante el keychain del sistema, builds multiplataforma y releases generados por GitHub Actions.

## Estado Del Proyecto

Scrappy está en etapa funcional temprana. Ya sirve para uso real, pero todavía no es un producto firmado/notarizado con instalador nativo.

Funciona actualmente en:

- Windows, mediante build `.exe` empaquetada en zip.
- Linux, mediante binario empaquetado en zip.
- macOS Apple Silicon, mediante `.app` empaquetada en zip.

No se está publicando build para macOS Intel en este momento.

## Alcance

Scrappy descarga y organiza materiales a los que tu usuario de Moodle ya tiene acceso. No intenta evadir permisos, no accede a cursos ajenos y no modifica contenido remoto.

Casos cubiertos:

- Listar materias inscritas.
- Seleccionar qué materias descargar.
- Detectar módulos/unidades dentro de cada materia.
- Descargar recursos alojados en Moodle.
- Guardar accesos directos para enlaces externos y Google Drive.
- Exportar un índice JSON y TXT de lo encontrado.
- Evitar descargas repetidas usando un manifiesto incremental.

Casos no cubiertos todavía:

- Auto-update dentro de la app.
- Notarización oficial de macOS con Apple Developer ID.
- Instaladores `.msi`, `.dmg`, `.pkg`, `.deb` o `.AppImage`.
- Sincronización bidireccional.
- Ejecución como servicio/background daemon.

## Características

### Aplicación De Escritorio

- GUI en PyQt6 con paneles separados para conexión, materias, configuración y registro.
- Selección visual de materias mediante cards.
- Selector de carpeta de destino.
- Modo headless configurable para Selenium.
- Registro de progreso durante la descarga.
- Persistencia de la última carpeta usada.

### Autenticación

- Login con usuario y contraseña de Moodle UCC.
- Obtención automática de token Moodle Mobile Web Services cuando está disponible.
- Recordatorio opcional de credenciales usando `keyring`.
- Las credenciales no se guardan en archivos del proyecto.

### Extracción De Datos

- Camino rápido por API:
  - `core_webservice_get_site_info`
  - `core_enrol_get_users_courses`
  - `core_course_get_contents`
- Fallback por Selenium:
  - Login en navegador.
  - Lectura de materias desde dashboard.
  - Lectura de módulos desde cursos con formato tiles.
  - Extracción de actividades desde el HTML.

### Descarga Y Organización

- Descargas paralelas con `requests`.
- Organización por materia y módulo.
- Resolución de nombres de archivo desde URL, headers y tipo de contenido.
- Sanitización de nombres para evitar caracteres inválidos.
- Prevención de colisiones de archivos.
- Soporte para recursos alojados en `pluginfile.php`.
- Soporte parcial para páginas HTML intermedias que contienen enlaces reales a archivos.

### Tipos De Recursos

Scrappy clasifica recursos como:

- PDF
- PowerPoint
- Word
- Archivo genérico
- Carpeta Moodle
- Link externo
- Google Drive
- YouTube
- Desconocido

Los enlaces de Google Drive se guardan como archivos `.url`, no como descargas directas del archivo remoto.

### Modos De Descarga

En la UI, cada ejecución puede usar uno de estos modos:

- **Actualizar (buscar cambios en módulos):** compara hashes de recursos por módulo contra el manifiesto local y descarga lo nuevo o cambiado.
- **Solo módulos nuevos:** salta módulos que ya existen en el manifiesto.
- **Forzar descarga completa:** procesa todo lo seleccionado sin usar el manifiesto como filtro.

## Instalación Para Usuarios

La forma recomendada para usuarios no técnicos es descargar el release correspondiente desde GitHub.

Release actual:

```text
https://github.com/Maxi49/Scrappy/releases/latest
```

Archivos publicados:

- `Scrappy-windows.zip`
- `Scrappy-linux.zip`
- `Scrappy-macos-apple-silicon.zip`

### Windows

1. Descargar `Scrappy-windows.zip`.
2. Extraer el zip en una carpeta local.
3. Ejecutar `Scrappy.exe`.

Si Windows SmartScreen muestra una advertencia, se debe a que la app todavía no está firmada con certificado de distribución. El usuario puede abrirla manualmente si confía en el origen del release.

### Linux

1. Descargar `Scrappy-linux.zip`.
2. Extraer el zip.
3. Entrar a la carpeta extraída:

```bash
cd Scrappy
```

4. Dar permisos de ejecución si hiciera falta:

```bash
chmod +x Scrappy
```

5. Ejecutar:

```bash
./Scrappy
```

Si el sistema no tiene librerías gráficas necesarias para Qt, instalar los paquetes equivalentes de la distribución. En Ubuntu/Debian suelen estar relacionados con EGL, GL, DBus, XKB y XCB.

### macOS Apple Silicon

1. Descargar `Scrappy-macos-apple-silicon.zip`.
2. Extraer el zip.
3. Mover `Scrappy.app` a `Applications` si se desea.
4. Abrir con click derecho y luego **Open/Abrir** la primera vez.

La app está firmada ad-hoc en CI para que el bundle sea válido, pero no está notarizada por Apple. Por eso macOS puede advertir que proviene de un desarrollador no identificado. Para eliminar ese aviso por completo hace falta una cuenta Apple Developer y notarización oficial.

## Uso De La App

### 1. Conexión

Al abrir Scrappy se muestra el panel de conexión.

Ingresar:

- Usuario de Moodle UCC.
- Contraseña de Moodle UCC.

Opcionalmente se puede activar el recordatorio de credenciales. En ese caso se usa el keychain/credential store del sistema operativo mediante `keyring`.

Si la API de Moodle devuelve token, la app muestra estado de conexión por API. Si no hay token, intenta usar Selenium como fallback.

### 2. Selección De Materias

Después del login, Scrappy lista las materias disponibles. Cada card representa una materia. Por defecto quedan seleccionadas.

Acciones disponibles:

- Seleccionar todas.
- Deseleccionar todas.
- Activar o desactivar materias individualmente.

### 3. Modo De Descarga

Antes de comenzar, elegir el modo:

- Actualizar.
- Solo módulos nuevos.
- Forzar descarga completa.

El modo se aplica a las materias seleccionadas en esa ejecución.

### 4. Configuración

Desde el panel de configuración se puede elegir:

- Carpeta de salida.
- Modo headless para Selenium.

La última carpeta de salida se guarda en:

```text
config/user_settings.json
```

### 5. Descarga

Al iniciar la descarga, la app cambia al panel de registro. Allí muestra eventos de progreso, errores parciales y estado final.

La salida se escribe dentro de la carpeta elegida.

## Salida Generada

Scrappy organiza los recursos así:

```text
<carpeta-de-salida>/
├── <Materia>/
│   ├── <Modulo>/
│   │   ├── archivo.pdf
│   │   ├── presentacion.pptx
│   │   └── enlace_drive.url
│   └── ...
├── config/
│   └── manifest.json
├── recursos_encontrados.json
└── recursos_encontrados.txt
```

### `recursos_encontrados.json`

Exporta una lista estructurada de recursos con esta forma:

```json
[
  {
    "nombre": "Guia de Trabajos Practicos.pdf",
    "url": "https://presencial.ucc.edu.ar/...",
    "tipo": "pdf",
    "modulo": "Unidad II",
    "materia": "Sistemas de Informacion"
  }
]
```

### `recursos_encontrados.txt`

Exporta una versión legible para revisar rápido por materia y módulo.

### `config/manifest.json`

Guarda hashes por módulo para poder detectar cambios entre ejecuciones. Es la base de los modos incrementales.

## Modo Desarrollador

### Requisitos

Recomendado:

- Python 3.11.
- Google Chrome instalado para el fallback Selenium.
- Git.

El proyecto pinnea PyQt6 y PyQt6-Qt6 para evitar incompatibilidades ABI en CI.

### Setup Local

Clonar el repositorio:

```bash
git clone https://github.com/Maxi49/Scrappy.git
cd Scrappy
```

Crear entorno virtual:

```bash
python -m venv .venv
```

Activar en macOS/Linux:

```bash
source .venv/bin/activate
```

Activar en Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Instalar dependencias:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Para builds y tests:

```bash
python -m pip install -r requirements-build.txt
```

### Ejecutar GUI

```bash
python main.py
```

Si se ejecuta sin argumentos, `main.py` abre la GUI.

### Ejecutar CLI

Si `main.py` recibe argumentos, usa modo CLI:

```bash
python main.py --username TU_USUARIO --password TU_PASSWORD
```

Opciones:

```bash
python main.py --help
```

Parámetros soportados:

- `--username`, `-u`
- `--password`, `-p`
- `--headless`
- `--no-export`

### Variables De Entorno

El proyecto carga `.env` mediante `python-dotenv`.

Variables soportadas:

```env
UCC_USERNAME=
UCC_PASSWORD=
HEADLESS=False
```

Estas variables se usan principalmente para CLI/Selenium. En GUI, el usuario normalmente ingresa credenciales desde la interfaz.

### Tests

Ejecutar la suite:

```bash
python -m pytest tests/ -q
```

En ambientes sin display, usar:

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q
```

### Type Check

El proyecto se viene validando con Pyright:

```bash
npx pyright .
```

### Build Local

Instalar dependencias de build:

```bash
python -m pip install -r requirements.txt -r requirements-build.txt
```

Generar binario local:

```bash
pyinstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name Scrappy \
  --hidden-import keyring.backends.chainer \
  --hidden-import keyring.backends.fail \
  --hidden-import keyring.backends.null \
  --hidden-import keyring.backends.macOS \
  --hidden-import keyring.backends.Windows \
  --hidden-import keyring.backends.SecretService \
  --hidden-import keyring.backends.kwallet \
  main.py
```

Empaquetar:

```bash
python scripts/package_artifact.py
```

El zip queda en:

```text
artifacts/
```

En macOS, el script usa `ditto` para preservar symlinks y metadata de `.app`. Esto es importante porque frameworks como `Python.framework` y Qt usan symlinks internos; si se rompen, macOS puede marcar la app como dañada.

## Builds Y Releases

Los binarios oficiales se generan con GitHub Actions en:

```text
.github/workflows/build-binaries.yml
```

El workflow se dispara:

- Manualmente con `workflow_dispatch`.
- Automáticamente al pushear tags que empiecen con `v`.

Ejemplo:

```bash
git tag -a v0.1.3 -m "Scrappy v0.1.3"
git push origin v0.1.3
```

Matriz actual:

- Ubuntu 22.04: `Scrappy-linux.zip`
- Windows Server 2022: `Scrappy-windows.zip`
- macOS 14 Apple Silicon: `Scrappy-macos-apple-silicon.zip`

Pasos principales del workflow:

1. Checkout.
2. Setup Python 3.11.
3. Instalación de dependencias.
4. Instalación de librerías Qt runtime en Linux.
5. Ejecución de tests.
6. Build con PyInstaller.
7. Firma ad-hoc del `.app` en macOS.
8. Empaquetado.
9. Verificación del zip macOS descomprimido con `codesign --verify`.
10. Upload de artifacts.
11. Upload al GitHub Release cuando el workflow corre sobre un tag.

## Arquitectura

```text
Scrappy/
├── main.py
├── gui/
│   ├── main_window.py
│   ├── workers.py
│   ├── sidebar.py
│   ├── theme.py
│   └── panels/
│       ├── conexion.py
│       ├── materias.py
│       ├── configuracion.py
│       └── registro.py
├── scraper/
│   ├── api.py
│   ├── auth.py
│   ├── navigator.py
│   ├── parser.py
│   └── models.py
├── utils/
│   └── config.py
├── scripts/
│   └── package_artifact.py
├── tests/
├── requirements.txt
├── requirements-build.txt
└── README.md
```

### `main.py`

Punto de entrada. Decide entre GUI y CLI según si el proceso recibe argumentos.

### `gui/main_window.py`

Ventana principal PyQt6. Coordina:

- Estado de conexión.
- Navegación entre paneles.
- Inicio de workers.
- Persistencia de carpeta de salida.
- Guardado opcional de credenciales.

### `gui/workers.py`

Workers basados en `QThread` para no bloquear la UI:

- `FetchMateriasWorker`: autentica y lista materias.
- `ScraperWorker`: ejecuta descarga y emite progreso.

### `gui/panels/`

Paneles visuales:

- `conexion.py`: login.
- `materias.py`: selección de materias y modo de descarga.
- `configuracion.py`: carpeta de salida y headless.
- `registro.py`: logs de ejecución.

### `scraper/api.py`

Cliente Moodle Web Services. Convierte respuestas de Moodle a modelos internos:

- Cursos a `Materia`.
- Secciones a `Modulo`.
- Archivos y actividades a `Recurso`.

También clasifica tipos de recurso desde `modname`, URL y extensión.

### `scraper/auth.py`

Autenticación:

- `get_moodle_token`: obtiene token del servicio `moodle_mobile_app`.
- `MoodleAuthenticator`: login Selenium.

### `scraper/navigator.py`

Orquestador principal. Decide entre API y Selenium, maneja manifest, descargas paralelas, exportación, sanitización de rutas y sesiones de descarga.

### `scraper/parser.py`

Parser HTML usado por Selenium. Extrae materias, módulos y recursos desde páginas Moodle renderizadas.

### `scraper/models.py`

Dataclasses de dominio:

- `Materia`
- `Modulo`
- `Recurso`
- `TipoRecurso`

### `utils/config.py`

Configuración central:

- URLs de Moodle.
- Variables de entorno.
- Módulos excluidos.
- Timeout.
- Carpeta y archivo de salida por defecto.

### `scripts/package_artifact.py`

Empaqueta los outputs de PyInstaller. Usa:

- `ditto` en macOS `.app`.
- `shutil.make_archive` en Linux/Windows.

## Flujo Interno De Descarga

### Camino API

1. La GUI pide usuario y contraseña.
2. `FetchMateriasWorker` intenta obtener token con `login/token.php`.
3. Si hay token:
   - Se consulta `core_webservice_get_site_info`.
   - Se listan cursos con `core_enrol_get_users_courses`.
   - Se muestran materias en la UI.
4. Al iniciar descarga:
   - `MoodleScraper` usa `core_course_get_contents`.
   - Convierte secciones y módulos a modelos internos.
   - Aplica filtros y modo incremental.
   - Descarga archivos con `requests`.
   - Exporta JSON/TXT.
   - Actualiza manifest.

### Camino Selenium

1. Si no hay token, Scrappy inicializa Chrome.
2. Hace login en Moodle.
3. Lee materias desde el dashboard.
4. Lee módulos desde cada curso.
5. Extrae recursos del HTML.
6. Crea una sesión `requests` con cookies del navegador.
7. Descarga archivos en paralelo.
8. Exporta JSON/TXT y actualiza manifest.

## Módulos Excluidos

Por defecto, Scrappy ignora módulos cuyo nombre contenga, normalizado sin tildes:

- `presentacion`
- `presentacion materia`
- `para estudiantes`
- `biblioteca`

Esto excluye módulos completos, no archivos individuales. Por ejemplo, un PDF llamado “Presentacion de la Unidad” dentro de un módulo válido no debería excluirse solo por el nombre del archivo.

## Seguridad Y Privacidad

- Scrappy corre localmente.
- No envía credenciales a servicios propios del proyecto.
- Las credenciales se usan contra Moodle UCC.
- El recordatorio opcional usa el almacén seguro del sistema mediante `keyring`.
- La carpeta `config/user_settings.json` guarda configuración local, no contraseñas.
- Los recursos descargados quedan en la carpeta elegida por el usuario.

## Limitaciones Conocidas

- La cobertura depende de cómo Moodle exponga cada recurso.
- Algunos enlaces externos no se descargan como archivo; se registran o se guardan como acceso directo.
- Google Drive no se descarga directamente en todos los casos por restricciones propias de Drive.
- Si Moodle cambia su HTML, el fallback Selenium puede requerir ajustes.
- Si Moodle cambia o deshabilita Web Services, el camino API puede dejar de estar disponible.
- macOS todavía puede advertir que la app no está notarizada.
- No hay actualización automática dentro de la app todavía.

## Troubleshooting

### “No se encontraron materias”

Posibles causas:

- Credenciales incorrectas.
- Usuario sin cursos activos.
- Moodle no entregó token y Selenium no pudo leer el dashboard.
- Cambios en el HTML del dashboard.

Probar:

```bash
python main.py
```

Y revisar el panel de registro o la salida de consola.

### Error De Autenticación

Verificar:

- Usuario y contraseña.
- Acceso manual a Moodle desde navegador.
- Estado de la cuenta UCC.
- Que no haya un segundo factor o flujo no soportado por Selenium.

### ChromeDriver O Chrome

El fallback Selenium requiere Google Chrome. `webdriver-manager` descarga el driver compatible, pero Chrome debe estar instalado.

Si falla:

- Actualizar Chrome.
- Reintentar.
- Ejecutar en modo visible para ver dónde queda detenido.

### macOS Dice Que La App Está Dañada

Usar el zip más reciente del release. A partir de `v0.1.2`, el build de macOS verifica el `.app` empaquetado con `codesign --verify` antes de publicarlo.

Si macOS sigue bloqueando:

1. Extraer el zip con Finder.
2. Mover `Scrappy.app` a `Applications`.
3. Click derecho sobre la app.
4. Elegir **Open/Abrir**.

Si el bloqueo persiste por cuarentena, se puede remover manualmente:

```bash
xattr -dr com.apple.quarantine /Applications/Scrappy.app
```

Usar ese comando solo si se confía en el binario descargado.

### Permisos De Escritura

Si no descarga archivos:

- Revisar que la carpeta de salida exista.
- Revisar permisos de escritura.
- Probar con `Downloads` o `Desktop`.

### Descarga Incompleta

Posibles causas:

- Recursos externos que no son descargables directamente.
- Sesión expirada.
- Cambios en URLs de Moodle.
- Restricciones del servidor.
- Archivos protegidos por una vista HTML intermedia no soportada.

Reintentar en modo “Forzar descarga completa” puede ayudar si el manifest local quedó desactualizado.

### PyQt No Importa En Linux CI O Entornos Headless

Para tests:

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q
```

En Linux pueden hacer falta librerías del sistema como:

- `libegl1`
- `libgl1`
- `libdbus-1-3`
- `libxkbcommon-x11-0`
- `libxcb-cursor0`

## Roadmap

Próximas mejoras razonables:

- Aviso de actualización dentro de la app consultando GitHub Releases.
- Descarga asistida de nuevas versiones.
- Notarización macOS.
- Instaladores nativos.
- Mejor manejo de links externos.
- Más tests de integración para API y parser.
- Mejor reporte de recursos omitidos.
- Configuración editable para módulos excluidos.

## Contribución

El proyecto está orientado a uso personal/educativo. Si se hacen cambios, mantener estas reglas:

- No hardcodear credenciales.
- No subir archivos descargados de Moodle.
- No modificar permisos ni comportamiento remoto.
- Mantener tests para cambios de UI, API, packaging o parser.
- Validar builds de macOS preservando symlinks de `.app`.

Flujo recomendado:

```bash
python -m pytest tests/ -q
npx pyright .
```

## Licencia

Este proyecto se distribuye bajo licencia MIT. Ver `LICENSE`.
