"""
Configuración y constantes del scrapper
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Configuración del scrapper de Moodle UCC"""

    # URLs de la plataforma
    BASE_URL = "https://presencial.ucc.edu.ar"
    LOGIN_URL = f"{BASE_URL}/login/index.php"
    DASHBOARD_URL = f"{BASE_URL}/my/"

    # Credenciales (se pueden cargar desde .env o pedir al usuario)
    USERNAME = os.getenv("UCC_USERNAME", "")
    PASSWORD = os.getenv("UCC_PASSWORD", "")

    # Módulos/Tiles completos a excluir del scraping
    # NOTA: Esto solo excluye módulos completos (tiles), NO recursos individuales
    # Por ejemplo, si un PDF se llama "Presentación de la Unidad 1", NO será excluido
    # IMPORTANTE: La comparación ignora mayúsculas, minúsculas y tildes
    MODULOS_EXCLUIDOS = [
        "presentacion",
        "presentacion materia",
        "para estudiantes",
        "biblioteca"
    ]

    # Configuración de Selenium
    HEADLESS = os.getenv("HEADLESS", "False").lower() == "true"
    TIMEOUT = 30  # segundos

    # Salida
    OUTPUT_DIR = "output"
    OUTPUT_FILE = "recursos_encontrados.json"
