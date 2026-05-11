import re, unittest

class ThemeTest(unittest.TestCase):
    def test_color_constants_are_valid_hex(self):
        from gui.theme import (
            BG_APP, BG_SIDEBAR, BG_CARD, BG_INPUT, BG_ITEM_ACTIVE, BG_ITEM_HOVER,
            BORDER, TEXT_PRIMARY, TEXT_SECONDARY, ACCENT, SUCCESS, ERROR, LOG_BG, LOG_FG,
        )
        hex_re = re.compile(r'^#[0-9a-fA-F]{6}$')
        for c in [BG_APP, BG_SIDEBAR, BG_CARD, BG_INPUT, BG_ITEM_ACTIVE, BG_ITEM_HOVER,
                  BORDER, TEXT_PRIMARY, TEXT_SECONDARY, ACCENT, SUCCESS, ERROR, LOG_BG, LOG_FG]:
            self.assertRegex(c, hex_re, f"Invalid hex color: {c}")

    def test_stylesheet_is_nonempty_string(self):
        from gui.theme import GLOBAL_STYLESHEET
        self.assertIsInstance(GLOBAL_STYLESHEET, str)
        self.assertGreater(len(GLOBAL_STYLESHEET), 100)

if __name__ == "__main__":
    unittest.main()
