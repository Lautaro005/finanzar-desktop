# FinanzAR Desktop

Aplicación de escritorio que ordena tus finanzas personales a partir de
**resúmenes de tarjeta de crédito en PDF**, con **OCR local**, **copiloto
explicable** y **memoria semántica** en tu propio equipo. Nada de tus documentos,
movimientos o preguntas sale de la máquina.

**Plataformas**: macOS es la plataforma de referencia (desarrollo y validación
funcional). Linux y Windows se compilan y empaquetan en CI (AppImage/deb,
MSI/`.exe`) pero **no están validados a mano** todavía: son bienvenidos los
reportes.

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
git clone https://github.com/Lautaro005/finanzar-desktop.git
cd finanzar-desktop
./scripts/dev.sh
```

`dev.sh` verifica herramientas, crea entornos, comprueba espacio libre, descarga
y verifica los modelos en el primer arranque, compila el sidecar del backend,
levanta el backend local e **abre la ventana de FinanzAR**.

Requisitos de desarrollo: Rust (rustup), Node 20+, `uv` y `git`.
La app instalada **no requiere Python**.

## Estructura

```text
finanzar-desktop/
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

## OCR real con GLM-OCR

El pipeline funciona con dos motores y siempre informa cuál usó:

- `glm-ocr`: carga directa del modelo (requiere el extra `ocr`).
- `native-pymupdf`: texto nativo del PDF (respaldo, sin dependencias pesadas).

Para habilitar GLM-OCR real (descarga torch + torchvision + transformers, varios GB):

```bash
cd backend && uv pip install -e ".[ocr]"
uv run python ../scripts/ocr_check.py   # genera un PDF de prueba y muestra el resultado
```

El script imprime el texto reconocido, los campos con su confianza y evidencia,
y los movimientos detectados. Debe reportar `Motor usado: glm-ocr` y
`RESULTADO: GLM-OCR REAL OK`.

## Licencia

**GNU AGPL-3.0** (ver [`LICENSE`](LICENSE)). El proyecto se distribuye bajo AGPL-3.0,
la misma licencia de **PyMuPDF**, que forma parte del pipeline de OCR: cualquiera
que lo redistribuya —incluso como parte de un producto— debe publicar el código
fuente completo de su versión. No se puede cerrar ni revender como software
propietario; para eso hace falta una licencia comercial de PyMuPDF y un acuerdo
aparte con el autor.

Los modelos y runtimes de terceros conservan **sus** licencias (MIT y
Apache-2.0): ver [`docs/licenses.md`](docs/licenses.md). Nada de eso se ve
afectado por la licencia del código propio.
