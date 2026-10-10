#!/usr/bin/env bash
# Construye el sidecar del backend Python con PyInstaller (macOS/Linux).
#
#   ./scripts/build_backend.sh [target-triple]
#
# La lógica vive en scripts/build_backend.py para que Windows (CI) use la misma.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$ROOT/scripts/build_backend.py" "$@"
