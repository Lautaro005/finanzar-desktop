"""Punto de entrada del sidecar.

Rust (o ``scripts/dev.sh``) arranca este proceso y le pasa el puerto y el
directorio de datos::

    python -m finanzar_backend --port 8765 --data-dir ~/Library/.../FinanzAR
"""

from __future__ import annotations

import argparse
import os
import sys


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backend local de FinanzAR Desktop")
    parser.add_argument("--host", default=os.environ.get("FINANZAR_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("FINANZAR_PORT", "8765")))
    parser.add_argument("--data-dir", default=os.environ.get("FINANZAR_DATA_DIR"))
    parser.add_argument("--log-level", default=os.environ.get("FINANZAR_LOG_LEVEL", "INFO"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    if args.data_dir:
        os.environ["FINANZAR_DATA_DIR"] = args.data_dir
    os.environ["FINANZAR_HOST"] = args.host
    os.environ["FINANZAR_PORT"] = str(args.port)
    os.environ["FINANZAR_LOG_LEVEL"] = args.log_level

    # El bind debe ser siempre loopback: nunca 0.0.0.0.
    if args.host not in {"127.0.0.1", "localhost"}:
        raise SystemExit("Por seguridad, FinanzAR solo escucha en 127.0.0.1")

    import uvicorn

    # Se importa después de fijar el entorno para que Settings tome los valores.
    from .main import create_app

    app = create_app()
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level.lower())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
