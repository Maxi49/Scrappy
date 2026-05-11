"""
Parser para extraer información del HTML de Moodle (fallback Selenium)
"""
import re
import time
import traceback
import unicodedata
from typing import List

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from scraper.models import Materia, Modulo, Recurso, TipoRecurso
from utils.config import Config


class MoodleParser:
    """Parser para extraer información de las páginas de Moodle"""

    def __init__(self, driver: webdriver.Chrome):
        self.driver = driver
        self.config = Config()

    @staticmethod
    def normalizar_texto(texto: str) -> str:
        """
        Normaliza un texto removiendo tildes y convirtiéndolo a minúsculas

        Args:
            texto: Texto a normalizar

        Returns:
            str: Texto normalizado sin tildes y en minúsculas
        """
        # Convertir a minúsculas
        texto = texto.lower()
        # Remover tildes usando unicode normalization
        texto = unicodedata.normalize('NFD', texto)
        texto = ''.join(char for char in texto if unicodedata.category(char) != 'Mn')
        return texto

    def obtener_materias(self) -> List[Materia]:
        """
        Extrae la lista de materias desde el dashboard (/my/)

        Returns:
            List[Materia]: Lista de materias encontradas
        """
        print("\nExtrayendo lista de materias del dashboard...")

        materias = []

        try:
            # Navegar al dashboard si no estamos ahí
            if "/my/" not in self.driver.current_url:
                self.driver.get(self.config.DASHBOARD_URL)

            # Esperar a que desaparezca el placeholder de carga
            # Los cursos se cargan dinámicamente con AJAX
            wait = WebDriverWait(self.driver, 30)  # Aumentar timeout para carga dinámica

            print("Esperando a que se carguen los cursos...")

            # Esperar a que los enlaces de cursos estén presentes en el DOM
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-region='courses-view']")))
            wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a[href*='/course/view.php?id=']")))

            enlaces_cursos = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='/course/view.php?id=']")

            # Usar set para evitar duplicados
            cursos_vistos = set()

            for enlace in enlaces_cursos:
                try:
                    url = enlace.get_attribute('href')
                    nombre = enlace.text.strip()

                    # Filtrar enlaces vacíos o duplicados
                    if not nombre or not url or url in cursos_vistos:
                        continue

                    cursos_vistos.add(url)

                    # Extraer el ID del curso de la URL
                    match = re.search(r'id=(\d+)', url)
                    id_curso = match.group(1) if match else None

                    materia = Materia(nombre=nombre, url=url, id_curso=id_curso)
                    materias.append(materia)

                    print(f"  - {nombre} (ID: {id_curso})")

                except Exception as e:
                    # Ignorar enlaces que no se puedan procesar
                    continue

            print(f"\nTotal de materias encontradas: {len(materias)}")

        except Exception as e:
            print(f"Error al obtener materias: {str(e)}")
            traceback.print_exc()

        return materias

    def obtener_modulos(self, materia: Materia) -> List[Modulo]:
        """
        Extrae los módulos (tiles) de una materia específica
        Este Moodle usa formato "Tiles" donde cada módulo es una baldosa clickeable

        Args:
            materia: Objeto Materia con la URL del curso

        Returns:
            List[Modulo]: Lista de módulos encontrados
        """
        print(f"\nExtrayendo módulos de: {materia.nombre}")

        modulos = []

        try:
            # Navegar a la página del curso
            self.driver.get(materia.url)

            # Esperar a que carguen los tiles
            wait = WebDriverWait(self.driver, 30)

            print("Esperando a que se carguen los módulos...")

            # Esperar a que los tiles estén renderizados
            wait.until(EC.presence_of_element_located((By.ID, "multi_section_tiles")))
            wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "li.tile.tile-clickable")))

            tiles = self.driver.find_elements(By.CSS_SELECTOR, "li.tile.tile-clickable")

            print(f"  Se encontraron {len(tiles)} tiles en total")

            for tile in tiles:
                try:
                    # Obtener el nombre del módulo desde el h3 dentro del tile
                    nombre_elem = tile.find_element(By.TAG_NAME, "h3")
                    nombre = nombre_elem.text.strip()

                    if not nombre:
                        continue

                    # Filtrar módulos excluidos (normalizar para ignorar tildes y mayúsculas)
                    nombre_normalizado = self.normalizar_texto(nombre)
                    if any(excluido in nombre_normalizado for excluido in self.config.MODULOS_EXCLUIDOS):
                        print(f"  ✗ {nombre} (excluido)")
                        continue

                    # Obtener el enlace del tile
                    link_elem = tile.find_element(By.CSS_SELECTOR, "a.tile-link")
                    tile_url = link_elem.get_attribute('href')

                    modulo = Modulo(nombre=nombre)
                    # Guardar la URL del módulo para usarla después
                    modulo.url = tile_url
                    modulos.append(modulo)
                    print(f"  ✓ {nombre}")

                except Exception as e:
                    # Ignorar tiles que no se puedan procesar
                    continue

            print(f"  Total módulos válidos: {len(modulos)}")

        except Exception as e:
            print(f"  Error al obtener módulos: {str(e)}")
            traceback.print_exc()

        return modulos

    def determinar_tipo_recurso(self, url: str, nombre: str) -> TipoRecurso:
        """
        Determina el tipo de recurso basándose en la URL y nombre

        Args:
            url: URL del recurso
            nombre: Nombre del recurso

        Returns:
            TipoRecurso: Tipo identificado
        """
        url_lower = url.lower()
        nombre_lower = nombre.lower()

        # Google Drive (debe ir antes de otros checks)
        if 'drive.google.com' in url_lower or 'docs.google.com' in url_lower:
            return TipoRecurso.GOOGLE_DRIVE

        # Videos de YouTube
        if 'youtube.com' in url_lower or 'youtu.be' in url_lower:
            return TipoRecurso.VIDEO_YOUTUBE

        # PDFs
        if '.pdf' in url_lower or 'pdf' in nombre_lower:
            return TipoRecurso.PDF

        # PowerPoint
        if any(ext in url_lower for ext in ['.ppt', '.pptx']) or 'powerpoint' in nombre_lower:
            return TipoRecurso.POWERPOINT

        # Word
        if any(ext in url_lower for ext in ['.doc', '.docx']) or 'word' in nombre_lower:
            return TipoRecurso.WORD

        # Carpetas en Moodle
        if '/mod/folder/' in url_lower:
            return TipoRecurso.CARPETA

        # Recursos genéricos en Moodle
        if '/mod/resource/' in url_lower:
            return TipoRecurso.ARCHIVO

        # Links externos
        if url.startswith('http') and 'presencial.ucc.edu.ar' not in url:
            return TipoRecurso.LINK

        return TipoRecurso.DESCONOCIDO

    def extraer_recursos_modulo(self, materia: Materia, modulo: Modulo) -> List[Recurso]:
        """
        Extrae los recursos de un módulo específico navegando a su página individual
        En formato Tiles, cada módulo tiene su propia URL (course/section.php)

        Args:
            materia: Materia a la que pertenece el módulo
            modulo: Módulo del cual extraer recursos (debe tener URL)

        Returns:
            List[Recurso]: Lista de recursos encontrados
        """
        recursos = []
        urls_vistas = set()  # Para evitar duplicados

        try:
            if not modulo.url:
                print(f"    El módulo {modulo.nombre} no tiene URL")
                return recursos

            # Navegar a la página del módulo
            print(f"  Navegando al módulo: {modulo.nombre}")
            self.driver.get(modulo.url)

            wait = WebDriverWait(self.driver, 30)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "li.activity, .course-content")))

            actividades = self.driver.find_elements(By.CSS_SELECTOR, "li.activity")
            print(f"    Se encontraron {len(actividades)} actividades")

            for actividad in actividades:
                try:
                    # Buscar el enlace dentro de la actividad
                    link_elem = actividad.find_element(By.CSS_SELECTOR, "a.aalink")
                    url = link_elem.get_attribute('href')

                    # Buscar el nombre en el span.instancename
                    try:
                        nombre_elem = actividad.find_element(By.CSS_SELECTOR, "span.instancename")
                        nombre = nombre_elem.text.strip()
                    except:
                        # Si no hay instancename, usar el texto del enlace
                        nombre = link_elem.text.strip()

                    if not nombre or not url or url in urls_vistas:
                        continue

                    urls_vistas.add(url)

                    # Determinar el tipo de recurso
                    tipo = self.determinar_tipo_recurso(url, nombre)

                    recurso = Recurso(
                        nombre=nombre,
                        url=url,
                        tipo=tipo,
                        modulo_nombre=modulo.nombre,
                        materia_nombre=materia.nombre
                    )

                    recursos.append(recurso)
                    print(f"    - {nombre} [{tipo.value}]")

                except Exception as e:
                    # Ignorar actividades que no se puedan procesar
                    continue

            # 2. Extraer enlaces de contenido HTML (h3, labels, etc.)
            # Buscar todos los enlaces que apunten a Google Drive o externos
            print(f"    Buscando enlaces adicionales en contenido HTML...")

            todos_enlaces = self.driver.find_elements(By.TAG_NAME, "a")

            for enlace in todos_enlaces:
                try:
                    url = enlace.get_attribute('href')

                    if not url or url in urls_vistas:
                        continue

                    # Procesar enlaces relevantes (Drive, YouTube, externos o pluginfile suelto)
                    if not ('drive.google.com' in url or 'youtube.com' in url or 'youtu.be' in url
                            or 'pluginfile.php' in url
                            or (url.startswith('http') and 'presencial.ucc.edu.ar' not in url)):
                        continue

                    nombre = enlace.text.strip()

                    # Si el texto está vacío, intentar obtener el contexto
                    if not nombre:
                        try:
                            # Buscar el padre más cercano con texto
                            parent = enlace.find_element(By.XPATH, "..")
                            nombre = parent.text.strip()
                            # Limitar a primeras palabras si es muy largo
                            if len(nombre) > 100:
                                nombre = nombre[:100] + "..."
                        except:
                            nombre = "Enlace sin título"

                    if not nombre or url in urls_vistas:
                        continue

                    urls_vistas.add(url)

                    # Determinar el tipo de recurso
                    tipo = self.determinar_tipo_recurso(url, nombre)

                    recurso = Recurso(
                        nombre=nombre,
                        url=url,
                        tipo=tipo,
                        modulo_nombre=modulo.nombre,
                        materia_nombre=materia.nombre
                    )

                    recursos.append(recurso)
                    print(f"    - {nombre} [{tipo.value}] (HTML)")

                except Exception as e:
                    continue

        except Exception as e:
            print(f"    Error al extraer recursos: {str(e)}")
            traceback.print_exc()

        return recursos
