# UI Redesign — Scrappy Moodle UCC

## Contexto

La UI actual (PyQt6) se percibe tosca: colores agresivos (navy/purple/teal), layout todo apilado en una sola ventana sin separación clara de secciones, lista de materias con scroll nativo antiestético, y dos checkboxes redundantes para la misma opción. El objetivo es rediseñar la UI con un estilo VS Code + macOS: dark neutro, sidebar de navegación, cards modernas para la selección de materias.

---

## Layout general

Ventana fija de 960×640px (mínimo 860×560). Sin header independiente — el nombre de la app vive en la sidebar.

```
┌──────────────────────────────────────────────┐
│  Sidebar (180px fija)  │  Contenido (flex)   │
└──────────────────────────────────────────────┘
```

La sidebar nunca se colapsa. El contenido es un `QStackedWidget` que swapea el panel activo.

---

## Paleta de colores

| Elemento            | Color     |
|---------------------|-----------|
| Fondo app           | `#1e1e1e` |
| Sidebar             | `#252526` |
| Cards / paneles     | `#2d2d2d` |
| Bordes              | `#3e3e42` |
| Texto principal     | `#cccccc` |
| Texto secundario    | `#858585` |
| Acento (azul)       | `#0078d4` |
| Éxito               | `#4ec9b0` |
| Error               | `#f44747` |
| Log terminal fondo  | `#060d1a` |
| Log terminal texto  | `#a3e635` |

Sin gradientes. Sin bordes redondeados exagerados (máximo 8px).

---

## Sidebar

- Ancho fijo: 180px
- Fondo: `#252526`
- Cabecera: nombre "Scrappy" con ícono pequeño, no clickeable
- 4 ítems de navegación: **Conexión**, **Materias**, **Configuración**, **Registro**
- Cada ítem: ícono (unicode o qtawesome) + etiqueta de texto
- Ítem activo: borde izquierdo 2px `#0078d4` + fondo `#37373d`
- Hover: fondo `#2a2d2e`
- Separador sutil entre cabecera y nav items

---

## Panel: Conexión

Primer panel visible al abrir la app. Si hay credenciales guardadas en keyring, se conecta automáticamente y navega a Materias sin intervención del usuario.

**Componentes:**
- Input "Usuario UCC" — fondo `#3c3c3c`, borde `#3e3e42`, focus borde `#0078d4`
- Input "Contraseña" — mismo estilo, `EchoMode.Password`
- Checkbox "Recordar en este dispositivo"
- Botón "Conectar" — full-width, altura 38px, azul `#0078d4`, border-radius 8px
- Línea de estado debajo del botón: dot de color + texto

**Estados del dot:**
- `#858585` — Desconectado
- `#0078d4` pulsando — Conectando...
- `#4ec9b0` — Conectado · API ✓
- `#f44747` — Error: credenciales inválidas

**Flujo:** Al conectar exitosamente, la sidebar navega automáticamente a Materias. No hay progress bar separada — el feedback es la línea de estado.

---

## Panel: Materias

Panel principal de selección y ejecución de descarga.

**Componentes:**
- Título "Materias" + contador "8 disponibles" + links "Todas · Ninguna" (texto clickeable, sin botón)
- Grilla de cards 2 columnas, scroll vertical si hay más de 6 materias
- Combo "Modo de descarga" — global para todas las materias seleccionadas
- Barra de progreso + estado — visibles solo durante la descarga
- Botón "Comenzar descarga" — full-width, azul; se deshabilita mientras corre (ScraperWorker no soporta cancelación)

**Cards de materias:**
- Tamaño: ~160×90px
- Click en cualquier parte de la card togglea selección
- Indicador de check en esquina superior derecha
- Seleccionada: borde `#0078d4`, fondo `#2a2d2e`
- Deseleccionada: borde `#3e3e42`, fondo `#252526`, texto `#858585` tachado
- Hover: fondo `#37373d`

**Modo de descarga (combo global):**
- "Actualizar (buscar cambios en módulos)" — `("update", True)`
- "Solo módulos nuevos" — `("update", False)`
- "Forzar descarga completa" — `("full", True)`

Se elimina la opción de modo por materia individual — era confusa y poco usada.

---

## Panel: Configuración

Ajustes persistentes de la app.

**Componentes:**
- Campo "Carpeta de destino": `QLineEdit` readonly + botón "Elegir" → `QFileDialog`. Se guarda automáticamente en `config/user_settings.json` al cambiar (comportamiento actual conservado).
- `QCheckBox` estilizado como toggle "Ocultar navegador" — reemplaza las dos checkboxes redundantes (headless + mostrar navegador). Un solo control, estado inicial desde `Config.HEADLESS`.
- Texto aclaratorio: "Cuando hay API activa el navegador no se usa de todas formas."

---

## Panel: Registro

Log de actividad full-height.

**Componentes:**
- Header: label "Registro de actividad" + botón "Limpiar" (ghost, pequeño)
- `QTextEdit` readonly, font monospace (Menlo/Consolas 11px), fondo `#060d1a`, texto `#a3e635`
- Auto-scroll al final en cada nueva línea
- La sidebar navega automáticamente a este panel cuando arranca la descarga

---

## Componentes reutilizables

- `SidebarButton(icon, label)` — botón de nav con estados active/hover
- `MateriaCard(materia)` — card clickeable con toggle interno
- `StatusDot(color)` — indicador circular animado (pulse cuando conectando)

---

## Comportamiento de auto-navegación

| Evento | Navegación automática |
|---|---|
| App abre + credenciales guardadas | Login silencioso → Materias |
| Login exitoso | → Materias |
| Inicio de descarga | → Registro |
| Fin de descarga | permanece en Registro |

---

## Qué no cambia

- Lógica de `ScraperWorker`, `FetchMateriasWorker`, `MoodleScraper` — sin tocar
- Guardado de credenciales en keyring
- Guardado de ruta de destino en `config/user_settings.json`
- Log verde sobre negro — apropiado para output técnico
