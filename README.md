# FinanzAR Desktop

Aplicación de escritorio para macOS que ordena tus finanzas personales a partir
de **resúmenes de tarjeta de crédito en PDF**, con **OCR local**, **copiloto
explicable** y **memoria semántica** en tu propio equipo. Nada de tus documentos,
movimientos o preguntas sale de la máquina.

- **Shell de escritorio:** Tauri 2 (Rust).
- **Interfaz:** React + TypeScript + Vite, con la identidad visual del prototipo.
- **Backend local:** FastAPI (sidecar Python) escuchando **solo** en `127.0.0.1`.
- **Fuente de verdad:** SQLite con migraciones.
- **Memoria semántica:** ChromaDB `PersistentClient`.
- **OCR:** [`zai-org/GLM-OCR`](https://huggingface.co/zai-org/GLM-OCR) (MIT).
- **Copiloto:** [`XHToken/Spark-X2.5-1.7B-GGUF`](https://huggingface.co/XHToken/Spark-X2.5-1.7B-GGUF)
  (Q4_K_M, Apache-2.0) servido por `llama.cpp` (`llama-server`, MIT).

## Arranque en un comando

```bash
git clone https://github.com/finanzar/finanzar-local.git
cd finanzar-local
./scripts/dev.sh
```

`dev.sh` verifica herramientas, crea entornos, comprueba espacio libre, descarga
y verifica los modelos en el primer arranque, compila el sidecar del backend,
levanta el backend local e **abre la ventana de FinanzAR**.

Requisitos de desarrollo: Rust (rustup), Node 20+, `uv` y `git`.
La app instalada **no requiere Python**.

## Estructura

```text
finanzar-local/
├── src/                 # React + TypeScript (interfaz)
├── src-tauri/           # Shell Tauri 2 en Rust + sidecar del backend
├── backend/             # FastAPI + SQLite + ChromaDB + OCR + copiloto
├── models/manifest.json # Revisiones y hashes fijados
├── scripts/             # dev.sh, build_backend.sh, download_runtime.sh
└── .github/workflows/   # CI y releases de macOS
```

## Datos y privacidad

- Directorio de datos: `~/Library/Application Support/FinanzAR/`
  (`finanzar.sqlite3`, `documents/`, `models/`, `chroma/`, `bin/`, `logs/`).
- Los PDF originales se guardan con nombre derivado de su SHA-256; los duplicados
  se detectan por checksum y se rechazan.
- El backend escucha únicamente en `127.0.0.1` y rechaza cualquier bind externo.
- Los logs redactan números de tarjeta (dejan marca y últimos cuatro dígitos) e
  importes.
- El updater solo consulta GitHub Releases y **nunca instala sin tu confirmación**.

## Exportación XLSX

`Datos → Exportar XLSX` genera un workbook con diez hojas: Resumen mensual,
Cuentas, Ingresos, Movimientos, Cuotas, Suscripciones, Tarjetas, Calendario,
Insights y Metadatos de exportación, con formato de moneda, autofiltro y paneles
congelados.

## Actualizaciones

La app comprueba versiones cada **3 horas** (con jitter y backoff), permite
desactivar la comprobación automática y pedir una manual. La instalación usa el
updater firmado de Tauri y requiere consentimiento explícito; se conserva la
versión anterior para rollback.

Clave pública de firma en `src-tauri/tauri.conf.json` (`plugins.updater.pubkey`).
La clave privada **no se versiona**: se pasa por
`TAURI_SIGNING_PRIVATE_KEY` en el momento del build.

## Tests

```bash
cd backend && uv run ruff check . && uv run pytest -q
cd src-tauri && cargo fmt --check && cargo clippy --all-targets -- -D warnings && cargo test
npm run build && npm run test
```

## Licencias

Ver [`docs/licenses.md`](docs/licenses.md). Resumen: código propio MIT; GLM-OCR
MIT; PP-DocLayoutV3 Apache-2.0; Spark-X2.5-1.7B Apache-2.0; llama.cpp MIT.
