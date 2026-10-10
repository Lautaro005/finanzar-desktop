# Changelog

Todas las versiones siguen [SemVer](https://semver.org/lang/es/).

## 0.2.6 — 2026-10-10

### Walkthrough de primer arranque

- Cada descarga (llama.cpp, Spark, GLM-OCR y EmbeddingGemma) muestra su **barra de
  progreso con el porcentaje** dentro de su propia tarjeta, y el botón pasa a
  "Descargando… 42%". Mientras el porcentaje todavía no se conoce, la barra se
  anima para que se vea que está trabajando.

### Dólares en el dashboard

- **Todos los indicadores** muestran pesos y, debajo, dólares cuando los hay:
  balance disponible, ingresos del mes, a pagar, los cuatro pasos de la
  proyección (saldo actual, ingresos programados, pagos y fijos, saldo estimado),
  cuotas activas, suscripciones y pagos realizados. Nada se convierte: cada
  moneda se informa por separado.

### Ingresos

- Los **ingresos recurrentes se pueden eliminar** (antes sólo se podían pausar).
  Los ingresos que ya entraron quedan en el historial y dejan de acreditarse.

### Interfaz

- El **sidebar** ya no repite "Configuración" abajo del perfil: queda sólo el
  ítem de arriba y la tuerca dentro del chip de perfil, que abre tu perfil.
- En **Perfil**, los tags de tarjetas y categorías ya no quedan pegados al
  subtítulo de la tarjeta.

## 0.2.5 — 2026-10-10

### Primer arranque

- Nuevo **asistente de primer arranque** en cinco pasos: tu nombre, los modelos,
  las cuentas, el sueldo o ingreso y el primer resumen (opcional). Nada se
  descarga solo: cada modelo se baja cuando lo pedís y con **barra de progreso**.
- Spark-X2.5-1.7B y el runtime de llama.cpp quedan como pasos **obligatorios**;
  para leer resúmenes se elige entre la **lectura rápida por columnas** (sin
  descargas) y **GLM-OCR**; **EmbeddingGemma-2** es opcional y mejora la memoria
  del copiloto.

### Dólares (USD)

- Se pueden crear **cuentas en dólares** y cargar ingresos en USD.
- El **dashboard muestra los pesos y, debajo, los dólares** en cada indicador (sin
  convertir: no hay tipo de cambio en la app).
- Los importes por moneda se informan por separado en cuentas, ingresos, total a
  pagar y en la planilla de Datos; editar una cuenta o un ingreso incluye la
  moneda.

### Perfil local

- Nueva pantalla de **Perfil** (el chip del sidebar y el engranaje al final):
  **nombre** (el copiloto te llama por tu nombre y el sidebar lo muestra),
  **tarjetas** (American Express, Mastercard, Visa, más las que agregues) y
  **categorías** de movimientos.
- Las categorías del perfil **se aplican solas** al importar un resumen: si el
  nombre de la categoría aparece en la descripción del consumo, gana esa; el
  resto usa las reglas de comercios conocidos.

### Documentos y revisión

- El detalle del documento suma un **toggle Información / Movimientos**: al pasar
  a movimientos, los consumos de la tarjeta aparecen **separados en consumos e
  impuestos y percepciones**.
- Las cuatro filas de datos (cierre, vencimiento, pago mínimo y total) ocupan el
  ancho completo y el **workflow termina la columna**: «Confirmado» es el último
  paso.
- En la revisión, **datos extraídos y movimientos del resumen tienen la misma
  altura** y los datos se organizan en **tres columnas**.
- **Arreglado**: el menú de tres puntos de los movimientos no respondía dentro de
  la revisión (quedaba detrás del diálogo).
- Al cargar un PDF aparece un **placeholder con animación** hasta que el resumen
  termina de leerse.

### Calendario, movimientos y señales

- **Próximos eventos** ya no muestra lo que pasó: sólo de hoy en adelante.
- La pantalla de **Movimientos** muestra todo lo extraído del resumen, incluidos
  los consumos del mes anterior (antes se filtraba sólo por el mes del movimiento).
- El dashboard **saca el botón de preguntarle a la IA** del encabezado y deja
  «Agregar dinero» y «Cargar resumen» al final de la fila; el período se elige con
  un **dropdown de meses** (en el dashboard y en Datos) en lugar de tipear.
- Las **señales para mirar** son concretas y automáticas: comparación mensual con
  la categoría que explica la diferencia, mayor gasto del mes y consumos en
  dólares.

### Ingresos

- Registrar un ingreso o un sueldo **exige una cuenta**: si no hay ninguna, la app
  explica y lleva a crearla (antes el sueldo entraba al balance y las cuentas
  quedaban en cero).
- El historial muestra la columna **Cuenta** y los tres puntos pasan al final.

### Copiloto y memoria

- Preguntas de consumos («¿cuáles fueron mis consumos?») **ya no caen en «fuera
  de alcance»**: responden con el total del período, las categorías con más peso y
  los consumos en dólares.
- **Memoria con embeddings**: se agregó **EmbeddingGemma-2** (Q8_0, 768
  dimensiones) como modelo opcional; cuando está descargado, el copiloto busca por
  significado en vez de por texto. Verificado en local: requiere **llama.cpp
  b11552** (la b10828 no carga el modelo). Sin el modelo, la memoria sigue
  funcionando con el embedding por hashing.

### OCR

- El extractor (prompt y heurística) **ignora el bloque saldado del período
  anterior**: SALDO ANTERIOR, SU PAGO y la devolución de impuestos no entran como
  consumos del período.

### Releases e infraestructura

- **Arreglado el release**: el build de macOS Intel pedía el runner `macos-13`,
  que GitHub ya no ofrece, así que quedaba «queued» para siempre y la release
  nunca se publicaba (quedaba vacía). Ahora usa `macos-15-intel`.
- El runtime de llama.cpp sube a **b11552** y el selector de binario prefiere la
  build fijada (antes podía quedarse con una vieja descargada en el mismo
  directorio).

## 0.2.1 — 2026-10-10

### Revisión de documentos

- **Marcar una zona del PDF** ahora usa el mismo lector por columnas que el OCR:
  antes esa zona se leía como texto plano, duplicaba lo que ya estaba leído y
  arrastraba el pie legal. Ahora respeta la zona marcada y no agrega de nuevo lo
  que ya venía del resumen.
- Se pueden **editar y borrar movimientos** desde la propia revisión (descripción,
  importe, moneda, fecha y tipo).
- La revisión **entra entera en la pantalla**: el PDF se ajusta al alto disponible
  y la lista de movimientos tiene su propio espacio; se terminaron el scroll de la
  ventana y la superposición de textos en los campos.
- El **emisor** y la **moneda** se eligen de listas (American Express /
  Mastercard / Visa / Otra; pesos / dólares) en vez de quedar como texto suelto.

### Documentos

- Se puede **borrar un documento** con sus movimientos, su pago del período, el
  PDF y los fragmentos de memoria.

### Historial de ingresos

- El menú de tres puntos **ya no lo corta el contenedor** (se dibuja sobre la
  interfaz, sin scroll) y la confirmación de borrado usa un diálogo chico con aire
  en lugar del modal de revisión.

### Copiloto

- **Fuera de alcance**: una pregunta que no es de finanzas (por ejemplo una
  cuenta) ya no se responde con el balance; el copiloto aclara para qué sirve.
- Las **fuentes ya no se mezclan en el texto** de la respuesta: van aparte,
  plegadas, al final.
- Respuestas por intención cuando no hay datos ("No tenés cuotas activas
  registradas") en vez de un texto genérico.
- Las **sugerencias de preguntas** solo aparecen con la conversación reiniciada.

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
