"""
Cliente Moodle Web Services — reemplaza Selenium para listado de cursos y extracción de recursos.
"""
import requests
from pathlib import Path
from typing import Any, List, cast
from scraper.models import Materia, Modulo, Recurso, TipoRecurso


_EXT_TIPO = {
    ".pdf": TipoRecurso.PDF,
    ".ppt": TipoRecurso.POWERPOINT,
    ".pptx": TipoRecurso.POWERPOINT,
    ".doc": TipoRecurso.WORD,
    ".docx": TipoRecurso.WORD,
    ".xls": TipoRecurso.ARCHIVO,
    ".xlsx": TipoRecurso.ARCHIVO,
}


def _tipo_desde_modulo(modname: str, url: str, contents: list) -> TipoRecurso:
    url_l = (url or "").lower()
    if "youtube.com" in url_l or "youtu.be" in url_l:
        return TipoRecurso.VIDEO_YOUTUBE
    if "drive.google.com" in url_l or "docs.google.com" in url_l:
        return TipoRecurso.GOOGLE_DRIVE
    if modname == "folder":
        return TipoRecurso.CARPETA
    if modname == "url":
        if "presencial.ucc.edu.ar" not in url_l:
            return TipoRecurso.LINK
        return TipoRecurso.ARCHIVO
    if modname == "resource" and contents:
        ext = Path(contents[0].get("filename", "")).suffix.lower()
        return _EXT_TIPO.get(ext, TipoRecurso.ARCHIVO)
    return TipoRecurso.ARCHIVO


def _tipo_desde_archivo(filename: str) -> TipoRecurso:
    ext = Path(filename or "").suffix.lower()
    return _EXT_TIPO.get(ext, TipoRecurso.ARCHIVO)


class MoodleAPIClient:
    """Cliente liviano para Moodle Web Services REST."""

    def __init__(self, token: str, base_url: str):
        self.token = token
        self.base_url = base_url.rstrip("/")
        # session: solo para llamadas POST a la API (wstoken va en el body)
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        # download_session: para GET de archivos (webservice/pluginfile.php requiere ?token en URL)
        self.download_session = requests.Session()
        self.download_session.params = {"token": token}

    def _call(self, function: str, **params) -> object:
        data = {
            "wstoken": self.token,
            "wsfunction": function,
            "moodlewsrestformat": "json",
        }
        data.update(params)
        resp = self.session.post(
            f"{self.base_url}/webservice/rest/server.php",
            data=data,
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        if isinstance(result, dict) and "exception" in result:
            raise RuntimeError(result.get("message") or result["exception"])
        return result

    def get_site_info(self) -> dict[str, Any]:
        return cast(dict[str, Any], self._call("core_webservice_get_site_info"))

    def get_enrolled_courses(self, userid: int) -> list:
        return cast(list[dict[str, Any]], self._call("core_enrol_get_users_courses", userid=userid))

    def get_course_contents(self, courseid: int) -> list:
        return cast(list[dict[str, Any]], self._call("core_course_get_contents", courseid=courseid))


def api_courses_to_materias(courses: list) -> List[Materia]:
    materias = []
    for c in courses:
        course_id = str(c.get("id", ""))
        nombre = c.get("fullname", "").strip()
        url = c.get("viewurl", "") or f"https://presencial.ucc.edu.ar/course/view.php?id={course_id}"
        if nombre and course_id:
            materias.append(Materia(nombre=nombre, url=url, id_curso=course_id))
    return materias


def api_contents_to_modulos(sections: list, materia: Materia, excluidos: List[str]) -> List[Modulo]:
    """
    Convierte secciones de core_course_get_contents a Modulo/Recurso.
    Excluidos: lista de nombres normalizados a ignorar (de Config.MODULOS_EXCLUIDOS).
    """
    import unicodedata

    def _normalizar(texto: str) -> str:
        texto = texto.lower()
        texto = unicodedata.normalize("NFD", texto)
        return "".join(c for c in texto if unicodedata.category(c) != "Mn")

    modulos = []
    for section in sections:
        nombre_seccion = (section.get("name") or "").strip()
        if not nombre_seccion:
            continue
        nombre_norm = _normalizar(nombre_seccion)
        if any(ex in nombre_norm for ex in excluidos):
            continue

        modulo = Modulo(nombre=nombre_seccion)
        for mod in section.get("modules") or []:
            modname = mod.get("modname", "")
            nombre_mod = (mod.get("name") or "").strip()
            mod_url = mod.get("url") or mod.get("fileurl") or ""
            contents = mod.get("contents") or []

            if not nombre_mod:
                continue

            # Módulos sin URL directa y sin archivos → skip
            if not mod_url and not contents:
                continue

            tipo = _tipo_desde_modulo(modname, mod_url, contents)

            if contents:
                # Moodle devuelve archivos de resources y folders en contents.
                for content in contents:
                    if content.get("type") == "file":
                        file_url = content.get("fileurl", mod_url)
                        file_name = content.get("filename") or nombre_mod
                        # "filepath" indica la subcarpeta dentro de un recurso folder (ej. "/Pila/").
                        # Sin esto, archivos con el mismo nombre en subcarpetas distintas
                        # (típico en carpetas de ejercicios: Pila/nodo.h, Cola/nodo.h, Hash/nodo.h)
                        # colisionan en el mismo directorio de salida y aparentan ser duplicados.
                        subcarpeta = (content.get("filepath") or "/").strip("/")
                        recurso = Recurso(
                            nombre=file_name,
                            url=file_url,
                            tipo=_tipo_desde_archivo(file_name),
                            modulo_nombre=nombre_seccion,
                            materia_nombre=materia.nombre,
                            subcarpeta=subcarpeta,
                        )
                        modulo.agregar_recurso(recurso)
            else:
                recurso = Recurso(
                    nombre=nombre_mod,
                    url=mod_url,
                    tipo=tipo,
                    modulo_nombre=nombre_seccion,
                    materia_nombre=materia.nombre,
                )
                modulo.agregar_recurso(recurso)

        if modulo.recursos:
            modulos.append(modulo)

    return modulos
