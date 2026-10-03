import unittest

from PyQt6 import QtCore, QtWidgets

Checked = QtCore.Qt.CheckState.Checked
Unchecked = QtCore.Qt.CheckState.Unchecked
Partial = QtCore.Qt.CheckState.PartiallyChecked


def get_app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def sample_tree():
    return {
        "scanned_at": "2026-10-03T10:00:00Z",
        "roots": [
            {
                "id": "R1", "course_id": 1, "materia": "Sistemas", "modulo": "U1", "link_name": "Cátedra A",
                "new": False,
                "node": {"id": "R1", "kind": "folder", "name": "Cátedra A", "children": [
                    {"id": "a", "kind": "file", "name": "a.pdf", "size": 1000},
                    {"id": "S", "kind": "folder", "name": "Sub", "children": [
                        {"id": "b", "kind": "file", "name": "b.pdf", "size": 2000},
                    ]},
                ]},
            },
            {
                "id": "R2", "course_id": 1, "materia": "Sistemas", "modulo": "U2", "link_name": "Cátedra B",
                "new": True,
                "node": {"id": "R2", "kind": "folder", "name": "Cátedra B", "children": [
                    {"id": "c", "kind": "file", "name": "c.pdf", "size": 500},
                    {"id": "d", "kind": "file", "name": "Clase", "mime": "application/vnd.google-apps.presentation", "size": 0},
                ]},
            },
            {
                "id": "R3", "course_id": 2, "materia": "Álgebra", "modulo": "U1", "link_name": "Privada",
                "new": True, "error": "esta carpeta de Drive es privada; conectá Google en Conexión",
            },
        ],
    }


class DrivePanelTest(unittest.TestCase):
    def setUp(self):
        self.app = get_app()
        from gui.panels.drive import DrivePanel

        self.panel = DrivePanel()
        self.panel.show_tree(sample_tree(), {"R1": "include", "S": "exclude"})

    def item(self, drive_id):
        return self.panel.item_for(drive_id)

    def test_check_states_follow_the_nearest_rule(self):
        self.assertEqual(self.item("R1").checkState(0), Partial)
        self.assertEqual(self.item("a").checkState(0), Checked)
        self.assertEqual(self.item("S").checkState(0), Unchecked)
        self.assertEqual(self.item("b").checkState(0), Unchecked)
        self.assertEqual(self.item("R2").checkState(0), Unchecked)

    def test_new_and_unreadable_links_are_labelled(self):
        self.assertIn("nuevo", self.item("R2").text(0))
        self.assertNotIn("nuevo", self.item("R1").text(0))
        self.assertIn("privada", self.item("R3").toolTip(0))
        self.assertIn("privada", self.item("R3").text(1))

    def test_footer_shows_selected_and_total_size(self):
        self.assertIn("Seleccionado: 1000 B de 3.4 KB", self.panel.summary_label.text())

    def test_saving_unchanged_selection_keeps_the_rules(self):
        self.assertEqual(
            self.panel.rules(), {"R1": "include", "S": "exclude", "R2": "exclude", "R3": "exclude"}
        )
        self.assertFalse(self.panel.is_dirty())

    def test_selecting_a_new_link_includes_it_whole(self):
        self.item("R2").setCheckState(0, Checked)
        self.assertEqual(self.item("c").checkState(0), Checked)
        self.assertEqual(self.panel.rules()["R2"], "include")
        self.assertNotIn("c", self.panel.rules())
        self.assertTrue(self.panel.is_dirty())

    def test_unchecking_one_file_keeps_the_folder_included(self):
        self.item("R2").setCheckState(0, Checked)
        self.item("c").setCheckState(0, Unchecked)
        rules = self.panel.rules()
        self.assertEqual(rules["R2"], "include")
        self.assertEqual(rules["c"], "exclude")

    def test_completing_an_excluded_folder_drops_its_exception(self):
        self.item("b").setCheckState(0, Checked)
        self.assertEqual(self.item("R1").checkState(0), Checked)
        rules = self.panel.rules()
        self.assertEqual(rules["R1"], "include")
        self.assertNotIn("S", rules)
        self.assertNotIn("b", rules)

    def test_checking_one_file_of_a_new_link_only_includes_that_file(self):
        self.item("c").setCheckState(0, Checked)
        rules = self.panel.rules()
        self.assertEqual(rules["R2"], "exclude")
        self.assertEqual(rules["c"], "include")

    def test_buttons_emit_scan_and_save(self):
        scans, saves = [], []
        self.panel.scan_requested.connect(lambda: scans.append(True))
        self.panel.save_requested.connect(saves.append)
        self.panel.scan_btn.click()
        self.item("R2").setCheckState(0, Checked)
        self.panel.save_btn.click()
        self.assertEqual(scans, [True])
        self.assertEqual(saves[0]["R2"], "include")

    def test_mark_saved_clears_dirty(self):
        self.item("R2").setCheckState(0, Checked)
        self.panel.mark_saved()
        self.assertFalse(self.panel.is_dirty())

    def test_empty_state_explains_how_to_start(self):
        from gui.panels.drive import DrivePanel

        panel = DrivePanel()
        panel.show_tree({"scanned_at": "", "roots": None}, None)
        self.assertIn("Analizar Drive", panel.status_label.text())
        self.assertEqual(panel.rules(), {})


if __name__ == "__main__":
    unittest.main()
