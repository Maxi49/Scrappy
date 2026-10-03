# Integración con Google Drive — Scrappy

## Contexto

Muchos profesores no suben el material a Moodle: publican en Moodle un link a una carpeta o archivo de Google Drive. Hoy el core detecta esos links (`classifyLink` → `ResourceGoogle` en `internal/moodle/catalog.go`) pero solo guarda un acceso directo `.url`; el contenido no se descarga.

Objetivo: descargar el contenido de Drive enlazado desde Moodle, con la misma estructura de carpetas, manifest y reporte que el resto, dejando que el usuario elija qué se descarga.

### Decisiones tomadas

- Los links salen **solo de Moodle** (no hay carga manual de links).
- Acceso **híbrido**: API key para lo compartido como "cualquiera con el enlace"; OAuth (scope `drive.readonly`) como respaldo para lo restringido a cuentas de la UCC.
- El proyecto OAuth queda en modo **Testing**: máximo 100 test users cargados a mano (suficiente: la app nunca va a superar ese número) y refresh token que vence a los 7 días (aceptado: el usuario reconecta).
- Archivos nativos de Google: Docs, Slides y Drawings → PDF; Sheets → `.xlsx`.
- La selección es **opt-in por link**: un link de Drive nuevo no descarga nada hasta que el usuario lo revisa; lo nuevo dentro de una carpeta ya seleccionada se descarga solo.
- Todo vive en el core de Go (CLAUDE.md). Python solo dibuja, abre el navegador y guarda el token en el keyring.
- Sin dependencias Go nuevas: REST de Drive y OAuth con `net/http`.

### Fuera de alcance

Pegar links a mano, revocar el token en Google, borrar archivos locales que desaparecieron de Drive, smoke test de Drive en el paquete.

---

## 1. Arquitectura

Paquete nuevo `internal/gdrive`:

| Archivo | Responsabilidad |
|---|---|
| `links.go` | Parsear un link de Drive → `(id, kind, resourceKey)` |
| `client.go` | Llamadas REST (`files.get`, `files.list`, `alt=media`, `export`) con API key o bearer; reintentos; redacción de secretos |
| `oauth.go` | Login loopback con PKCE, refresh del access token |
| `credentials.go` | `apiKey`, `clientID`, `clientSecret` (inyectados por `-ldflags -X`, fallback a env `SCRAPPY_GOOGLE_API_KEY`, `SCRAPPY_GOOGLE_CLIENT_ID`, `SCRAPPY_GOOGLE_CLIENT_SECRET`) |
| `tree.go` | Árbol escaneado (`drive-tree.json`) |
| `selection.go` | Reglas de selección (`drive-selection.json`) y su resolución |
| `expand.go` | Catálogo + árbol + selección → recursos descargables |
| `fetch.go` | Implementación de `syncer.Fetcher` |

Las URLs base de Drive y de los endpoints OAuth son variables del paquete para que los tests apunten a un `httptest.Server`.

Flujo del `sync` en `cmd/scrappy-core/main.go`:

```
moodle.Discover → gdrive.Expand → syncer.Run(…, Options{Fetcher: gdrive fetcher})
```

`internal/moodle` no conoce Drive. Si el build no tiene credenciales, `Expand` no hace nada salvo agregar un aviso en `diagnostics.warnings`; los `.url` se siguen guardando.

### Links soportados

`drive.google.com/drive/folders/X`, `drive.google.com/drive/u/N/folders/X`, `drive.google.com/file/d/X/…`, `drive.google.com/open?id=X`, `docs.google.com/{document,spreadsheets,presentation,drawings}/d/X/…`. Si el link trae `resourcekey=…`, se manda en el header `X-Goog-Drive-Resource-Keys` como `X/resourcekey`. Un link que no se puede parsear queda solo como `.url`.

### Recursos generados

Cada archivo de Drive seleccionado se agrega al catálogo como un `moodle.Resource`:

