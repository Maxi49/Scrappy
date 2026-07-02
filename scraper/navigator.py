"""
Navegador principal del scrapper
"""
import concurrent.futures
import hashlib
import json
import math
import os
import platform
import re
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, unquote

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from scraper.api import MoodleAPIClient, api_courses_to_materias, api_contents_to_modulos
from scraper.auth import MoodleAuthenticator
from scraper.models import Materia, Modulo, Recurso, TipoRecurso
from scraper.parser import MoodleParser
from utils.config import Config

from typing import Any, Callable, List, Optional


def _module_key(nombre: str) -> str:
    return re.sub(r"\s+", " ", nombre.strip().lower())


def _materia_key(materia) -> str:
    return (materia.id_curso or materia.nombre).strip().lower()


def _hash_recursos(recursos: List[Recurso]) -> str:
    hasher = hashlib.md5()
    for r in sorted(recursos, key=lambda x: (x.nombre, x.url, x.tipo.value)):
        hasher.update(r.nombre.encode("utf-8", errors="ignore"))
        hasher.update(r.url.encode("utf-8", errors="ignore"))
        hasher.update(r.tipo.value.encode("utf-8", errors="ignore"))
    return hasher.hexdigest()


def _scrapear_lote_worker(payload):
    """Worker en proceso separado: login propio y scraping de un lote de materias (fallback Selenium)."""
    materias, username, password, headless, materia_modes, manifest_snapshot = payload
    scraper = MoodleScraper(headless=headless)
    scraper.progress_cb = None
    recursos = []
    materias_resultado = []
    manifest_updates = []
    try:
        scraper.inicializar_driver()
        if not scraper.login(username, password):
            return [], [], []
        assert scraper.parser is not None
        for materia in materias:
            try:
                mkey = _materia_key(materia)
                mode_cfg = materia_modes.get(materia.nombre, {"mode": "update", "scan_existing": True})
                prev_modules = manifest_snapshot.get(mkey, {}).get("modulos", {})

                modulos = scraper.parser.obtener_modulos(materia)
                materia.modulos = modulos
                for modulo in modulos:
                    mk = _module_key(modulo.nombre)
                    if mode_cfg["mode"] == "update" and not mode_cfg.get("scan_existing", True):
                        if mk in prev_modules:
                            continue
                    recursos_modulo = scraper.parser.extraer_recursos_modulo(materia, modulo)
                    modulo.recursos = recursos_modulo
                    if mode_cfg["mode"] == "update" and mode_cfg.get("scan_existing", True):
                        new_hash = _hash_recursos(recursos_modulo)
                        prev_hash = prev_modules.get(mk, {}).get("hash")
                        if prev_hash and prev_hash == new_hash:
                            continue
                        manifest_updates.append({"materia_key": mkey, "module_key": mk, "module_name": modulo.nombre, "hash": new_hash, "recursos": recursos_modulo})
                        recursos.extend(recursos_modulo)
                    else:
                        new_hash = _hash_recursos(recursos_modulo)
                        manifest_updates.append({"materia_key": mkey, "module_key": mk, "module_name": modulo.nombre, "hash": new_hash, "recursos": recursos_modulo})
                        recursos.extend(recursos_modulo)
                materias_resultado.append(materia)
            except Exception:
                continue
        return materias_resultado, recursos, manifest_updates
    finally:
        scraper.cerrar()


