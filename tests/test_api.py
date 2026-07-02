import unittest

from scraper.models import Materia, TipoRecurso


class MoodleAPIConversionTest(unittest.TestCase):
    def test_folder_contents_are_converted_to_downloadable_files(self):
        from scraper.api import api_contents_to_modulos

        materia = Materia(nombre="SISTEMAS DE INFORMACION", url="http://course", id_curso="14243")
        sections = [{
            "name": "UNIDAD II: SISTEMAS DE INFORMACIÓN",
            "modules": [{
                "modname": "folder",
                "name": "Presentaciones de la Unidad",
                "url": "https://presencial.ucc.edu.ar/mod/folder/view.php?id=1154218",
                "contents": [{
                    "type": "file",
                    "filename": "SI-U2.1_ Sistemas de información-R.pdf",
                    "filepath": "/",
                    "fileurl": "https://presencial.ucc.edu.ar/webservice/pluginfile.php/1886742/mod_folder/content/2/SI-U2.1.pdf?forcedownload=1",
                    "mimetype": "application/pdf",
                }],
            }],
        }]

        modulos = api_contents_to_modulos(sections, materia, [])

        self.assertEqual(len(modulos), 1)
        self.assertEqual(len(modulos[0].recursos), 1)
        recurso = modulos[0].recursos[0]
        self.assertEqual(recurso.nombre, "SI-U2.1_ Sistemas de información-R.pdf")
        self.assertEqual(recurso.tipo, TipoRecurso.PDF)
        self.assertIn("/webservice/pluginfile.php/", recurso.url)
        self.assertNotEqual(recurso.tipo, TipoRecurso.CARPETA)
        self.assertEqual(recurso.subcarpeta, "")

    def test_same_filename_in_different_subfolders_keeps_distinct_subcarpeta(self):
        """
        Reproduce el caso real de "Algoritmos": una carpeta de ejercicios donde
        cada tema tiene su propia subcarpeta con un archivo de nombre genérico
        (nodo.h). Sin distinguir subcarpetas, los tres recursos son
        indistinguibles y navigator.py los trata como colisiones de nombre.
        """
        from scraper.api import api_contents_to_modulos

        materia = Materia(nombre="ALGORITMOS Y ESTRUCTURAS DE DATOS", url="http://course", id_curso="1")
        sections = [{
            "name": "Práctico",
            "modules": [{
                "modname": "folder",
                "name": "Ejercicios",
                "url": "https://presencial.ucc.edu.ar/mod/folder/view.php?id=1",
                "contents": [
                    {"type": "file", "filename": "nodo.h", "filepath": "/",
                     "fileurl": "https://presencial.ucc.edu.ar/webservice/pluginfile.php/1/mod_folder/content/1/nodo.h"},
                    {"type": "file", "filename": "nodo.h", "filepath": "/Pila/",
                     "fileurl": "https://presencial.ucc.edu.ar/webservice/pluginfile.php/2/mod_folder/content/1/Pila/nodo.h"},
                    {"type": "file", "filename": "nodo.h", "filepath": "/Cola/",
                     "fileurl": "https://presencial.ucc.edu.ar/webservice/pluginfile.php/3/mod_folder/content/2/Cola/nodo.h"},
                ],
            }],
        }]

        modulos = api_contents_to_modulos(sections, materia, [])

        self.assertEqual(len(modulos), 1)
        subcarpetas = sorted(r.subcarpeta for r in modulos[0].recursos)
        self.assertEqual(subcarpetas, ["", "Cola", "Pila"])


if __name__ == "__main__":
    unittest.main()
