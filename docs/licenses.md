# Licencias de terceros

FinanzAR Desktop combina código propio con modelos y runtimes de terceros. Este
documento resume licencias y obligaciones de atribución.

## Código del proyecto

| Componente | Licencia |
| --- | --- |
| FinanzAR Desktop (Rust, React/TS, Python) | **GNU AGPL-3.0** (`LICENSE`) |

**Por qué AGPL-3.0**: el pipeline de OCR usa **PyMuPDF**, que es AGPL-3.0 (o
licencia comercial paga). Distribuir el binario con PyMuPDF obliga a liberar el
código bajo AGPL-3.0. La consecuencia práctica es la buscada: cualquiera que
redistribuya la app —incluso vendiéndola— debe publicar su código fuente
completo. Para un producto cerrado habría que comprar la licencia comercial de
PyMuPDF y acordar otra licencia con el autor.

**Si en el futuro se quiere una licencia más permisiva**: hay que reemplazar
PyMuPDF por una librería permisiva que también renderice páginas (por ejemplo
`pypdfium2`, Apache-2.0/BSD-3). Mientras siga PyMuPDF, la app distribuida debe
ser AGPL-3.0.

## Modelos

| Modelo | Repositorio | Revisión | Licencia | Notas |
| --- | --- | --- | --- | --- |
| GLM-OCR | `zai-org/GLM-OCR` | `2e85a62840ccac27daa451df36c736c4636b8628` | MIT | Modelo multimodal 0.9B para document understanding. |
| PP-DocLayoutV3 | `PaddlePaddle/PP-DocLayoutV3` | `241f8bdfc77a7c7bee915a5057aaee58c235a8d3` | Apache-2.0 | Análisis de layout del pipeline OCR (opcional). |
| Spark-X2.5-1.7B-GGUF | `XHToken/Spark-X2.5-1.7B-GGUF` | `1f7fa33b1245c14730da39e125714ad3a327901b` | Apache-2.0 | Copiloto en cuantización `Q4_K_M`. |

## Runtimes y dependencias principales

| Componente | Licencia |
| --- | --- |
| llama.cpp (`llama-server`) — `ggml-org/llama.cpp` build `b10828` | MIT |
| Tauri 2 | MIT / Apache-2.0 |
| FastAPI, Starlette, Uvicorn | MIT / BSD |
| ChromaDB | Apache-2.0 |
| PyMuPDF | AGPL-3.0 / comercial |
| openpyxl | MIT |
| huggingface_hub | Apache-2.0 |
| PyTorch / Transformers (extra `ocr`) | BSD / Apache-2.0 |

## Atribución

- GLM-OCR: citar el reporte técnico del proyecto (arXiv:2603.10910) al redistribuir
  resultados derivados del modelo.
- llvm/llama.cpp: incluir el archivo `LICENSE` del runtime junto al binario
  descargado (el descargador conserva el contenido del archivo comprimido).
- PP-DocLayoutV3: incluir aviso de Apache-2.0 si se distribuye el modelo.

## Obligaciones antes de cada release

1. Re-verificar la licencia de cada modelo contra su model card.
2. Confirmar que la revisión fijada en `models/manifest.json` sigue publicada.
3. No incluir modelos, PDFs reales ni datos de usuario en el repositorio.
4. Conservar este documento y `LICENSE` en cada artefacto distribuido.
