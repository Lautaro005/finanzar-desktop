# Seguridad

## Modelo de amenazas

FinanzAR Desktop es **local-first**. El objetivo es que ningún dato financiero
salga del equipo y que la superficie de red sea mínima.

- El backend escucha **solo** en `127.0.0.1` y rechaza cualquier host distinto en
  el arranque (`finanzar_backend/__main__.py`).
- Toda ruta recibida para abrir documentos se valida contra el directorio de
  documentos de la aplicación; se bloquea el *path traversal*
  (`resolve_document_path`).
- La CSP de Tauri no permite `eval`, scripts remotos ni HTML inseguro; solo se
  habilita `connect-src` hacia `127.0.0.1` e `ipc`.
- Los logs estructurados redactan números de tarjeta e importes.

## Red

La aplicación solo usa la red para:

1. descargar modelos en el primer arranque;
2. comprobar actualizaciones cada 3 horas;
3. descargar una actualización que la persona aceptó explícitamente.

No hay telemetría ni envío de documentos, texto OCR, balances o preguntas.

## Secretos

- No se versionan claves, tokens ni archivos `.env`.
- La clave privada del updater vive fuera del repositorio y se inyecta en el
  build con `TAURI_SIGNING_PRIVATE_KEY`.
- El acceso a Hugging Face se hace de forma anónima; no se requieren tokens.

## Reporte de vulnerabilidades

Escribí a los maintainers del repositorio con una descripción, pasos de
reproducción e impacto. Se priorizan: fuga de datos financieros, ejecución
remota de código y bypass del consentimiento del updater.
