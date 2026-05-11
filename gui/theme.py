BG_APP           = "#1e1e1e"
BG_SIDEBAR       = "#252526"
BG_CARD          = "#2d2d2d"
BG_INPUT         = "#3c3c3c"
BG_ITEM_ACTIVE   = "#37373d"
BG_ITEM_HOVER    = "#2a2d2e"
BORDER           = "#3e3e42"
TEXT_PRIMARY     = "#cccccc"
TEXT_SECONDARY   = "#858585"
ACCENT           = "#0078d4"
SUCCESS          = "#4ec9b0"
ERROR            = "#f44747"
LOG_BG           = "#060d1a"
LOG_FG           = "#a3e635"

GLOBAL_STYLESHEET = f"""
QWidget {{
    background-color: {BG_APP};
    color: {TEXT_PRIMARY};
    font-family: -apple-system, 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    font-size: 13px;
}}
QLabel {{ background: transparent; }}
QLineEdit {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 8px 10px;
    color: {TEXT_PRIMARY};
}}
QLineEdit:focus {{ border-color: {ACCENT}; }}
QLineEdit:disabled {{ color: {TEXT_SECONDARY}; }}
QPushButton {{
    background-color: {ACCENT};
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 8px 14px;
    font-weight: 600;
}}
QPushButton:hover {{ background-color: #1a8fe3; }}
QPushButton:pressed {{ background-color: #006bbf; }}
QPushButton:disabled {{ background-color: #37373d; color: {TEXT_SECONDARY}; }}
QPushButton#ghost {{
    background: transparent;
    border: 1px solid {BORDER};
    color: {TEXT_PRIMARY};
}}
QPushButton#ghost:hover {{ border-color: #555; background: {BG_ITEM_HOVER}; }}
QComboBox {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 6px 10px;
    color: {TEXT_PRIMARY};
}}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    color: {TEXT_PRIMARY};
    selection-background-color: {ACCENT};
}}
QCheckBox {{ spacing: 8px; color: {TEXT_PRIMARY}; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border-radius: 3px;
    border: 1px solid {BORDER};
    background: {BG_INPUT};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
QProgressBar {{
    border: 1px solid {BORDER};
    border-radius: 4px;
    background: {BG_APP};
    height: 6px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 3px;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
}}
QScrollBar::handle:vertical {{
    background: #555;
    min-height: 24px;
    border-radius: 4px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollArea {{ border: none; background: transparent; }}
"""
