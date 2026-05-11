# Scrapper Moodle UCC

Scrapper automatizado (con GUI) para extraer recursos educativos de la plataforma Moodle de la Universidad Católica de Córdoba.

## Características

- Autenticación automática en Moodle (puede recordar credenciales con keyring).
- Reutiliza la última carpeta de destino seleccionada (persistida en `config/user_settings.json`).
- Scraping paralelo (3–4 navegadores en paralelo) y descargas en paralelo con `requests`.
- Modos por materia: actualizar (solo cambios), solo módulos nuevos o forzar descarga completa.
- Manifiesto por materia (`output/config/manifest.json`) para detectar cambios y saltar módulos sin novedades.
- Identificación de recursos: PDFs, PPT/PPTX, Word, YouTube, enlaces externos, pluginfile, Google Drive (guardados como accesos directos `.url`), carpetas y archivos genéricos.
- Exporta resultados en JSON y TXT. Descarga archivos a `output/` organizados por materia/módulo.
- Filtrado de módulos no relevantes (Presentación, Para estudiantes, Biblioteca).
- Headless opcional.

## Requisitos

- Python 3.8 o superior
- Google Chrome instalado

## Instalación

1. Clonar o descargar este repositorio
2. Crear un entorno virtual (recomendado):
```bash
python -m venv venv
```
3. Activar el entorno virtual:
   - Windows:
   ```bash
   venv\Scripts\activate
   ```
   - Linux/Mac:
   ```bash
   source venv/bin/activate
   ```
4. Instalar dependencias:
```bash
pip install -r requirements.txt
```

5. (Opcional) Configurar credenciales:
   - Copiar `.env.example` a `.env`
   - Completar con tus credenciales de Moodle

## Uso

Ejecuta la GUI:
```bash
python main.py
```

En la interfaz podrás:
- Ingresar credenciales (opcionalmente recordarlas).
- Seleccionar materias y aplicar modos de scraping (actualizar, solo módulos nuevos o completa).
- Elegir la carpeta de destino (se recuerda para el próximo inicio).
- Iniciar en modo headless o visible.

## Builds para compartir

El proyecto genera un artefacto por sistema operativo con GitHub Actions:

- `Scrappy-linux.zip`
- `Scrappy-windows.zip`
- `Scrappy-macos-intel.zip`
- `Scrappy-macos-apple-silicon.zip`

Para crear builds multiplataforma:

1. Subir los cambios a GitHub.
2. Ir a **Actions → Build binaries → Run workflow**.
3. Descargar el zip correspondiente desde los artifacts del workflow.

También se puede disparar creando un tag:

```bash
git tag v0.1.0
git push origin v0.1.0
```

Build local para probar en tu sistema:

```bash
python -m pip install -r requirements.txt -r requirements-build.txt
pyinstaller --noconfirm --clean --windowed --name Scrappy main.py
python scripts/package_artifact.py
```

Notas:
- Cada plataforma debe compilarse en su propio sistema operativo; PyInstaller no genera `.exe` de Windows desde macOS ni binario Linux desde Windows.
- Los usuarios siguen necesitando Google Chrome instalado para el fallback Selenium. Cuando la API está disponible, el navegador no se usa.
- En macOS, si Gatekeeper bloquea la app por no estar firmada, abrir con click derecho → **Open/Abrir** la primera vez.

## Salida

Se organizan carpetas por materia y módulo en `output/` y se exporta:

1. `recursos_encontrados.json`: Formato JSON estructurado con todos los recursos
2. `recursos_encontrados.txt`: Formato texto legible con organización por materia y módulo

## Estructura del proyecto

```
uniscrapper/
├── main.py                 # Punto de entrada
├── scraper/
│   ├── __init__.py
│   ├── auth.py            # Autenticación en Moodle
│   ├── navigator.py       # Navegación y orquestación
│   ├── parser.py          # Parsing del HTML
│   └── models.py          # Modelos de datos
├── utils/
│   ├── __init__.py
│   └── config.py          # Configuración
├── output/                # Resultados del scraping
├── requirements.txt       # Dependencias
└── README.md             # Este archivo
```

## Notas importantes

- Este scrapper fue autorizado por la UCC para uso personal
- Las credenciales nunca se almacenan en el código
- El navegador se cierra automáticamente al finalizar
- Los módulos "Presentación", "Para estudiantes" y "Biblioteca" se excluyen automáticamente

## Solución de problemas

### Error: ChromeDriver no encontrado
El script descarga automáticamente el driver correcto. Si falla, verifica que tienes Chrome instalado.

### Error de autenticación
Verifica que tus credenciales sean correctas y que tu cuenta esté activa en Moodle.

### Timeout en scraping
Aumenta el valor de `TIMEOUT` en `utils/config.py` si tu conexión es lenta.

## Licencia

MIT License.
