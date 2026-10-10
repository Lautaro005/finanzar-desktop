#!/usr/bin/env bash
# FinanzAR Desktop — arranque de desarrollo con un solo comando.
#
#   ./scripts/dev.sh
#
# Verifica herramientas, prepara entornos, descarga modelos en el primer
# arranque, compila el sidecar del backend, levanta el backend local en
# 127.0.0.1 y abre la ventana de Tauri.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# --- Configuración -------------------------------------------------------
DATA_DIR="${FINANZAR_DATA_DIR:-$HOME/Library/Application Support/FinanzAR}"
export FINANZAR_DATA_DIR="$DATA_DIR"
REQUIRED_BYTES=$((5 * 1024 * 1024 * 1024))  # 5 GB (modelos + margen)
BACKEND_LOG="$DATA_DIR/logs/dev-backend.log"

log()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*" >&2; }
fail() { printf '\033[1;31mxx\033[0m %s\n' "$*" >&2; exit 1; }

mkdir -p "$DATA_DIR/logs"

# --- 1. Herramientas de desarrollo --------------------------------------
log "Verificando herramientas de desarrollo"
missing=()
for tool in rustc cargo node npm uv python3 git; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    missing+=("$tool")
  fi
done
if [ "${#missing[@]}" -gt 0 ]; then
  fail "Faltan herramientas: ${missing[*]}. Instalá Rust (rustup), Node/npm, uv y git."
fi
for tool in rustc cargo node npm uv; do
  printf '    %-7s %s\n' "$tool" "$($tool --version 2>&1 | head -1)"
done

# --- 2. Entornos necesarios ---------------------------------------------
if [ ! -d "node_modules" ]; then
  log "Instalando dependencias del frontend"
  npm install --no-audit --no-fund
fi

if [ ! -d "backend/.venv" ]; then
  log "Creando entorno de Python del backend"
  (cd backend && uv venv --python 3.12)
fi
log "Sincronizando dependencias del backend"
(cd backend && uv pip install -e ".[dev]" >/dev/null)

# --- 3. Espacio libre (primer arranque) ---------------------------------
available=$(df -k "$DATA_DIR" | awk 'NR==2 {print $4 * 1024}')
if [ "$available" -lt "$REQUIRED_BYTES" ]; then
  fail "Espacio insuficiente: se necesitan ~5 GB libres en $(dirname "$DATA_DIR") y hay $(( available / 1024 / 1024 / 1024 )) GB."
fi
log "Espacio libre suficiente ($(( available / 1024 / 1024 / 1024 )) GB)"

# --- 4. Modelos y runtime (primer arranque) -----------------------------
if (cd backend && uv run python -m finanzar_backend.models.verify >/dev/null 2>&1); then
  log "Modelos ya verificados; se reutilizan"
else
  log "Primer arranque: descargando GLM-OCR, Spark (Q4_K_M) y el runtime de llama.cpp"
  (cd backend && uv run python -m finanzar_backend.models --all) \
    || warn "La descarga de modelos falló; podés reintentarla desde Configuración."
fi

# --- 5. Compilar o encontrar sidecars -----------------------------------
TARGET="$(rustc -vV | awk '/host:/{print $2}')"
SIDECAR="src-tauri/binaries/finanzar-backend-$TARGET"
if [ ! -x "$SIDECAR" ]; then
  log "Compilando sidecar del backend ($TARGET)"
  bash scripts/build_backend.sh "$TARGET"
else
  log "Sidecar encontrado: $SIDECAR"
fi

# --- 6. Backend Python ---------------------------------------------------
PORT="$(python3 - <<'PY'
import socket
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    print(s.getsockname()[1])
PY
)"
export FINANZAR_PORT="$PORT"
log "Iniciando backend local en 127.0.0.1:$PORT"
(cd backend && uv run python -m finanzar_backend --host 127.0.0.1 --port "$PORT" --data-dir "$DATA_DIR" \
  >"$BACKEND_LOG" 2>&1) &
BACKEND_PID=$!

cleanup() {
  log "Cerrando backend local"
  # Señalizar el proceso Python (no el wrapper de uv) para que su lifespan
  # detenga también llama-server.
  pkill -f "finanzar_backend --host 127.0.0.1 --port $PORT" 2>/dev/null || true
  kill "$BACKEND_PID" 2>/dev/null || true
  for _ in $(seq 1 6); do
    pgrep -f "finanzar_backend --host 127.0.0.1 --port $PORT" >/dev/null 2>&1 || break
    sleep 0.5
  done
  pkill -9 -f "finanzar_backend --host 127.0.0.1 --port $PORT" 2>/dev/null || true
  # Si quedó un llama-server del proyecto, se apaga por su directorio de datos.
  for pid in $(pgrep -f "llama-server" 2>/dev/null || true); do
    if ps -o command= -p "$pid" 2>/dev/null | grep -q "Application Support/FinanzAR"; then
      kill "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT INT TERM

for _ in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
    log "Backend listo"
    break
  fi
  sleep 0.5
done

# --- 7. Ventana de Tauri -------------------------------------------------
log "Abriendo la ventana de FinanzAR"
npm run tauri dev