class MoodleScraper:
    """Scrapper principal para Moodle UCC"""

    def __init__(
        self,
        headless: Optional[bool] = None,
        user_agent: Optional[str] = None,
        api_token: Optional[str] = None,
    ):
        self.config = Config()
        self.headless = headless if headless is not None else self.config.HEADLESS
        self.user_agent_override = user_agent
        self.api_token = api_token or ""
        self.driver: Optional[webdriver.Chrome] = None
        self.authenticator: Optional[MoodleAuthenticator] = None
        self.parser: Optional[MoodleParser] = None
        self.session: Optional[requests.Session] = None
        self.progress_cb: Optional[Callable[[str], None]] = None
        self._path_lock = threading.Lock()
        self._reserved_paths: set = set()

    def _notify(self, message: str):
        print(message)
        if self.progress_cb:
            try:
                self.progress_cb(message)
            except Exception:
                pass

    def _load_manifest(self, base_dir: Path):
        path = Path(base_dir) / "config" / "manifest.json"
        if not path.exists():
            return {"materias": {}}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"materias": {}}

    def _save_manifest(self, manifest: dict, base_dir: Path):
        config_dir = Path(base_dir) / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        path = config_dir / "manifest.json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def inicializar_driver(self):
        """Inicializa el driver de Selenium"""
        self._notify("Inicializando navegador...")

        options = Options()
        if self.headless:
            options.add_argument("--headless")
        if self.user_agent_override:
            options.add_argument(f"--user-agent={self.user_agent_override}")

        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-gpu")
        options.add_argument("--blink-settings=imagesEnabled=false")
        options.add_argument("--disable-notifications")

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.driver.maximize_window()
        self.authenticator = MoodleAuthenticator(self.driver)
        self.parser = MoodleParser(self.driver)

        self._notify("Navegador inicializado correctamente")

    def login(self, username: Optional[str] = None, password: Optional[str] = None) -> bool:
        assert self.authenticator is not None
        ok = self.authenticator.login(username, password)
        self._notify("Login exitoso" if ok else "Login fallido")
        return ok

    def exportar_recursos(self, recursos: List[Recurso], formato: str = "json"):
        os.makedirs(self.config.OUTPUT_DIR, exist_ok=True)

        if formato == "json":
            output_path = os.path.join(self.config.OUTPUT_DIR, self.config.OUTPUT_FILE)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump([r.to_dict() for r in recursos], f, ensure_ascii=False, indent=2)
            print(f"\n✓ Recursos exportados a: {output_path}")

        elif formato == "txt":
            output_path = os.path.join(self.config.OUTPUT_DIR, "recursos_encontrados.txt")
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("RECURSOS ENCONTRADOS EN MOODLE UCC\n")
                f.write("=" * 80 + "\n\n")
                materia_actual = None
                modulo_actual = None
                for recurso in recursos:
                    if recurso.materia_nombre != materia_actual:
                        materia_actual = recurso.materia_nombre
                        f.write(f"\n{'='*80}\nMATERIA: {materia_actual}\n{'='*80}\n")
                    if recurso.modulo_nombre != modulo_actual:
                        modulo_actual = recurso.modulo_nombre
                        f.write(f"\n  MÓDULO: {modulo_actual}\n  {'-'*76}\n")
                    f.write(f"    - {recurso.nombre}\n      Tipo: {recurso.tipo.value}\n      URL: {recurso.url}\n\n")
            print(f"\n✓ Recursos exportados a: {output_path}")

    def cerrar(self):
        if self.driver:
            self.driver.quit()
            self.driver = None

    def obtener_materias_con_credenciales(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> List[Materia]:
        """Fallback Selenium: inicia sesión y lista materias."""
        materias = []
        try:
            self.inicializar_driver()
            if not self.login(username, password):
                return materias
            assert self.parser is not None
            materias = self.parser.obtener_materias()
            self._notify(f"Materias encontradas: {len(materias)}")
        finally:
            self.cerrar()
        return materias

    # ------------------------------------------------------------------ #
    # Camino rápido: API
    # ------------------------------------------------------------------ #
    def ejecutar_con_api(
        self,
        username: str,
        password: str,
        exportar: bool,
        materias: List[Materia],
        materia_modes: dict[str, Any],
        base_dir: Path,
    ) -> bool:
        client = MoodleAPIClient(self.api_token, self.config.BASE_URL)
        manifest = self._load_manifest(base_dir)
        manifest_materias = manifest.setdefault("materias", {})

        recursos_totales: List[Recurso] = []
        manifest_updates = []

        self._notify(f"Buscando contenidos de {len(materias)} materias vía API...")

        def _fetch_materia(materia: Materia):
            if not materia.id_curso:
                return materia, [], []
            try:
                courseid = int(materia.id_curso)
            except (TypeError, ValueError):
                return materia, [], []

            mode_cfg = materia_modes.get(materia.nombre, {"mode": "update", "scan_existing": True})
            mkey = _materia_key(materia)
            prev_modules = manifest_materias.get(mkey, {}).get("modulos", {})

            sections = client.get_course_contents(courseid)
            modulos = api_contents_to_modulos(sections, materia, self.config.MODULOS_EXCLUIDOS)
            materia.modulos = modulos

            recursos: List[Recurso] = []
            updates = []
            for modulo in modulos:
                mk = _module_key(modulo.nombre)
                if mode_cfg["mode"] == "update" and not mode_cfg.get("scan_existing", True):
                    if mk in prev_modules:
                        continue
                if mode_cfg["mode"] == "update" and mode_cfg.get("scan_existing", True):
                    new_hash = _hash_recursos(modulo.recursos)
                    prev_hash = prev_modules.get(mk, {}).get("hash")
                    if prev_hash and prev_hash == new_hash:
                        continue
                    updates.append({"materia_key": mkey, "module_key": mk, "module_name": modulo.nombre, "hash": new_hash, "recursos": modulo.recursos})
                    recursos.extend(modulo.recursos)
                else:
                    new_hash = _hash_recursos(modulo.recursos)
                    updates.append({"materia_key": mkey, "module_key": mk, "module_name": modulo.nombre, "hash": new_hash, "recursos": modulo.recursos})
                    recursos.extend(modulo.recursos)
            return materia, recursos, updates

        # Fetch de contenidos en paralelo (I/O puro, ThreadPool suficiente)
        max_api_workers = min(8, len(materias))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_api_workers) as pool:
            futures = {pool.submit(_fetch_materia, m): m for m in materias}
            for future in concurrent.futures.as_completed(futures):
                try:
                    materia, recursos, updates = future.result()
                    recursos_totales.extend(recursos)
                    manifest_updates.extend(updates)
                    self._notify(f"✓ {materia.nombre}: {len(recursos)} recursos")
                except Exception as e:
                    self._notify(f"Error en {futures[future].nombre}: {e}")

        # Actualizar manifest
        for upd in manifest_updates:
            mkey = upd["materia_key"]
            m_entry = manifest_materias.setdefault(mkey, {"modulos": {}})
            m_entry.setdefault("modulos", {})[upd["module_key"]] = {
                "nombre": upd["module_name"],
                "hash": upd["hash"],
                "recursos": [{"nombre": r.nombre, "url": r.url, "tipo": r.tipo.value} for r in upd["recursos"]],
            }
            m_entry["ultima_descarga"] = datetime.utcnow().isoformat()

        self._notify(f"Total recursos encontrados: {len(recursos_totales)}")

        # Descargas en paralelo
        if recursos_totales:
            self._descargar_con_api(recursos_totales, base_dir, client)

        if exportar and recursos_totales:
            self.exportar_recursos(recursos_totales, "json")
            self.exportar_recursos(recursos_totales, "txt")

        self._save_manifest(manifest, base_dir)
        return True

    def _descargar_con_api(self, recursos: List[Recurso], base_dir: Path, client: MoodleAPIClient):
        """Descarga usando download_session del cliente (añade ?token automáticamente a cada GET)."""
        self._notify("Iniciando descargas...")
        max_workers = min(16, max(4, (os.cpu_count() or 4) * 2))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(self._download_recurso, r, base_dir, client.download_session)
                for r in recursos
            ]
            for f in concurrent.futures.as_completed(futures):
                try:
                    f.result()
                except Exception as e:
                    self._notify(f"Error descarga: {e}")

    # ------------------------------------------------------------------ #
    # Camino fallback: Selenium + ProcessPool
    # ------------------------------------------------------------------ #
    def ejecutar_con_selenium(
        self,
        username: str,
        password: str,
        exportar: bool,
        materias: List[Materia],
        materia_modes: dict[str, Any],
        base_dir: Path,
    ) -> bool:
        manifest = self._load_manifest(base_dir)
        manifest_materias = manifest.setdefault("materias", {})

        base_session = self._build_session_from_driver()
        download_futures = []
        download_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=min(6, max(2, os.cpu_count() or 4))
        )

        recursos: List[Recurso] = []
        materias_resultado = []
        materias_count = len(materias)
        mode_map = materia_modes or {}

        max_workers = min(4, max(1, math.ceil(materias_count / 3)))
        chunk_size = math.ceil(materias_count / max_workers)
        payloads = [
            (materias[i:i + chunk_size], username, password, self.headless, mode_map, manifest_materias)
            for i in range(0, materias_count, chunk_size)
        ]

        self._notify(f"Procesando {materias_count} materias con {len(payloads)} procesos...")
        try:
            with concurrent.futures.ProcessPoolExecutor(max_workers=len(payloads)) as executor:
                futures = [executor.submit(_scrapear_lote_worker, p) for p in payloads]
                for future in concurrent.futures.as_completed(futures):
                    try:
                        materias_proc, recursos_proc, manifest_updates = future.result()
                        materias_resultado.extend(materias_proc)
                        recursos.extend(recursos_proc)
                        for recurso in recursos_proc:
                            download_futures.append(
                                download_executor.submit(self._download_recurso, recurso, base_dir, base_session)
                            )
                        for upd in manifest_updates:
                            mkey = upd["materia_key"]
                            m_entry = manifest_materias.setdefault(mkey, {
                                "nombre": next((m.nombre for m in materias_proc if _materia_key(m) == mkey), mkey),
                                "modulos": {},
                            })
                            m_entry.setdefault("modulos", {})[upd["module_key"]] = {
                                "nombre": upd["module_name"],
                                "hash": upd["hash"],
                                "recursos": [{"nombre": r.nombre, "url": r.url, "tipo": r.tipo.value} for r in upd["recursos"]],
                            }
                            m_entry["ultima_descarga"] = datetime.utcnow().isoformat()
                        for m in materias_proc:
                            self._notify(f"Recursos en {m.nombre}: {m.total_recursos()}")
                    except Exception as e:
                        self._notify(f"Error en lote: {e}")
        except Exception as e:
            self._notify(f"Error durante scraping paralelo: {e}")
        finally:
            for f in download_futures:
                try:
                    f.result()
                except Exception as e:
                    self._notify(f"Error descarga: {e}")
            download_executor.shutdown(wait=True)

        self._notify(f"Total recursos: {len(recursos)}")
        if exportar and recursos:
            self.exportar_recursos(recursos, "json")
            self.exportar_recursos(recursos, "txt")
        self._save_manifest(manifest, base_dir)
        return True

    # ------------------------------------------------------------------ #
    # Punto de entrada unificado
    # ------------------------------------------------------------------ #
    def ejecutar(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        exportar: bool = True,
        materias: Optional[List[Materia]] = None,
        materia_modes: Optional[dict[str, Any]] = None,
    ) -> bool:
        try:
            base_dir = Path(self.config.OUTPUT_DIR)
            materias_a_scrapear = materias

            if self.api_token:
                self._notify("Modo API activo — sin navegador.")
                if not materias_a_scrapear:
                    client = MoodleAPIClient(self.api_token, self.config.BASE_URL)
                    info = client.get_site_info()
                    courses = client.get_enrolled_courses(info["userid"])
                    materias_a_scrapear = api_courses_to_materias(courses)
                if not materias_a_scrapear:
                    self._notify("No se encontraron materias.")
                    return False
                return self.ejecutar_con_api(username or "", password or "", exportar, materias_a_scrapear, materia_modes or {}, base_dir)

            # Fallback Selenium
            self._notify("API no disponible — usando navegador.")
            self.inicializar_driver()
            if not self.login(username, password):
                self._notify("Login fallido. Abortando.")
                return False
            if not materias_a_scrapear:
                assert self.parser is not None
                materias_a_scrapear = self.parser.obtener_materias()
            if not materias_a_scrapear:
                self._notify("No se encontraron materias.")
                return False
            return self.ejecutar_con_selenium(username or "", password or "", exportar, materias_a_scrapear, materia_modes or {}, base_dir)

        except Exception as e:
            self._notify(f"Error: {e}")
            return False
        finally:
            self.cerrar()

    # ------------------------------------------------------------------ #
    # Descarga de archivos
    # ------------------------------------------------------------------ #
    def _build_session_from_driver(self) -> requests.Session:
        session = requests.Session()
        try:
            assert self.driver is not None
            for cookie in self.driver.get_cookies():
                session.cookies.set(cookie["name"], cookie["value"])
            ua = self.driver.execute_script("return navigator.userAgent;")
        except Exception:
            system = platform.system()
            if system == "Darwin":
                ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            elif system == "Windows":
                ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            else:
                ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            self._notify("No se pudo leer cookies del navegador; usando UA por defecto.")
        session.headers.update({"User-Agent": ua})
        return session

    def _sanitizar_nombre(self, nombre: str, fallback: str = "archivo") -> str:
        limpio = re.sub(r'[\\/:*?"<>|]+', "_", nombre)
        limpio = re.sub(r"[\r\n\t]+", " ", limpio)
        limpio = re.sub(r"\s+", " ", limpio).strip().rstrip(" .")
        return (limpio or fallback)[:180]

    def _fix_mojibake(self, nombre: str) -> str:
        if not any(ch in nombre for ch in ("Ã", "Â", "�")):
            return nombre
        try:
            return nombre.encode("latin-1").decode("utf-8")
        except Exception:
            return nombre

    def _resolver_nombre_archivo(self, recurso: Recurso, response) -> str:
        dispo = response.headers.get("content-disposition", "")
        filename = None
        if "filename" in dispo.lower():
            params = {}
            for part in dispo.split(";")[1:]:
                if "=" in part:
                    k, v = part.split("=", 1)
                    params[k.strip().lower()] = v.strip().strip('"').strip("'")
            if "filename*" in params:
                raw = params["filename*"]
                if raw.lower().startswith("utf-8''"):
                    raw = raw[7:]
                filename = unquote(raw)
            if not filename and "filename" in params:
                filename = params["filename"]
        if filename:
            filename = unquote(self._fix_mojibake(filename.strip().strip('"').strip("'")))
            filename = self._sanitizar_nombre(filename)

        parsed = urlparse(response.url or recurso.url)
        base = os.path.basename(parsed.path)
        extension = Path(base).suffix if base else ""

        if not filename:
            filename = self._sanitizar_nombre(unquote(base)) if base else self._sanitizar_nombre(recurso.nombre)

        ext_from_name = Path(recurso.nombre).suffix
        if ext_from_name and not Path(filename).suffix:
            filename = f"{filename}{ext_from_name}"

        if not Path(filename).suffix:
            if extension:
                filename = f"{filename}{extension}"
            else:
                ctype = response.headers.get("content-type", "").lower()
                ext_map = {
                    "application/pdf": ".pdf",
                    "application/vnd.ms-powerpoint": ".ppt",
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
                    "application/vnd.ms-excel": ".xls",
                    "application/msword": ".doc",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
                }
                for key, ext in ext_map.items():
                    if key in ctype:
                        filename = f"{filename}{ext}"
                        break

        if not Path(filename).suffix:
            filename = f"{filename}.pdf" if recurso.tipo == TipoRecurso.GOOGLE_DRIVE else f"{filename}.bin"

        return filename

    def _ruta_unica(self, base_path: Path, filename: str) -> Path:
        # Reserva en memoria para evitar colisiones entre threads sin tocar el disco.
        # Los archivos solo se crean cuando la descarga termina exitosamente.
        with self._path_lock:
            path = base_path / filename
            key = str(path)
            if not path.exists() and key not in self._reserved_paths:
                self._reserved_paths.add(key)
                return path
            stem, suffix = path.stem, path.suffix
            counter = 1
            while True:
                candidate = base_path / f"{stem}_{counter}{suffix}"
                ckey = str(candidate)
                if not candidate.exists() and ckey not in self._reserved_paths:
                    self._reserved_paths.add(ckey)
                    return candidate
                counter += 1

    def _es_descargable(self, recurso: Recurso) -> bool:
        url = recurso.url.lower()
        return ("presencial.ucc.edu.ar" in url) and ("/mod/resource/" in url or "/pluginfile.php" in url)

    # Tipos que no se descargan como archivo: se guardan como acceso directo .url
    # (o, para carpetas sin contenido expandido, como link a la carpeta en Moodle).
    _TIPOS_ENLACE = (TipoRecurso.GOOGLE_DRIVE, TipoRecurso.LINK, TipoRecurso.VIDEO_YOUTUBE, TipoRecurso.CARPETA)

    def _dir_para_recurso(self, recurso: Recurso, base_dir: Path) -> Path:
        """
        Directorio de destino para un recurso, preservando la subcarpeta de Moodle
        (recurso.subcarpeta) cuando exista.

        Sin esto, archivos con el mismo nombre en subcarpetas distintas de un mismo
        recurso "folder" (ej. Pila/nodo.h, Cola/nodo.h, Hash/nodo.h) colisionan en
        el mismo directorio de módulo y _ruta_unica los renombra como si fueran
        duplicados (nodo.h, nodo_1.h, nodo_2.h...) en vez de mantenerlos separados.
        """
        materia_dir = base_dir / self._sanitizar_nombre(recurso.materia_nombre, "materia")
        modulo_dir = materia_dir / self._sanitizar_nombre(recurso.modulo_nombre or "sin_modulo", "sin_modulo")
        for parte in (recurso.subcarpeta or "").split("/"):
            parte = parte.strip()
            if parte:
                modulo_dir = modulo_dir / self._sanitizar_nombre(parte, "sub")
        return modulo_dir

    def _guardar_enlace(self, recurso: Recurso, modulo_dir: Path):
        etiqueta = {
            TipoRecurso.GOOGLE_DRIVE: "enlace Drive",
            TipoRecurso.LINK: "enlace",
            TipoRecurso.VIDEO_YOUTUBE: "video YouTube",
            TipoRecurso.CARPETA: "carpeta Moodle",
        }.get(recurso.tipo, "enlace")
        nombre_archivo = self._sanitizar_nombre(recurso.nombre, "enlace") + ".url"
        destino = self._ruta_unica(modulo_dir, nombre_archivo)
        with open(destino, "w", encoding="utf-8") as f:
            f.write(f"[InternetShortcut]\nURL={recurso.url}\n")
        print(f"  ✓ {recurso.materia_nombre}/{recurso.modulo_nombre} -> {etiqueta}: {destino.name}")
        self._notify(f"{etiqueta.capitalize()} guardado: {recurso.nombre}")

    def _download_recurso(self, recurso: Recurso, base_dir: Path, session: requests.Session):
        modulo_dir = self._dir_para_recurso(recurso, base_dir)

        if recurso.tipo in self._TIPOS_ENLACE:
            modulo_dir.mkdir(parents=True, exist_ok=True)
            self._guardar_enlace(recurso, modulo_dir)
            return

        if not self._es_descargable(recurso):
            return

        resp = session.get(recurso.url, allow_redirects=True, timeout=60, stream=True)
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "").lower()
        download_resp = resp

        if "text/html" in content_type:
            html_body = resp.text
            soup = BeautifulSoup(html_body, "html.parser")

            pluginfile_url = None
            for a in soup.find_all("a", href=True):
                if "pluginfile.php" in a["href"]:
                    pluginfile_url = a["href"]
                    break

            iframe = soup.find("iframe", src=re.compile(r"docs.google.com/presentation"))
            if iframe and iframe.get("src"):
                modulo_dir.mkdir(parents=True, exist_ok=True)
                slides_name = self._sanitizar_nombre(f"{recurso.nombre} - Slides", "slides") + ".url"
                slides_dest = self._ruta_unica(modulo_dir, slides_name)
                with open(slides_dest, "w", encoding="utf-8") as f:
                    f.write(f"[InternetShortcut]\nURL={iframe['src']}\n")
                self._notify(f"Slides enlazados: {recurso.nombre}")

            if not pluginfile_url:
                return

            download_resp = session.get(pluginfile_url, allow_redirects=True, timeout=60, stream=True)
            download_resp.raise_for_status()

        filename = self._resolver_nombre_archivo(recurso, download_resp)
        modulo_dir.mkdir(parents=True, exist_ok=True)
        destino = self._ruta_unica(modulo_dir, filename)

        # Descarga streaming con escritura atómica vía tmp
        tmp = destino.with_suffix(destino.suffix + ".tmp")
        try:
            with open(tmp, "wb") as f:
                for chunk in download_resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
            tmp.rename(destino)
        except Exception:
            tmp.unlink(missing_ok=True)
            with self._path_lock:
                self._reserved_paths.discard(str(destino))
            raise

        print(f"  ✓ {recurso.materia_nombre}/{recurso.modulo_nombre} -> {destino.name}")
        self._notify(f"Descargado: {recurso.nombre}")
