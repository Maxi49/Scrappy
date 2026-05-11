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


if __name__ == "__main__":
    unittest.main()
