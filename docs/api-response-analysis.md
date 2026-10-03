# Análisis de la respuesta de Moodle

Fecha del análisis: 2026-09-10. Se inspeccionó la estructura de la API de Moodle UCC con una cuenta real, sin persistir credenciales, tokens, nombres de materias, URLs ni respuestas completas.

## Respuesta base observada

`core_course_get_contents` devolvió:

| Dato | Cantidad |
|---|---:|
| Materias | 13 |
| Secciones | 156 |
| Actividades | 459 |
| Elementos `contents.type=file` | 351 |
| Elementos `contents.type=url` | 25 |
| Actividades sin `contents` | 151 |
| Módulos visibles pero no accesibles | 4 |

Tipos de actividad observados: `assign`, `folder`, `forum`, `label`, `page`, `questionnaire`, `quiz`, `resource`, `subsection` y `url`.

Los 351 archivos incluyen PDF, PPTX, DOCX, XLSX, imágenes, videos MP4, ZIP, HTML, CSV y archivos de código. Veinte viven dentro de subcarpetas de Moodle.

## Por qué la implementación Python perdía archivos

1. **Ignoraba `contents.type=url`.** Cuando un módulo tenía `contents`, el conversor sólo aceptaba elementos con `type == "file"`. Los 25 enlaces URL observados se descartaban completos.

2. **Consultaba una vista parcial.** Las 65 tareas no tenían `contents` en el endpoint base, pero `mod_assign_get_assignments` expuso 105 archivos en `introfiles`. También apareció un archivo de etiqueta y dos entradas adicionales mediante APIs específicas de módulo.

3. **Excluía secciones válidas por nombre.** Los filtros predeterminados coincidieron con 38 secciones. Dentro de ellas había al menos 28 archivos y 6 enlaces. Los filtros se superponían y usaban coincidencia por subcadena, por lo que el descarte era silencioso y amplio.

4. **El manifiesto se actualizaba antes de validar descargas.** Aunque una descarga fallara o fuera ignorada, el hash remoto del módulo quedaba guardado. La ejecución siguiente veía el mismo hash y omitía el módulo, incluso si el archivo nunca había llegado al disco.

5. **Los fallos parciales no cambiaban el resultado global.** Errores por materia y por archivo se capturaban, se mostraban como texto y la operación igualmente devolvía éxito.

6. **El contrato JSON no era estricto.** Esta instalación devuelve algunos flags como `0/1` y otros como booleanos. Python los coercionaba silenciosamente; un modelo Go inicialmente estricto permitió detectar la inconsistencia y ahora soporta ambas representaciones con prueba explícita.

7. **La identidad del archivo era insuficiente.** El hash anterior no incluía la subcarpeta. Archivos con igual nombre dentro de carpetas diferentes podían confundirse o terminar renombrados de manera no determinística.

8. **La descarga tenía filtros de URL silenciosos.** Varios tipos detectados no llegaban al downloader. Además, una sesión HTTP compartida entre threads se usaba concurrentemente sin garantías de seguridad.

## Verificación de APIs complementarias

La instancia habilita, entre otras, estas funciones relevantes:

- `mod_assign_get_assignments`
- `mod_book_get_books_by_courses`
- `mod_folder_get_folders_by_courses`
- `mod_forum_get_forums_by_courses`
- `mod_label_get_labels_by_courses`
- `mod_page_get_pages_by_courses`
- `mod_quiz_get_quizzes_by_courses`
- `mod_resource_get_resources_by_courses`
- `mod_url_get_urls_by_courses`

Al combinar la respuesta base con las APIs disponibles, procesar archivos/enlaces embebidos y deduplicar representaciones, el diagnóstico del core Go encontró 503 recursos únicos. Se deduplicaron 320 apariciones repetidas entre endpoints. La API señaló cuatro módulos inaccesibles; ninguno expuso un recurso descargable, por lo que no se generaron descargas inválidas para ellos.

Como verificación de autorización de descarga se tomó una muestra de diez archivos pequeños: cinco de la respuesta base y cinco adjuntos de tareas. Se solicitó únicamente el primer byte. Los diez respondieron como archivo (`200` o `206`), ninguno redirigió al login y todos entregaron contenido.

## Comportamiento corregido

- No hay secciones excluidas por defecto.
- Se procesan archivos, URLs, `introfiles`, `contentfiles` y vínculos relevantes del HTML.
- Se usa `course module id + filepath + filename` como identidad estable de archivo.
- El manifiesto v2 registra rutas locales por recurso sólo después de una escritura exitosa.
- Un archivo ausente o con tamaño incorrecto se vuelve a descargar aunque el metadato remoto no haya cambiado.
- Las rutas se planifican de forma determinística y preservan subcarpetas.
- Cada fallo queda en `sync-report.json` y provoca resultado parcial/fallido visible en la UI.
- El token sólo se agrega al host Moodle exacto y a endpoints de archivo de Web Services.

## Referencias del contrato

Moodle documenta que los archivos para clientes Web Services se sirven mediante `/webservice/pluginfile.php` y requieren token. También documenta que `core_course_get_contents` devuelve módulos y URLs de archivos, pero los archivos propios de cada actividad pueden aparecer en estructuras `external_files` de APIs específicas. Véase [File handling](https://moodledev.io/docs/5.0/apis/subsystems/external/files) y [Web service API functions](https://docs.moodle.org/dev/index.php?title=Web_service_API_functions).
