"""Punto de entrada de Scrappy: UI PyQt o cliente CLI del core Go."""
import sys
import argparse
import getpass
import os

from gui.core_bridge import CoreClient
from utils.config import Config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Scrappy para Moodle UCC - Descarga recursos de cursos'
    )
    parser.add_argument(
        '--username',
        '-u',
        type=str,
        help='Usuario de Moodle (si no se proporciona, se pedirá por consola)'
    )
    parser.add_argument(
        '--headless',
        action='store_const',
        const=True,
        default=None,
        # Sin efecto: se acepta para no romper scripts que usaban la versión Selenium.
        help=argparse.SUPPRESS
    )
    parser.add_argument(
        '--no-export',
        action='store_true',
        help='No exportar los resultados a archivos'
    )
    parser.add_argument(
        '--output',
        '-o',
        default='output',
        help='Carpeta de destino (por defecto: output)'
    )
    parser.epilog = (
        'La contraseña se toma de la variable UCC_PASSWORD o se pide por consola; '
        'nunca como argumento, porque quedaría visible para otros procesos.'
    )
    return parser


def main_cli():
    """Función principal para modo CLI"""
    args = build_parser().parse_args()

    # En Windows la salida redirigida usa cp1252 y no admite el banner ni las
    # marcas de progreso. En la build sin consola un error ahí abre un diálogo
    # modal y la CLI queda colgada, así que se reemplazan esos caracteres.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")

    # Banner
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║         SCRAPPER MOODLE UCC                              ║
    ║         Universidad Católica de Córdoba                  ║
    ╚══════════════════════════════════════════════════════════╝
    """)

    username = args.username or os.getenv("UCC_USERNAME", "") or input("Usuario: ").strip()
    password = os.getenv("UCC_PASSWORD", "") or getpass.getpass("Contraseña: ")
    core = CoreClient()
    try:
        materias, token = core.list_courses(username, password, Config.BASE_URL)
        result = core.sync(
            username=username,
            password=password,
            token=token,
            base_url=Config.BASE_URL,
            output_path=args.output,
            export=not args.no_export,
            materias=materias,
            materia_modes={
                materia.nombre: {"mode": "update", "scan_existing": True}
                for materia in materias
            },
            progress=print,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if not result.get("ok"):
        print(f"Error: {result.get('error', 'descarga incompleta')}", file=sys.stderr)
        return 1
    print("\n¡Proceso completado!")
    return 0


def main_gui():
    """Función principal para modo GUI"""
    from gui import main as gui_main
    gui_main()


def main():
    """Punto de entrada principal - decide entre GUI o CLI"""
    # Si hay argumentos de línea de comandos, usar CLI
    # Si no, usar GUI
    if len(sys.argv) > 1:
        return main_cli()
    else:
        main_gui()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