- `ID = stableID("gdrive|<courseID>|<fileId>")`: el mismo archivo enlazado dos veces en una materia se baja una vez.
- `CourseID`, `CourseName`, `ModuleName`: los del link de Moodle.
- `Subfolder = <nombre del link>/<ruta de carpetas en Drive>`. El contenido queda en `Materia/Sección/<nombre del link>/…`.
- `Name`: nombre en Drive, con `.pdf` / `.xlsx` agregado a los nativos.
- `URL = https://drive.google.com/file/d/<fileId>/view` (canónica, sin claves).
- `Size`: tamaño real; 0 para nativos. `Modified`: `modifiedTime` en Unix. `MIME`: el real o el de exportación.
- `Source = "google_drive"`, `Type` por extensión, `Accessible = true`.
- Campo nuevo `Drive *DriveRef` con `json:"-"` (`FileID`, `ResourceKey`, `ExportMIME`, `UseOAuth`), para que el `Fetcher` sepa cómo bajarlo.

El link original de Moodle sigue generando su `.url`.

El fingerprint existente (`syncer/paths.go`, combina URL, MIME, Size y Modified) no cambia: si el profesor edita el archivo, `modifiedTime` cambia y se vuelve a bajar. El formato del manifest (v2) no cambia.

---

## 2. OAuth

### Acción `google_login`

Request: `{"action":"google_login","cancel_on_stdin_close":true}`.

1. El core genera `code_verifier` (PKCE S256) y `state` aleatorio, abre un listener en `127.0.0.1:0`.
2. Emite `{"event":"open_url","url":"https://accounts.google.com/o/oauth2/v2/auth?…"}` con scopes `openid email https://www.googleapis.com/auth/drive.readonly`, `access_type=offline`, `prompt=consent`.
3. La UI abre la URL con `QDesktopServices.openUrl` y muestra el link para copiar por si el navegador no se abre.
4. En el callback el core valida `state`, intercambia el código en el endpoint de tokens y responde al navegador con una página "Listo, podés volver a Scrappy".
5. Resultado: `{"event":"result","ok":true,"refresh_token":"…","email":"…"}`. El email sale del payload del `id_token` (recibido por TLS directo de Google, no se verifica la firma).
6. Timeout de 5 minutos. Cancelación por cierre de stdin, igual que el sync. El listener siempre se cierra.

Errores de Google en el callback (`error=access_denied`, `admin_policy_enforced`, etc.) terminan en `ok:false` con un mensaje en castellano; si es política de la organización, se aclara que es un bloqueo del administrador de la UCC.

### Almacenamiento

La UI guarda en el keyring, servicio `scrappy_google`, las claves `refresh_token` y `email`. El refresh token viaja solo por stdin (campo `google_refresh_token`), nunca en argumentos ni logs.

### Uso en sync y drive_scan

El access token se pide de forma perezosa: solo cuando una llamada con API key devuelve 403 o 404 y hay refresh token. Se cachea durante la ejecución y se protege con mutex (workers concurrentes).

Si el refresh devuelve `invalid_grant` (venció a los 7 días o fue revocado), el resultado incluye `google_auth_expired: true`; los recursos que necesitaban OAuth fallan con *"La sesión de Google venció; reconectá Google en Conexión"*. Lo público sigue bajando con la API key. La UI borra el token del keyring y muestra "Sesión vencida".

### UI (panel Conexión)

Bloque "Google Drive" con estado (*No conectado* / *Conectado como x@…* / *Sesión vencida*) y botón "Conectar con Google" ↔ "Desconectar". Desconectar borra el keyring.

### Credenciales de la app

`scripts/build_core.py` lee `SCRAPPY_GOOGLE_API_KEY`, `SCRAPPY_GOOGLE_CLIENT_ID` y `SCRAPPY_GOOGLE_CLIENT_SECRET` del entorno y los pasa con `-ldflags -X`. En CI salen de secrets de GitHub. No se commitean.

