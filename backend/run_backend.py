"""Punto de entrada para el sidecar empaquetado con PyInstaller.

PyInstaller no puede usar ``python -m paquete`` directamente, así que este
módulo delega en ``finanzar_backend.__main__:main``.
"""

from __future__ import annotations

import multiprocessing
import sys


def _run() -> int:
    from finanzar_backend.__main__ import main

    return main(sys.argv[1:])


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(_run())
