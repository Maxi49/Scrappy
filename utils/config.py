"""
Configuración y constantes del scrapper
"""
import os
from typing import ClassVar

from dotenv import load_dotenv

load_dotenv()


class Config:
    """Configuración del scrapper de Moodle UCC"""

    # URLs de la plataforma
    BASE_URL: ClassVar[str] = "https://presencial.ucc.edu.ar"
    LOGIN_URL: ClassVar[str] = f"{BASE_URL}/login/index.php"
    DASHBOARD_URL: ClassVar[str] = f"{BASE_URL}/my/"

    # Credenciales (se pueden cargar desde .env o pedir al usuario)
    USERNAME: ClassVar[str] = os.getenv("UCC_USERNAME", "")
    PASSWORD: ClassVar[str] = os.getenv("UCC_PASSWORD", "")

    # Módulos/Tiles completos a excluir del scraping
    # NOTA: Esto solo excluye módulos completos (tiles), NO recursos individuales
    # Por ejemplo, si un PDF se llama "Presentación de la Unidad 1", NO será excluido
    # IMPORTANTE: La comparación ignora mayúsculas, minúsculas y tildes
    MODULOS_EXCLUIDOS: ClassVar[list[str]] = [
        "presentacion",
        "presentacion materia",
        "para estudiantes",
        "biblioteca"
    ]

    # Configuración de Selenium
    HEADLESS: ClassVar[bool] = os.getenv("HEADLESS", "False").lower() == "true"
    TIMEOUT: ClassVar[int] = 30  # segundos

    # Salida
    OUTPUT_DIR: str = "output"
    OUTPUT_FILE: ClassVar[str] = "recursos_encontrados.json"
