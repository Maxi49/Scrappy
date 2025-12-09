# Scrapper Moodle UCC

Scrapper automatizado para extraer recursos educativos de la plataforma Moodle de la Universidad Católica de Córdoba.

## Características

- Autenticación automática en Moodle
- Extracción de todas las materias del usuario
- Navegación automática por módulos de cada materia
- Identificación de diferentes tipos de recursos:
  - PDFs
  - PowerPoint
  - Documentos Word
  - Videos de YouTube
  - Enlaces externos
  - Carpetas y archivos genéricos
- Exportación de resultados en JSON y TXT
- Filtrado de módulos no relevantes (Presentación, Para estudiantes, Biblioteca)

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

### Modo básico (pedirá credenciales por consola):
```bash
python main.py
```

### Con credenciales por argumentos:
```bash
python main.py --username tu_usuario --password tu_contraseña
```

### Modo headless (sin interfaz gráfica):
```bash
python main.py --headless
```

### Sin exportar resultados:
```bash
python main.py --no-export
```

## Salida

El scrapper genera dos archivos en la carpeta `output/`:

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

Este proyecto es de uso educativo y personal.
