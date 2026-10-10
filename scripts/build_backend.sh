#!/usr/bin/env bash
# Construye el sidecar del backend Python con PyInstaller para macOS.
#
# Uso:
#   ./scripts/build_backend.sh [target-triple]
#
# El binario resultante se coloca en src-tauri/binaries/ con el sufijo de target
# que exige Tauri (por ejemplo finanzar-backend-aarch64-apple-darwin).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT/backend"
BINARIES_DIR="$ROOT/src-tauri/binaries"

TARGET="${1:-$(rustc -vV | awk '/host:/{print $2}')}"
ARCH="${TARGET%%-*}"
case "$ARCH" in
  aarch64) PYINSTALLER_TARGET_ARCH="arm64" ;;
  x86_64) PYINSTALLER_TARGET_ARCH="x86_64" ;;
  *) echo "Target no soportado: $TARGET" >&2; exit 1 ;;
esac

echo "==> Construyendo sidecar del backend para $TARGET"
cd "$BACKEND_DIR"

if [ ! -d ".venv" ]; then
  uv venv --python 3.12
fi
uv pip install -e ".[dev]" >/dev/null
uv pip install "pyinstaller>=6.10" >/dev/null

uv run pyinstaller \
  --noconfirm \
  --clean \
  --onefile \
  --name finanzar-backend \
  --target-arch "$PYINSTALLER_TARGET_ARCH" \
  --add-data "$ROOT/models/manifest.json:models" \
  --collect-submodules uvicorn \
  --collect-submodules chromadb \
  --collect-submodules huggingface_hub \
  --collect-data chromadb \
  --hidden-import uvicorn.logging \
  --hidden-import uvicorn.loops.auto \
  --hidden-import uvicorn.protocols.http.auto \
  --hidden-import uvicorn.protocols.websockets.auto \
  --hidden-import uvicorn.lifespan.on \
  --hidden-import fitz \
  --hidden-import openpyxl \
  --exclude-module torch \
  --exclude-module transformers \
  --exclude-module tkinter \
  run_backend.py

mkdir -p "$BINARIES_DIR"
cp "dist/finanzar-backend" "$BINARIES_DIR/finanzar-backend-$TARGET"
chmod +x "$BINARIES_DIR/finanzar-backend-$TARGET"
echo "==> Sidecar listo: src-tauri/binaries/finanzar-backend-$TARGET"
"$BINARIES_DIR/finanzar-backend-$TARGET" --help || true
