"""
Configuración compartida de Scrappy
"""
import os
from typing import ClassVar


class Config:
    """Configuración mínima compartida por la UI."""

    BASE_URL: ClassVar[str] = os.getenv(
        "MOODLE_BASE_URL", "https://presencial.ucc.edu.ar"
    ).rstrip("/")
