# Changelog

Todas las versiones siguen [SemVer](https://semver.org/lang/es/).

## 0.1.0 — 2026-10-10

Primera versión funcional.

### Producto

- Dashboard mensual con balance consolidado, ingresos, total a pagar,
  proyecciones a 1/3/6/12 meses, compromisos, fondo de emergencia, documentos
  pendientes e insights explicables.
- Cuentas (CRUD, archivado), ingresos puntuales y sueldo recurrente automático.
- Importación de PDF con checksum y detección de duplicados, OCR local con
  GLM-OCR, extracción estructurada y revisión lado a lado con confirmación.
- Copiloto local con recuperación desde SQLite y ChromaDB, que responde solo con
  datos confirmados y muestra sus fuentes.
- Vista tipo planilla con filtros, orden, edición de campos permitidos y
  exportación XLSX de diez hojas.
- Pantalla de actualizaciones con comprobación cada 3 horas, jitter, backoff y
  consentimiento antes de instalar.

### Técnico

- Shell Tauri 2 en Rust que arranca y detiene el sidecar del backend.
- Backend FastAPI en `127.0.0.1`, SQLite con migraciones y ChromaDB
  `PersistentClient` con embeddings locales (sin descargas de red).
- Revisiones y hashes de modelos fijados en `models/manifest.json`.
- Descargador de modelos reanudable, verificable y cancelable, con registro en
  `model_installations`.
- Sidecar del backend para macOS vía PyInstaller y runtime de `llama.cpp`
  descargado por target.
- CI con ruff, pytest, build de frontend, tests de Vitest, `cargo fmt`,
  `cargo clippy` y `cargo test` para `aarch64` y `x86_64`.

### OCR real verificado

- Extra opcional `ocr` (`torch` + `torchvision` + `transformers>=5`) que habilita
  la carga directa de GLM-OCR, con `scripts/ocr_check.py` como verificación de
  punta a punta sobre un PDF de prueba.
- Decodificación solo de los tokens generados (evita los marcadores `<|image|>`
  del prompt en el texto) y deduplicación de líneas repetidas.
- Deduplicación de movimientos con normalización de descripción, para que el OCR
  no duplique cargos al guardar.

### Limitaciones conocidas

- El sidecar empaquetado se generó y validó para `aarch64-apple-darwin`; el build
  para `x86_64-apple-darwin` queda en CI.
- El análisis de layout con PP-DocLayoutV3 es opcional y no viene habilitado por
  defecto: el OCR funciona sobre la página completa.
- Las releases firmadas requieren configurar `TAURI_SIGNING_PRIVATE_KEY` y un
  repositorio real en `tauri.conf.json`.
- El extra `ocr` no se instala por defecto (son varios GB); sin él la app usa el
  motor `native-pymupdf` y lo informa como tal.
