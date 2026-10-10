# Changelog

Todas las versiones siguen [SemVer](https://semver.org/lang/es/).

## 0.2.0 — 2026-10-10

### Resúmenes, pesos y dólares

- **Extracción por layout**: se usa la posición de cada palabra del PDF para
  distinguir la **columna de pesos** de la **columna de dólares**. Antes, en
  cuanto el documento decía "dólares", todos los consumos quedaban marcados como
  USD.
- Se leen las **percepciones e impuestos** que se cobran en pesos por las compras
  en dólares (IVA RG 4240, IIBB PERCEP-BSAS, DB.RG 5617, impuesto de sellos,
  retenciones) como movimientos de tipo `tax`, y las **devoluciones**
  (`DEV.IMP.`) con importe negativo.
- Se ignora el texto legal del pie (planes de cuotas del financiado, comisiones,
  condiciones, TNA/TEA) que antes entraba como consumo.
- El extractor del copiloto local ahora tiene un **system prompt** con el
  contexto de los resúmenes argentinos (dos columnas, percepciones, fechas
  Día/Mes/Año) y se usa como complemento cuando falta un dato crítico.
- Volver a correr el OCR **reemplaza** la extracción anterior del documento en
  lugar de mezclarla con la nueva.

### Documentos

- La revisión abre el **PDF real** (con navegación de páginas) en lugar del
  recuadro simulado.
- Se resaltan en verde las zonas que la IA leyó y se pueden **marcar consumos**
  arrastrando sobre el PDF para que se extraigan; si la zona pisa algo ya leído,
  no se duplica.
- El modal muestra los movimientos del resumen y permite recargarlos.

### Balance, calendario e ingresos

- El **balance disponible** incluye los ingresos sin cuenta asignada (el sueldo
  automático) y los pagos de tarjetas sin cuenta: antes quedaba en cero aunque
  hubiera ingresos cargados.
- El **vencimiento** del resumen aparece en el calendario y en "próximos pagos",
  y la extracción genera el pago del período.
- El **historial de ingresos** suma editar y borrar por fila (los ingresos del
  sueldo automático se anulan para que no reaparezcan).
- Las **suscripciones** reconocen Apple/iTunes y se reflejan en el dashboard.

### Interfaz

- Fechas y períodos en **formato argentino** (`dd/mm/aaaa`, `mm/aaaa`) con campos
  propios de la app: los campos nativos del navegador se mostraban como
  `mm/dd/aaaa` en un equipo configurado en inglés.
- Widget del copiloto: **refresh** para reiniciar la conversación y la **cruz**
  para cerrar; las respuestas se muestran en párrafos y viñetas, con las fuentes
  plegadas, y el motor deja de responder "sin datos" cuando hay evidencia
  (incluidas las negativas del modelo chico con otras palabras).
- Aire entre el encabezado y el contenido en las tarjetas de Configuración
  (metas de ahorro).

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

### Plataformas, licencia y releases

- **Licencia: GNU AGPL-3.0** (antes MIT). El motivo es PyMuPDF (AGPL-3.0), que
  forma parte del pipeline de OCR: distribuir el binario obliga a liberar el
  código bajo AGPL. Efecto buscado: nadie puede cerrarlo ni revenderlo como
  producto propietario. Modelos y runtimes conservan sus licencias (MIT /
  Apache-2.0).
- **CI multiplataforma**: los linteos y tests de Rust corren en
  `aarch64-apple-darwin`, `x86_64-apple-darwin`, `x86_64-unknown-linux-gnu` y
  `x86_64-pc-windows-msvc` (con las dependencias de sistema de Linux).
- **Release multiplataforma** (`release.yml`): en cada tag `v*` construye
  instaladores para macOS (`.dmg`), Windows (`MSI` y `.exe`) y Linux
  (`.AppImage` y `.deb`), arma el sidecar del backend con PyInstaller en cada
  sistema y publica la release con los artefactos.
- `scripts/build_backend.py` reemplaza la lógica del sidecar: funciona igual en
  macOS, Linux y Windows (deja `finanzar-backend-<target>[.exe]`).
- `scripts/build_updater_manifest.py`: genera `latest.json` **solo** con las
  plataformas que tengan archivo y firma (una entrada sin firma rompería la
  actualización) e informa cuáles omite.
- `bundle.targets` pasa a `all` para que cada sistema empaquete sus formatos.

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
