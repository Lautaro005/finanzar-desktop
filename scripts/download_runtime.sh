#!/usr/bin/env bash
# Descarga el runtime de llama.cpp (llama-server) para el target actual.
#
# El binario y sus bibliotecas quedan en el directorio de datos de FinanzAR
# (~/Library/Application Support/FinanzAR/bin/llama-server), donde el backend
# lo detecta automáticamente. No se versiona ningún binario de terceros.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"

if [ ! -d ".venv" ]; then
  uv venv --python 3.12
  uv pip install -e ".[dev]" >/dev/null
fi

echo "==> Descargando runtime llama.cpp (b10828) para el target actual"
uv run python -m finanzar_backend.models --runtime
echo "==> Listo. El runtime queda en ~/Library/Application Support/FinanzAR/bin/"