Configuración manual en Google Cloud (la hace el usuario):
1. Proyecto nuevo, habilitar Google Drive API.
2. API key restringida a la Drive API.
3. OAuth client tipo "Desktop app"; consent screen External, en Testing, scopes `openid`, `email`, `drive.readonly`.
4. Cargar como test users los mails (la cuenta de la UCC de cada uno).

---

## 3. Descarga y exportación

| Tipo en Drive | Descarga | Archivo local |
|---|---|---|
| Archivo común | `GET files/{id}?alt=media` | nombre original |
| Google Docs / Slides / Drawings | `GET files/{id}/export?mimeType=application/pdf`; si responde `exportSizeLimitExceeded`, reintento por `exportLinks[application/pdf]` | `nombre.pdf` |
| Google Sheets | igual, con el MIME de `.xlsx` | `nombre.xlsx` |
| Forms, Sites, Maps, otros no exportables | no se descargan | `nombre.url` (recurso de tipo link) |
| Atajo (`application/vnd.google-apps.shortcut`) | se sigue a `shortcutDetails.targetId` | según el destino |
| En la papelera | se ignora (`trashed = false`) | — |

Todas las llamadas usan `supportsAllDrives=true` (y `includeItemsFromAllDrives=true` en `files.list`).

**Credencial por archivo:** la expansión anota en `DriveRef.UseOAuth` si la carpeta del link se leyó con OAuth; la descarga usa la misma credencial.

**Integración con el syncer:** `syncer.Options` suma `Fetcher`:

```go
type Fetcher interface {
    Open(ctx context.Context, resource moodle.Resource) (io.ReadCloser, int64, error)
}
```

El worker de `syncer.Run` usa el `Fetcher` cuando `resource.Drive != nil` y escribe con el `copyAtomically` existente (`.part` temporal, chequeo de tamaño, rename atómico). Reintentos: 3 intentos con backoff ante 429, 5xx y 403 `rateLimitExceeded` / `userRateLimitExceeded`.

**Secretos:** ningún error que llegue a la UI o al reporte incluye la API key, el access token ni el refresh token (mismo criterio que `redactURLError`).

Archivos quitados de Drive: igual que con Moodle, el archivo local queda.

---

## 4. Selección de Drive

### Reglas (`<output>/.scrappy/drive-selection.json`)

```json
{"version": 1, "rules": {"<driveId>": "include", "<driveId>": "exclude"}}
```

Resolución para un nodo: se sube por sus ancestros (incluido el propio nodo) y **gana la regla más cercana**. Si se llega a la raíz (el link de Moodle) sin regla, el nodo **no se descarga** y la raíz se marca como *nuevo*. Al guardar desde el panel, cada raíz visible queda con regla explícita (`include` o `exclude`) y deja de ser nueva.

Consecuencias:
- Un archivo nuevo dentro de una carpeta incluida se descarga solo.
- Un link nuevo en Moodle no descarga nada hasta revisarlo.

### Árbol (`<output>/.scrappy/drive-tree.json`)

Lista de raíces (una por link de Moodle) con `id`, `course_id`, `materia`, `modulo`, `link_name`, `new`, `oauth`, `error` (motivo si no se pudo leer) y `node`, un árbol anidado: `id`, `name`, `kind` (folder/file/link), `mime`, `size` (0 si es nativo o desconocido), `modified`, `children`. Incluye `scanned_at`. Un `sync` o `drive_scan` reemplaza solo las raíces de las materias que analizó (`MergeTree`).

### Protocolo

- **`drive_scan`**: mismos campos que `sync` (credenciales de Moodle, `courses`, `output_path`, `google_refresh_token`). Corre `Discover`, lista **todas** las raíces completas, guarda `drive-tree.json` y devuelve `{"event":"result","ok":true,"tree":…,"rules":…,"google_auth_expired":…}`.
- **`drive_state`**: `{output_path}` → último árbol y reglas guardados, sin red. Lo usa el panel al abrirse, así Python no lee archivos de `.scrappy/`.
- **`drive_selection_save`**: `{"action":"drive_selection_save","output_path":…,"rules":{…}}`. El core valida y escribe atómicamente.
- **`sync`**: lista solo las carpetas cuyo estado efectivo es `include` o que son ancestros (según `drive-tree.json`) de una regla `include`. Para las raíces nuevas solo pide los metadatos de la raíz. Actualiza en `drive-tree.json` los subárboles que listó y conserva el resto del snapshot anterior.

