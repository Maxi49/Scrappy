"""
Navegador principal del scrapper
"""
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from typing import List
import concurrent.futures
import math
import json
import os
import re
import hashlib
from datetime import datetime
from pathlib import Path
import requests
from urllib.parse import urlparse, unquote
from bs4 import BeautifulSoup

from scraper.auth import MoodleAuthenticator
from scraper.parser import MoodleParser
from scraper.models import Materia, Recurso, TipoRecurso
from utils.config import Config


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
    """Worker en proceso separado: login propio y scraping de un lote de materias."""
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
        for materia in materias:
            try:
                mkey = _materia_key(materia)
                mode_cfg = materia_modes.get(materia.nombre, {"mode": "update", "scan_existing": True})
                prev_modules = manifest_snapshot.get(mkey, {}).get("modulos", {})

                modulos = scraper.parser.obtener_modulos(materia)
                materia.modulos = modulos
                for modulo in modulos:
                    mk = _module_key(modulo.nombre)
                    # Decidir si procesar el módulo
                    if mode_cfg["mode"] == "update" and not mode_cfg.get("scan_existing", True):
                        # Solo módulos nuevos: saltar si ya existe en manifest
                        if mk in prev_modules:
                            continue
                    recursos_modulo = scraper.parser.extraer_recursos_modulo(materia, modulo)
                    modulo.recursos = recursos_modulo
                    if mode_cfg["mode"] == "update" and mode_cfg.get("scan_existing", True):
                        new_hash = _hash_recursos(recursos_modulo)
                        prev_hash = prev_modules.get(mk, {}).get("hash")
                        if prev_hash and prev_hash == new_hash:
                            # Sin cambios: no descargar de nuevo
                            continue
                        manifest_updates.append({"materia_key": mkey, "module_key": mk, "module_name": modulo.nombre, "hash": new_hash, "recursos": recursos_modulo})
                        recursos.extend(recursos_modulo)
                    else:
                        # full o módulo nuevo
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

    def __init__(self, headless: bool = None, user_agent: str = None):
        """
        Inicializa el scrapper

        Args:
            headless: Si es True, ejecuta el navegador sin interfaz gráfica
        """
        self.config = Config()
        self.headless = headless if headless is not None else self.config.HEADLESS
        self.user_agent_override = user_agent
        self.driver = None
        self.authenticator = None
        self.parser = None
        self.session = None
        self.progress_cb = None

    def _notify(self, message: str):
        """Notifica progreso a un callback opcional y mantiene el print."""
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

    def _cookie_bundle(self):
        """Empaqueta cookies y User-Agent para reutilizarlos en otros procesos."""
        try:
            cookies = self.driver.get_cookies()
            ua = self.driver.execute_script("return navigator.userAgent;")
            return {"cookies": cookies, "user_agent": ua}
        except Exception:
            return None

    def inicializar_driver(self):
        """Inicializa el driver de Selenium"""
        self._notify("Inicializando navegador...")

        options = Options()
        if self.headless:
            options.add_argument('--headless')
        if self.user_agent_override:
            options.add_argument(f'--user-agent={self.user_agent_override}')

        # Opciones adicionales para mejorar estabilidad
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-gpu')
        options.add_argument('--blink-settings=imagesEnabled=false')
        options.add_argument('--disable-notifications')

        # Instalar y configurar ChromeDriver automáticamente
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)

        # Maximizar ventana
        self.driver.maximize_window()

        # Inicializar componentes
        self.authenticator = MoodleAuthenticator(self.driver)
        self.parser = MoodleParser(self.driver)

        self._notify("Navegador inicializado correctamente")

    def login(self, username: str = None, password: str = None) -> bool:
        """
        Realiza el login en Moodle

        Args:
            username: Usuario (opcional)
            password: Contraseña (opcional)

        Returns:
            bool: True si el login fue exitoso
        """
        ok = self.authenticator.login(username, password)
        if ok:
            self._notify("Login exitoso")
        else:
            self._notify("Login fallido")
        return ok

    def scrapear_todo(self) -> List[Recurso]:
        """
        Realiza el scraping completo de todas las materias y sus recursos

        Returns:
            List[Recurso]: Lista de todos los recursos encontrados
        """
        todos_recursos = []

        try:
            # Obtener todas las materias
            materias = self.parser.obtener_materias()

            if not materias:
                print("\nNo se encontraron materias")
                return todos_recursos

            # Procesar cada materia
            for i, materia in enumerate(materias, 1):
                print(f"\n{'='*60}")
                print(f"Procesando materia {i}/{len(materias)}: {materia.nombre}")
                print(f"{'='*60}")

                # Obtener módulos de la materia
                modulos = self.parser.obtener_modulos(materia)
                materia.modulos = modulos

                # Extraer recursos de cada módulo
                for modulo in modulos:
                    recursos = self.parser.extraer_recursos_modulo(materia, modulo)
                    modulo.recursos = recursos
                    todos_recursos.extend(recursos)

                print(f"\nRecursos encontrados en {materia.nombre}: {materia.total_recursos()}")

        except Exception as e:
            print(f"\nError durante el scraping: {str(e)}")

        return todos_recursos

    def exportar_recursos(self, recursos: List[Recurso], formato: str = 'json'):
        """
        Exporta los recursos a un archivo

        Args:
            recursos: Lista de recursos a exportar
            formato: Formato de salida ('json' o 'txt')
        """
        # Crear directorio de salida si no existe
        os.makedirs(self.config.OUTPUT_DIR, exist_ok=True)

        if formato == 'json':
            output_path = os.path.join(self.config.OUTPUT_DIR, self.config.OUTPUT_FILE)

            # Convertir recursos a diccionarios
            recursos_dict = [recurso.to_dict() for recurso in recursos]

            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(recursos_dict, f, ensure_ascii=False, indent=2)

            print(f"\n✓ Recursos exportados a: {output_path}")

        elif formato == 'txt':
            output_path = os.path.join(self.config.OUTPUT_DIR, "recursos_encontrados.txt")

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write("RECURSOS ENCONTRADOS EN MOODLE UCC\n")
                f.write("=" * 80 + "\n\n")

                materia_actual = None
                modulo_actual = None

                for recurso in recursos:
                    # Escribir encabezado de materia si cambió
                    if recurso.materia_nombre != materia_actual:
                        materia_actual = recurso.materia_nombre
                        f.write(f"\n{'='*80}\n")
                        f.write(f"MATERIA: {materia_actual}\n")
                        f.write(f"{'='*80}\n")

                    # Escribir encabezado de módulo si cambió
                    if recurso.modulo_nombre != modulo_actual:
                        modulo_actual = recurso.modulo_nombre
                        f.write(f"\n  MÓDULO: {modulo_actual}\n")
                        f.write(f"  {'-'*76}\n")

                    # Escribir recurso
                    f.write(f"    - {recurso.nombre}\n")
                    f.write(f"      Tipo: {recurso.tipo.value}\n")
                    f.write(f"      URL: {recurso.url}\n\n")

            print(f"\n✓ Recursos exportados a: {output_path}")

    def cerrar(self):
        """Cierra el navegador"""
        if self.driver:
            print("\nCerrando navegador...")
            self.driver.quit()
            self.driver = None

    def obtener_materias_con_credenciales(self, username: str = None, password: str = None):
        """
        Inicializa driver, inicia sesión y retorna materias disponibles.
        Útil para flujos donde primero se listan cursos y luego se decide qué scrapear.
        """
        materias = []
        try:
            self.inicializar_driver()
            if not self.login(username, password):
                print("\nError en el login. Abortando...")
                return materias
            materias = self.parser.obtener_materias()
            self._notify(f"Materias encontradas: {len(materias)}")
        finally:
            self.cerrar()
        return materias

    def ejecutar(
        self,
        username: str = None,
        password: str = None,
        exportar: bool = True,
        materias: List[Materia] = None,
        materia_modes: dict = None,
    ) -> bool:
        """
        Ejecuta el scraper completo

        Args:
            username: Usuario (opcional)
            password: Contraseña (opcional)
            exportar: Si es True, exporta los resultados
            materias: Lista de materias a procesar (si no se provee, se obtienen todas)
        """
        success = True
        try:
            # Inicializar
            self.inicializar_driver()

            # Login
            if not self.login(username, password):
                print("\nError en el login. Abortando...")
                success = False
                return False

            # Scrapear
            print("\n" + "="*60)
            print("INICIANDO SCRAPING")
            print("="*60)
            self._notify("Obteniendo materias a procesar...")

            materias_a_scrapear = materias if materias is not None else self.parser.obtener_materias()
            if not materias_a_scrapear:
                print("\nNo se encontraron materias para procesar.")
                self._notify("No hay materias para procesar")
                return

            # Cargar manifiesto previo
            base_dir = Path(self.config.OUTPUT_DIR)
            manifest = self._load_manifest(base_dir)
            manifest_materias = manifest.setdefault("materias", {})

            # Preparar descarga en paralelo con requests mientras se scrapear materias
            base_session = self._build_download_session()
            download_futures = []
            download_executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=min(6, max(2, os.cpu_count() or 4))
            )

            recursos = []
            materias_resultado = []
            materias_count = len(materias_a_scrapear)
            mode_map = materia_modes or {}

            # Pool: 3-4 procesos máximo, con reparto equilibrado
            max_workers = min(4, max(2, math.ceil(materias_count / 3)))
            chunk_size = math.ceil(materias_count / max_workers)
            payloads = [
                (materias_a_scrapear[i:i + chunk_size], username, password, self.headless, mode_map, manifest_materias)
                for i in range(0, materias_count, chunk_size)
            ]

            self._notify(f"Procesando {materias_count} materias con {len(payloads)} procesos...")
            try:
                with concurrent.futures.ProcessPoolExecutor(max_workers=len(payloads)) as executor:
                    futures = [executor.submit(_scrapear_lote_worker, payload) for payload in payloads]
                    for future in concurrent.futures.as_completed(futures):
                        try:
                            materias_proc, recursos_proc, manifest_updates = future.result()
                            materias_resultado.extend(materias_proc)
                            recursos.extend(recursos_proc)
                            for recurso in recursos_proc:
                                download_futures.append(
                                    download_executor.submit(
                                        self._download_recurso, recurso, base_dir, base_session
                                    )
                                )
                            # Actualizar manifest en memoria con módulos procesados
                            for upd in manifest_updates:
                                mkey = upd["materia_key"]
                                m_entry = manifest_materias.setdefault(mkey, {
                                    "nombre": next((m.nombre for m in materias_proc if _materia_key(m) == mkey), mkey),
                                    "id_curso": next((m.id_curso for m in materias_proc if _materia_key(m) == mkey), ""),
                                    "modulos": {}
                                })
                                modules_dict = m_entry.setdefault("modulos", {})
                                modules_dict[upd["module_key"]] = {
                                    "nombre": upd["module_name"],
                                    "hash": upd["hash"],
                                    "recursos": [
                                        {"nombre": r.nombre, "url": r.url, "tipo": r.tipo.value}
                                        for r in upd["recursos"]
                                    ]
                                }
                                m_entry["ultima_descarga"] = datetime.utcnow().isoformat()
                            for materia_proc in materias_proc:
                                print(f"\nRecursos encontrados en {materia_proc.nombre}: {materia_proc.total_recursos()}")
                                self._notify(f"Recursos en {materia_proc.nombre}: {materia_proc.total_recursos()}")
                        except Exception as e:
                            print(f"\nError procesando lote: {e}")
                            self._notify(f"Error en lote: {e}")
            except Exception as e:
                print(f"\nError durante el scraping en paralelo: {str(e)}")
                self._notify(f"Error durante scraping paralelo: {str(e)}")
            finally:
                # Esperar a que terminen las descargas en curso
                for f in download_futures:
                    try:
                        f.result()
                    except Exception as e:
                        print(f"  ✗ Error en descarga: {e}")
                        self._notify(f"Error descarga: {e}")
                download_executor.shutdown(wait=True)

            # Resumen
            print("\n" + "="*60)
            print("RESUMEN")
            print("="*60)
            print(f"Total de recursos encontrados: {len(recursos)}")
            self._notify(f"Total recursos: {len(recursos)}")

            # Contar por tipo
            tipos = {}
            for recurso in recursos:
                tipo = recurso.tipo.value
                tipos[tipo] = tipos.get(tipo, 0) + 1

            print("\nRecursos por tipo:")
            for tipo, cantidad in sorted(tipos.items()):
                print(f"  - {tipo}: {cantidad}")

            # Exportar
            if exportar and recursos:
                self.exportar_recursos(recursos, formato='json')
                self.exportar_recursos(recursos, formato='txt')

            # Guardar manifest actualizado
            self._save_manifest(manifest, base_dir)

        finally:
            self.cerrar()
        return success

    # ------------------------------------------------------------------ #
    # Descarga de archivos
    # ------------------------------------------------------------------ #
    def _build_session_from_driver(self):
        """Crea una sesión de requests a partir de las cookies del driver."""
        session = requests.Session()
        try:
            for cookie in self.driver.get_cookies():
                session.cookies.set(cookie["name"], cookie["value"])
            ua = self.driver.execute_script("return navigator.userAgent;")
        except Exception:
            # Si el navegador ya no responde, usar UA genérico y sin cookies
            ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            self._notify("No se pudo leer cookies/userAgent del navegador; se usa valor por defecto.")
        # Reutilizar headers básicos del navegador
        session.headers.update({
            "User-Agent": ua
        })
        return session


    def _sanitizar_nombre(self, nombre: str, fallback: str = "archivo") -> str:
        # Mantener caracteres acentuados pero eliminar caracteres ilegales en FS
        limpio = re.sub(r'[\\/:*?"<>|]+', "_", nombre)
        limpio = re.sub(r"[\r\n\t]+", " ", limpio)
        limpio = re.sub(r"\s+", " ", limpio).strip()
        limpio = limpio.rstrip(" .")
        if not limpio:
            limpio = fallback
        return limpio[:180]

    def _fix_mojibake(self, nombre: str) -> str:
        """
        Intenta reparar nombres mal decodificados (UTF-8 visto como Latin-1).
        Si falla, retorna el nombre original.
        """
        # Solo intentar si parece mojibake (caracteres típicos Ã, Â, �)
        if not any(ch in nombre for ch in ("Ã", "Â", "�")):
            return nombre
        try:
            reparado = nombre.encode("latin-1").decode("utf-8")
            return reparado
        except Exception:
            return nombre

    def _resolver_nombre_archivo(self, recurso: Recurso, response) -> str:
        # Intentar extraer de Content-Disposition usando parse_header
        dispo = response.headers.get("content-disposition", "")
        filename = None
        if "filename" in dispo.lower():
            params = {}
            for part in dispo.split(";")[1:]:
                if "=" in part:
                    k, v = part.split("=", 1)
                    params[k.strip().lower()] = v.strip().strip('"').strip("'")

            if "filename*" in params:
                raw = params.get("filename*")
                if raw.lower().startswith("utf-8''"):
                    raw = raw[7:]
                filename = unquote(raw)
            if not filename and "filename" in params:
                filename = params.get("filename")

        if filename:
            filename = filename.strip().strip('"').strip("'")
            if filename.lower().startswith("utf-8''"):
                filename = filename[7:]
            filename = unquote(filename)
            filename = self._fix_mojibake(filename)
            filename = self._sanitizar_nombre(filename)
        else:
            filename = None

        parsed = urlparse(response.url or recurso.url)
        base = os.path.basename(parsed.path)
        extension = Path(base).suffix if base else ""

        if not filename:
            if base:
                filename = self._sanitizar_nombre(unquote(base))
            else:
                filename = self._sanitizar_nombre(recurso.nombre)

        # Si el nombre original del recurso tiene extensión, preferirla
        ext_from_name = Path(recurso.nombre).suffix
        if ext_from_name and not Path(filename).suffix:
            filename = f"{filename}{ext_from_name}"

        # Si no hay extensión, intentar deducir por content-type
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
                guessed_ext = None
                for key, ext in ext_map.items():
                    if key in ctype:
                        guessed_ext = ext
                        break
                if guessed_ext:
                    filename = f"{filename}{guessed_ext}"

        if not Path(filename).suffix:
            # Último recurso: usar nombre del recurso con .pdf como default para Drive, .bin para otros
            if recurso.tipo == TipoRecurso.GOOGLE_DRIVE:
                filename = f"{filename}.pdf"
            else:
                filename = f"{filename}.bin"

        return filename

    def _ruta_unica(self, base_path: Path, filename: str) -> Path:
        path = base_path / filename
        if not path.exists():
            return path
        stem = path.stem
        suffix = path.suffix
        counter = 1
        while True:
            candidate = base_path / f"{stem}_{counter}{suffix}"
            if not candidate.exists():
                return candidate
            counter += 1

    def _es_descargable(self, recurso: Recurso) -> bool:
        """Limitar descargas a recursos alojados en Moodle (evita externos como YouTube/Drive)."""
        url = recurso.url.lower()
        return ("presencial.ucc.edu.ar" in url) and ("/mod/resource/" in url or "/pluginfile.php" in url)

    def _build_download_session(self) -> requests.Session:
        """Construye una sesión de requests clonando cookies y headers del driver."""
        base_session = self._build_session_from_driver()
        return base_session

    def _download_recurso(self, recurso: Recurso, base_dir: Path, session: requests.Session):
        materia_dir = base_dir / self._sanitizar_nombre(recurso.materia_nombre, "materia")
        modulo_dir = materia_dir / self._sanitizar_nombre(recurso.modulo_nombre or "sin_modulo", "sin_modulo")
        modulo_dir.mkdir(parents=True, exist_ok=True)

        # Drive: solo guardamos acceso directo
        if recurso.tipo == TipoRecurso.GOOGLE_DRIVE:
            nombre_archivo = self._sanitizar_nombre(recurso.nombre, "enlace_drive") + ".url"
            destino = self._ruta_unica(modulo_dir, nombre_archivo)
            with open(destino, "w", encoding="utf-8") as f:
                f.write("[InternetShortcut]\n")
                f.write(f"URL={recurso.url}\n")
            print(f"  ✓ {recurso.materia_nombre}/{recurso.modulo_nombre} -> enlace Drive: {destino.name}")
            self._notify(f"Enlace Drive guardado: {recurso.nombre}")
            return

        # Recursos de Moodle u otros descargables
        if not self._es_descargable(recurso):
            return

        local_sess = requests.Session()
        local_sess.headers.update(session.headers)
        local_sess.cookies.update(session.cookies)

        resp = local_sess.get(recurso.url, allow_redirects=True, timeout=60, stream=True)
        resp.raise_for_status()

        # Si es HTML, buscar enlaces reales (pluginfile, slides embed)
        content_type = resp.headers.get("content-type", "").lower()
        download_resp = resp
        extra_urls = []
        if "text/html" in content_type:
            soup = BeautifulSoup(resp.text, "html.parser")

            # pluginfile u otros enlaces directos al archivo
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "pluginfile.php" in href:
                    extra_urls.append(href)
                    break

            # Iframe de Google Slides: guardar como acceso directo
            iframe = soup.find("iframe", src=re.compile(r"docs.google.com/presentation"))
            if iframe and iframe.get("src"):
                slides_url = iframe["src"]
                slides_name = self._sanitizar_nombre(f"{recurso.nombre} - Slides", "slides") + ".url"
                slides_dest = self._ruta_unica(modulo_dir, slides_name)
                with open(slides_dest, "w", encoding="utf-8") as f:
                    f.write("[InternetShortcut]\n")
                    f.write(f"URL={slides_url}\n")
                print(f"  ✓ {recurso.materia_nombre}/{recurso.modulo_nombre} -> Slides: {slides_dest.name}")
                self._notify(f"Slides enlazados: {recurso.nombre}")

            if extra_urls:
                download_url = extra_urls[0]
                download_resp = local_sess.get(download_url, allow_redirects=True, timeout=60, stream=True)
                download_resp.raise_for_status()

        filename = self._resolver_nombre_archivo(recurso, download_resp)
        destino = self._ruta_unica(modulo_dir, filename)

        with open(destino, "wb") as f:
            for chunk in download_resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        print(f"  ✓ {recurso.materia_nombre}/{recurso.modulo_nombre} -> {destino.name}")
        self._notify(f"Descargado: {recurso.nombre}")

    def descargar_recursos(self, recursos: List[Recurso]):
        """Descarga archivos a carpetas por materia dentro de OUTPUT_DIR."""
        if not self.driver:
            print("No hay driver para derivar cookies, se omiten descargas.")
            return

        base_dir = Path(self.config.OUTPUT_DIR)
        base_dir.mkdir(parents=True, exist_ok=True)
        base_session = self._build_download_session()

        print("\nDescargando archivos...")
        self._notify("Iniciando descargas...")
        max_workers = min(6, max(2, os.cpu_count() or 4))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(self._download_recurso, recurso, base_dir, base_session)
                for recurso in recursos
            ]
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"  ✗ Error en descarga: {e}")
