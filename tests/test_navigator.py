import unittest
from pathlib import Path

import requests

from scraper.models import Recurso, TipoRecurso
from scraper.navigator import MoodleScraper


class DirParaRecursoTest(unittest.TestCase):
    """
    Reproduce el bug de "archivos duplicados" reportado para la materia
    Algoritmos: una carpeta de Moodle con subcarpetas por tema (Pila/nodo.h,
    Cola/nodo.h, Hash/nodo.h, más un nodo.h suelto en la raíz) se aplanaba en
    un único directorio de módulo, así que _ruta_unica terminaba renombrando
    archivos distintos como nodo.h, nodo_1.h, nodo_2.h, nodo_3.h.
    """

    def setUp(self):
        self.scraper = MoodleScraper(headless=True)
        self.base_dir = Path("/tmp/scrappy-test-output")

    def _recurso(self, subcarpeta: str) -> Recurso:
        return Recurso(
            nombre="nodo.h",
            url="https://presencial.ucc.edu.ar/webservice/pluginfile.php/1/mod_folder/content/1/nodo.h",
            tipo=TipoRecurso.ARCHIVO,
            modulo_nombre="Práctico",
            materia_nombre="Algoritmos",
            subcarpeta=subcarpeta,
        )

    def test_root_and_subfolder_resources_get_distinct_directories(self):
        raiz = self.scraper._dir_para_recurso(self._recurso(""), self.base_dir)
        pila = self.scraper._dir_para_recurso(self._recurso("Pila"), self.base_dir)
        cola = self.scraper._dir_para_recurso(self._recurso("Cola"), self.base_dir)

        self.assertNotEqual(raiz, pila)
        self.assertNotEqual(pila, cola)
        self.assertEqual(pila, raiz / "Pila")
        self.assertEqual(cola, raiz / "Cola")

    def test_nested_subcarpeta_preserves_hierarchy(self):
        anidado = self.scraper._dir_para_recurso(self._recurso("Pila/Ejercicio1"), self.base_dir)
        self.assertEqual(anidado.name, "Ejercicio1")
        self.assertEqual(anidado.parent.name, "Pila")

    def test_empty_subcarpeta_matches_original_flat_layout(self):
        recurso = self._recurso("")
        directorio = self.scraper._dir_para_recurso(recurso, self.base_dir)
        esperado = (
            self.base_dir
            / self.scraper._sanitizar_nombre(recurso.materia_nombre, "materia")
            / self.scraper._sanitizar_nombre(recurso.modulo_nombre, "sin_modulo")
        )
        self.assertEqual(directorio, esperado)


class GuardarEnlaceTest(unittest.TestCase):
    """
    Antes del fix, sólo TipoRecurso.GOOGLE_DRIVE generaba un acceso directo .url;
    LINK, VIDEO_YOUTUBE y CARPETA se descartaban en silencio en _download_recurso
    (nunca pasaban _es_descargable), a pesar de que el README documenta guardar
    accesos directos para enlaces externos.
    """

    def setUp(self):
        import tempfile
        self.scraper = MoodleScraper(headless=True)
        self._tmp = tempfile.TemporaryDirectory()
        self.base_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _recurso(self, tipo: TipoRecurso, nombre: str, url: str) -> Recurso:
        return Recurso(
            nombre=nombre,
            url=url,
            tipo=tipo,
            modulo_nombre="Unidad 1",
            materia_nombre="Materia",
        )

    def test_link_externo_guarda_acceso_directo(self):
        recurso = self._recurso(TipoRecurso.LINK, "Sitio externo", "https://example.com/recurso")
        self.scraper._download_recurso(recurso, self.base_dir, session=requests.Session())

        archivos = list((self.base_dir / "Materia" / "Unidad 1").glob("*.url"))
        self.assertEqual(len(archivos), 1)
        contenido = archivos[0].read_text(encoding="utf-8")
        self.assertIn("https://example.com/recurso", contenido)

    def test_youtube_guarda_acceso_directo(self):
        recurso = self._recurso(TipoRecurso.VIDEO_YOUTUBE, "Video clase", "https://youtu.be/abc123")
        self.scraper._download_recurso(recurso, self.base_dir, session=requests.Session())

        archivos = list((self.base_dir / "Materia" / "Unidad 1").glob("*.url"))
        self.assertEqual(len(archivos), 1)

    def test_carpeta_sin_contenido_guarda_acceso_directo(self):
        recurso = self._recurso(
            TipoRecurso.CARPETA, "Bibliografía", "https://presencial.ucc.edu.ar/mod/folder/view.php?id=1"
        )
        self.scraper._download_recurso(recurso, self.base_dir, session=requests.Session())

        archivos = list((self.base_dir / "Materia" / "Unidad 1").glob("*.url"))
        self.assertEqual(len(archivos), 1)

    def test_recurso_no_descargable_no_crea_carpeta_fantasma(self):
        """
        Reproduce el bug de "carpetas fantasma": un recurso tipificado como
        ARCHIVO cuya URL no matchea _es_descargable (no es /mod/resource/ ni
        /pluginfile.php de presencial.ucc.edu.ar) no debe crear el directorio
        del módulo si al final no hay nada que guardar ahí.
        """
        recurso = self._recurso(TipoRecurso.ARCHIVO, "Recurso raro", "https://presencial.ucc.edu.ar/mod/page/view.php?id=1")
        self.scraper._download_recurso(recurso, self.base_dir, session=requests.Session())

        self.assertFalse((self.base_dir / "Materia" / "Unidad 1").exists())


if __name__ == "__main__":
    unittest.main()