### Panel "Drive" (barra lateral, debajo de Materias)

- `QTreeWidget` con checkboxes de tres estados; columnas Nombre y Tamaño (`—` para nativos). Primer nivel: materias; luego links, carpetas y archivos.
- Raíces nuevas con etiqueta "nuevo". Raíces inaccesibles en gris con el motivo (p. ej. *"Requiere conectar Google"*).
- Al abrir muestra el último `drive-tree.json` y la fecha de análisis, sin escanear.
- Pie: *"Seleccionado: 1,3 GB de 9,8 GB"*, botones **Analizar Drive** y **Guardar selección**.
- La UI calcula las reglas mínimas a partir de los checks (una regla por raíz; más reglas solo donde un hijo difiere de su padre) y las manda con `drive_selection_save`. Una carpeta parcialmente marcada conserva su regla anterior (o la última vez que se la marcó/desmarcó entera), así lo que el profe agregue después sigue esa regla.
- "Analizar Drive" usa las materias marcadas en Materias, o todas si no hay ninguna marcada; requiere estar conectado a Moodle.
- Salir del panel con cambios sin guardar pide confirmación.

---

## 5. Errores y reporte

- **Raíz ilegible:** una sola falla por link, con mensaje accionable:
  - privada y sin sesión: *"Esta carpeta de Drive es privada; conectá Google en Conexión"*;
  - con sesión pero sin acceso: *"Tu cuenta de Google no tiene acceso; ¿es la cuenta de la UCC?"* (el core no conoce el email);
  - sesión vencida: *"La sesión de Google venció; reconectá Google en Conexión"*.
- **Archivo puntual:** falla normal del reporte; el sync termina en `partial`.
- **Reporte:** campos nuevos `drive_unreviewed` (raíces nuevas sin revisar) y `google_auth_expired`. Lo descargado de Drive ya aparece en `resources_by_source["google_drive"]`.
- **`summarize_report`** (`gui/workers.py`): línea *"N carpetas de Drive nuevas sin revisar; revisalas en el panel Drive"* y, si corresponde, *"La sesión de Google venció"*.
- **Progreso:** *"Drive: listando «…»…"* por raíz. La expansión respeta la cancelación.
- El listado recursivo evita ciclos con un set de IDs visitados.

---

## 6. Tests

**Go** (`httptest` simulando Drive y el endpoint de tokens):
- Parseo de links (tabla), con y sin `resourcekey`.
- Listado recursivo y paginado; atajos; papelera; ciclos.
- API key → 403 → OAuth → OK; `invalid_grant` → `google_auth_expired`.
- Export con `exportSizeLimitExceeded` → `exportLinks`; Forms → `.url`.
- Redacción de API key y tokens en errores.
- Login: callback válido, `state` distinto rechazado, error de Google, timeout, cancelación.
- Resolución de reglas: la más cercana gana, raíz sin regla no baja, archivo nuevo en carpeta incluida baja.
- `syncer` con `Fetcher` falso: re-sync sin cambios → "sin cambios"; cambio de `modifiedTime` → se vuelve a bajar.
- `protocol_test`: `google_login`, `drive_scan`, `drive_selection_save`, `sync` con `google_refresh_token`.

**Python:**
- Bloque Google en Conexión (tres estados), evento `open_url` en el bridge, keyring (mock).
- Panel Drive: tres estados, reglas mínimas al guardar, confirmación al salir sin guardar.
- Líneas nuevas de `summarize_report`.

**Prueba real temprana:** apenas exista `google_login`, el usuario lo prueba con su cuenta de la UCC para descartar un bloqueo del administrador de Workspace antes de construir el resto.
