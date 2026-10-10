#!/usr/bin/env python3
"""Construye el sidecar del backend con PyInstaller para la plataforma actual.

Funciona en macOS, Linux y Windows (lo usa CI con `shell: bash`). Deja el
binario en `src-tauri/binaries/finanzar-backend-<target-triple>[.exe]`, que es
el nombre que Tauri espera para `externalBin`.

Uso:
    python scripts/build_backend.py [target-triple]
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
BINARIES = ROOT / "src-tauri" / "binaries"
MANIFEST = ROOT / "models" / "manifest.json"

PYINSTALLER_ARGS = [
    "--noconfirm",
    "--clean",
    "--onefile",
    "--name",
    "finanzar-backend",
    "--collect-submodules",
    "uvicorn",
    "--collect-submodules",
    "chromadb",
    "--collect-submodules",
    "huggingface_hub",
    "--collect-data",
    "chromadb",
    "--hidden-import",
    "uvicorn.logging",
    "--hidden-import",
    "uvicorn.loops.auto",
    "--hidden-import",
    "uvicorn.protocols.http.auto",
    "--hidden-import",
    "uvicorn.protocols.websockets.auto",
    "--hidden-import",
    "uvicorn.lifespan.on",
    "--hidden-import",
    "fitz",
    "--hidden-import",
    "openpyxl",
    "--exclude-module",
    "torch",
    "--exclude-module",
    "transformers",
    "--exclude-module",
    "tkinter",
    "run_backend.py",
]


def host_triple() -> str:
    """Target triple del host (`rustc -vV`), con respaldo por plataforma."""
    try:
        out = subprocess.run(["rustc", "-vV"], capture_output=True, text=True, check=True).stdout
        for line in out.splitlines():
            if line.startswith("host:"):
                return line.split(":", 1)[1].strip()
    except (OSError, subprocess.CalledProcessError):
        pass
    machine = platform.machine().lower()
    arch = "aarch64" if machine in {"arm64", "aarch64"} else "x86_64"
    if sys.platform == "darwin":
        return f"{arch}-apple-darwin"
    if sys.platform.startswith("win"):
        return f"{arch}-pc-windows-msvc"
    return f"{arch}-unknown-linux-gnu"


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Construye el sidecar del backend (PyInstaller)")
    parser.add_argument("target", nargs="?", default=None, help="Target triple (por defecto, el host)")
    args = parser.parse_args()

    target = args.target or host_triple()
    is_windows = sys.platform.startswith("win")
    exe_suffix = ".exe" if is_windows else ""
    print(f"==> Sidecar del backend para {target} ({'Windows' if is_windows else sys.platform})")

    if not (BACKEND / ".venv").exists():
        run(["uv", "venv", "--python", "3.12"], cwd=BACKEND)
    run(["uv", "pip", "install", "-e", ".[dev]"], cwd=BACKEND)
    run(["uv", "pip", "install", "pyinstaller>=6.10"], cwd=BACKEND)

    # PyInstaller usa `;` como separador de --add-data en Windows.
    separator = ";" if is_windows else ":"
    add_data = f"{MANIFEST}{separator}models"
    run(["uv", "run", "pyinstaller", *PYINSTALLER_ARGS, "--add-data", add_data], cwd=BACKEND)

    built = BACKEND / "dist" / f"finanzar-backend{exe_suffix}"
    if not built.exists():
        print(f"✗ PyInstaller no generó {built}", file=sys.stderr)
        return 1

    BINARIES.mkdir(parents=True, exist_ok=True)
    destination = BINARIES / f"finanzar-backend-{target}{exe_suffix}"
    shutil.copy2(built, destination)
    if not is_windows:
        destination.chmod(destination.stat().st_mode | 0o111)
    print(f"==> Sidecar listo: {destination.relative_to(ROOT)} ({destination.stat().st_size // 1024 // 1024} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
