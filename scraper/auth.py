"""
Manejo de autenticación en Moodle UCC
"""
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import getpass
import time
import requests
from typing import Optional
from utils.config import Config


def get_moodle_token(username: str, password: str, base_url: str) -> str | None:
    """
    Obtiene un token de Moodle Web Services vía POST.
    Usa data dict para que requests encodee correctamente caracteres especiales (#, @, etc).
    Retorna el token como string, o None si los web services no están habilitados o las credenciales fallan.
    """
    try:
        resp = requests.post(
            f"{base_url}/login/token.php",
            data={
                "username": username,
                "password": password,
                "service": "moodle_mobile_app",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("token") or None
    except Exception:
        return None


class MoodleAuthenticator:
    """Maneja la autenticación en la plataforma Moodle de UCC"""

    def __init__(self, driver: webdriver.Chrome):
        self.driver = driver
        self.config = Config()

    def obtener_credenciales(self):
        """
        Obtiene las credenciales del usuario.
        Primero intenta desde variables de entorno, sino pide por consola.
        """
        username = self.config.USERNAME
        password = self.config.PASSWORD

        if not username:
            print("\n=== Autenticación UCC Moodle ===")
            username = input("Usuario: ")

        if not password:
            password = getpass.getpass("Contraseña: ")

        return username, password

    def login(self, username: Optional[str] = None, password: Optional[str] = None):
        """
        Realiza el login en Moodle.

        Args:
            username: Nombre de usuario (opcional, se pedirá si no se proporciona)
            password: Contraseña (opcional, se pedirá si no se proporciona)

        Returns:
            bool: True si el login fue exitoso, False en caso contrario
        """
        try:
            # Navegar a la página de login
            print(f"Navegando a {self.config.LOGIN_URL}...")
            self.driver.get(self.config.LOGIN_URL)

            # Esperar a que la página cargue completamente
            time.sleep(2)

            # Obtener credenciales si no se proporcionaron
            if not username or not password:
                username, password = self.obtener_credenciales()

            # Esperar a que el formulario de login esté presente y sea interactuable
            wait = WebDriverWait(self.driver, self.config.TIMEOUT)

            # Esperar a que el campo de usuario esté visible y clickeable
            print("Esperando campos de login...")
            username_field = wait.until(
                EC.element_to_be_clickable((By.ID, "username"))
            )
            time.sleep(0.5)

            # Esperar a que el campo de contraseña esté visible y clickeable
            password_field = wait.until(
                EC.element_to_be_clickable((By.ID, "password"))
            )
            time.sleep(0.5)

            # Ingresar credenciales
            print("Ingresando credenciales...")
            username_field.clear()
            time.sleep(0.3)
            username_field.send_keys(username)
            time.sleep(0.5)

            password_field.clear()
            time.sleep(0.3)
            password_field.send_keys(password)
            time.sleep(0.5)

            # Esperar y hacer click en el botón de login
            login_button = wait.until(
                EC.element_to_be_clickable((By.ID, "loginbtn"))
            )
            time.sleep(0.5)
            login_button.click()

            # Esperar a que se complete el login verificando la URL del dashboard
            print("Esperando redirección...")
            wait.until(EC.url_contains("/my/"))

            print("Login exitoso!")
            return True

        except TimeoutException:
            print("Error: Tiempo de espera agotado. Verifica tus credenciales.")
            return False
        except Exception as e:
            print(f"Error durante el login: {str(e)}")
            return False

    def verificar_sesion(self):
        """
        Verifica si la sesión está activa.

        Returns:
            bool: True si la sesión está activa
        """
        try:
            current_url = self.driver.current_url
            return "/my/" in current_url or "/course/" in current_url
        except:
            return False
