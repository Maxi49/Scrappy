"""
Script principal para ejecutar el scrapper de Moodle UCC
"""
import sys
import argparse
from scraper.navigator import MoodleScraper


def main_cli():
    """Función principal para modo CLI"""

    # Configurar argumentos de línea de comandos
    parser = argparse.ArgumentParser(
        description='Scrapper para Moodle UCC - Extrae recursos de cursos'
    )
    parser.add_argument(
        '--username',
        '-u',
        type=str,
        help='Usuario de Moodle (si no se proporciona, se pedirá por consola)'
    )
    parser.add_argument(
        '--password',
        '-p',
        type=str,
        help='Contraseña de Moodle (si no se proporciona, se pedirá por consola)'
    )
    parser.add_argument(
        '--headless',
        action='store_const',
        const=True,
        default=None,
        help='Ejecutar en modo headless (por defecto usa Config.HEADLESS)'
    )
    parser.add_argument(
        '--no-export',
        action='store_true',
        help='No exportar los resultados a archivos'
    )

    args = parser.parse_args()

    # Banner
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║         SCRAPPER MOODLE UCC                              ║
    ║         Universidad Católica de Córdoba                  ║
    ╚══════════════════════════════════════════════════════════╝
    """)

    # Crear y ejecutar scraper
    scraper = MoodleScraper(headless=args.headless)
    scraper.ejecutar(
        username=args.username,
        password=args.password,
        exportar=not args.no_export
    )

    print("\n¡Proceso completado!")


def main_gui():
    """Función principal para modo GUI"""
    from gui import main as gui_main
    gui_main()


def main():
    """Punto de entrada principal - decide entre GUI o CLI"""
    # Si hay argumentos de línea de comandos, usar CLI
    # Si no, usar GUI
    if len(sys.argv) > 1:
        main_cli()
    else:
        main_gui()


if __name__ == "__main__":
    main()
