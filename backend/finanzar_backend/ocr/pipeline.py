"""Pipeline de documentos: importar, OCR, extraer, persistir y confirmar.

Trazabilidad completa: cada campo y movimiento guarda confianza, página y bbox.
Nada se indexa en la memoria semántica hasta que el usuario confirma.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from pathlib import Path
from typing import Any

from ..chroma_store.store import MemoryStore
from ..config import Settings
from ..core.errors import ConflictError, NotFoundError, ValidationError
from ..core.events import EventBus
from ..core.ids import new_id
from ..core.money import cents_to_str, to_cents
from ..db.repo import Repository
from ..db.sqlite import utcnow
from ..finance.engine import FinanceEngine, period_of, today
from ..finance.insights import refresh_insights
from . import extract as extract_mod
from . import pdf as pdf_mod
from .glm_ocr import build_engine

logger = logging.getLogger(__name__)


def checksum_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _norm_description(description: str) -> str:
    """Descripción comparable (solo alfanuméricos, minúsculas)."""
    return re.sub(r"[^0-9a-záéíóúñ]+", "", description.lower())


def _dedupe_transactions(items: list[Any]) -> list[Any]:
    """Elimina movimientos repetidos que el OCR puede devolver dos veces.

    Normaliza la descripción (solo alfanuméricos, minúsculas) y le quita
    puntuación colgante, para que variantes como ``Cuota notebook`` y
    ``Cuota notebook /`` colapsen en una sola. Se conserva la descripción más
    informativa (la más larga). La moneda forma parte de la clave: un consumo en
    dólares y su percepción en pesos suelen compartir fecha e importe y **no**
    son el mismo movimiento.
    """
    seen: dict[tuple[str, int, str, str], Any] = {}
    for item in items:
        cleaned = re.sub(r"\s+", " ", item.description.strip())
        cleaned = re.sub(r"[\s\-·:|/.,]+$", "", cleaned)
        if cleaned:
            item.description = cleaned
        normalized = _norm_description(item.description)
        key = (item.occurred_on, item.amount_cents, normalized, str(getattr(item, "currency", "ARS")))
        current = seen.get(key)
        if current is None or len(item.description) > len(current.description):
            seen[key] = item
    return list(seen.values())


class DocumentPipeline:
    def __init__(
        self,
        settings: Settings,
        repo: Repository,
        engine: FinanceEngine,
        memory: MemoryStore,
        bus: EventBus,
    ) -> None:
        self.settings = settings
        self.repo = repo
        self.engine = engine
        self.memory = memory
        self.bus = bus
        # Cliente del copiloto local; se inyecta desde el contexto cuando el
        # runtime está disponible (se usa solo como complemento de la lectura).
        self.llm_client: Any = None

    # -- almacenamiento ---------------------------------------------------
    def _store_original(self, content: bytes, filename: str, checksum: str) -> Path:
        suffix = Path(filename).suffix.lower() or ".pdf"
        target = self.settings.documents_dir / f"{checksum}{suffix}"
        if not target.exists():
            target.write_bytes(content)
        return target

    def glm_model_dir(self) -> Path | None:
        from ..models.manifest import load_manifest

        manifest = load_manifest()
        spec = manifest.model("glm-ocr")
        directory = self.settings.models_dir / spec.id / spec.revision
        if directory.exists():
            return directory
        return None

    # -- importar ---------------------------------------------------------
    def import_document(self, filename: str, content: bytes) -> dict[str, Any]:
        if not content:
            raise ConflictError("El archivo está vacío", code="empty_file")
        if not filename.lower().endswith(".pdf"):
            raise ConflictError("Por ahora solo se aceptan archivos PDF", code="unsupported_file")
        checksum = checksum_bytes(content)
        existing = self.repo.get_statement_by_checksum(checksum)
        if existing:
            raise ConflictError(
                f"Ese resumen ya fue importado como «{existing['filename']}»",
                code="duplicate_document",
                details={"statementId": existing["id"]},
            )
        stored = self._store_original(content, filename, checksum)
        try:
            pages = pdf_mod.page_count(stored)
        except Exception:
            pages = 0
        statement_id = new_id("doc")
        statement = self.repo.create_statement(
            statement_id,
            {
                "filename": filename,
                "checksum": checksum,
                "stored_path": str(stored),
                "pages": pages,
                "status": "imported",
                "period": period_of(today()),
            },
        )
        self.repo.db.execute(
            "INSERT INTO statement_chunks_index (id, statement_id, page, content_hash, indexed_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (new_id("idxcnt"), statement_id, None, checksum, utcnow()),
        )
        return statement

    # -- OCR + extracción -------------------------------------------------
    async def run_ocr(self, statement_id: str, prefer: str = "auto") -> dict[str, Any]:
        statement = self.repo.get_statement(statement_id)
        if not statement:
            raise NotFoundError("Documento no encontrado")
        job = await self.bus.create_job("ocr", {"statementId": statement_id})
        await self.bus.update_job(job, status="running", progress=0.05, message="Renderizando páginas")
        try:
            stored = Path(statement["stored_path"])
            pages = pdf_mod.render_pages(stored)
            engine = build_engine(stored, glm_model_dir=self.glm_model_dir(), prefer=prefer)
            await self.bus.update_job(
                job, progress=0.25, message=f"Reconociendo texto ({engine.name})"
            )
            page_texts = engine.run(pages)
            await self.bus.update_job(job, progress=0.6, message="Extrayendo datos estructurados")

            # El extractor por layout usa las coordenadas del PDF para separar la
            # columna de pesos de la de dólares. Si el PDF es escaneado (sin capa
            # de texto) no hay coordenadas y se cae al texto del OCR.
            extracted = extract_mod.extract_layout(stored)
            if extracted is None:
                extracted = extract_mod.extract_heuristic(page_texts)
            elif self._missing_critical(extracted):
                # El layout leyó los movimientos pero no el encabezado (etiquetas
                # distintas según el banco): se completa con la lectura por texto.
                extracted = extract_mod.merge_missing(extracted, extract_mod.extract_heuristic(page_texts))
            extracted.engine = engine.name if extracted.engine == "heuristic" else f"{engine.name}+layout"

            # Complemento con el copiloto local y el system prompt de resúmenes
            # argentinos: solo cuando falta información crítica y el runtime está.
            if self.llm_client is not None and self._missing_critical(extracted):
                await self.bus.update_job(job, progress=0.72, message="Completando con el copiloto local")
                extra = await asyncio.to_thread(extract_mod.extract_with_llm, self.llm_client, page_texts)
                if extra is not None:
                    extracted = extract_mod.merge_missing(extracted, extra)

            self._persist_extraction(statement_id, extracted)
            self._persist_payments(statement_id, extracted)
            self.repo.update_statement(
                statement_id,
                {
                    "status": "review",
                    "period": self._period_from(extracted) or statement.get("period"),
                    "close_date": self._field_value(extracted, "close_date"),
                    "due_date": self._field_value(extracted, "due_date"),
                    "total_cents": self._field_value(extracted, "total"),
                    "minimum_cents": self._field_value(extracted, "minimum"),
                    "currency": self._field_value(extracted, "currency") or statement.get("currency", "ARS"),
                    "pages": len(page_texts),
                },
            )
            await self.bus.update_job(job, status="done", progress=1.0, message="Extracción lista para revisar")
            return {
                "statementId": statement_id,
                "engine": extracted.engine,
                "fields": len(extracted.fields),
                "transactions": len(extracted.transactions),
                "installments": len(extracted.installments),
                "subscriptions": len(extracted.subscriptions),
            }
        except Exception as exc:  # pragma: no cover - errores del modelo
            logger.warning("OCR falló para %s: %s", statement_id, exc)
            self.repo.update_statement(statement_id, {"status": "error"})
            await self.bus.update_job(job, status="error", message=str(exc), error=str(exc))
            raise

    def _field_value(self, extracted: extract_mod.ExtractedStatement, key: str) -> Any:
        field = extracted.field_map().get(key)
        return field.value if field else None

    @staticmethod
    def _missing_critical(extracted: extract_mod.ExtractedStatement) -> bool:
        """¿Falta algún dato sin el cual el resumen queda incompleto?"""
        fields = extracted.field_map()
        for key in ("due_date", "total", "minimum"):
            if key not in fields or fields[key].value is None:
                return True
        return not (extracted.transactions or extracted.installments or extracted.subscriptions)

    def _period_from(self, extracted: extract_mod.ExtractedStatement) -> str | None:
        due = self._field_value(extracted, "due_date")
        if due:
            return str(due)[:7]
        return None

    def _persist_extraction(self, statement_id: str, extracted: extract_mod.ExtractedStatement) -> None:
        # Volver a correr el OCR no debe duplicar ni mezclar datos del intento
        # anterior: se limpia la extracción previa del documento.
        self.repo.clear_statement_extraction(statement_id)
        for field in extracted.fields:
            self.repo.upsert_statement_field(
                new_id("fld"),
                statement_id,
                {
                    "field_key": field.key,
                    "field_value": cents_to_str(field.value)
                    if field.value_type == "money" and field.value is not None
                    else (str(field.value) if field.value is not None else None),
                    "value_type": field.value_type,
                    "confidence": field.confidence,
                    "source_page": field.page,
                    "source_bbox": field.bbox,
                    "evidence_text": field.evidence,
                    "status": "pending",
                },
            )
        # El OCR puede devolver la misma línea dos veces; se deduplica antes de
        # guardar. La extracción por layout, en cambio, lee las filas reales del
        # PDF: si el resumen lista dos veces una percepción idéntica, se conserva.
        if "layout" not in extracted.engine:
            extracted.transactions = _dedupe_transactions(extracted.transactions)
            extracted.installments = _dedupe_transactions(extracted.installments)
            extracted.subscriptions = _dedupe_transactions(extracted.subscriptions)

        rows = []
        for tx in [*extracted.transactions, *extracted.installments, *extracted.subscriptions]:
            content_hash = hashlib.sha256(
                f"{tx.occurred_on}|{tx.description}|{tx.amount_cents}".encode()
            ).hexdigest()
            rows.append(
                {
                    "id": new_id("tx"),
                    "statement_id": statement_id,
                    "occurred_on": tx.occurred_on,
                    "description": tx.description,
                    "normalized_description": tx.description.lower(),
                    "category": tx.category,
                    "amount_cents": tx.amount_cents,
                    "currency": tx.currency,
                    "installment_number": tx.installment_number,
                    "installment_total": tx.installment_total,
                    "kind": tx.kind,
                    "confirmed": 0,
                    "source_page": tx.page,
                    "source_bbox": tx.bbox,
                    "confidence": tx.confidence,
                    "content_hash": content_hash,
                }
            )
        self.repo.insert_transactions(rows)
        self.repo.insert_installments(
            [
                {
                    "id": new_id("ins"),
                    "statement_id": statement_id,
                    "description": tx.description,
                    "installment_number": tx.installment_number,
                    "installment_total": tx.installment_total,
                    "amount_cents": tx.amount_cents,
                    "currency": tx.currency,
                    "first_period": period_of(today()),
                    "remaining": (tx.installment_total or 0) - (tx.installment_number or 0),
                }
                for tx in extracted.installments
                if tx.installment_number and tx.installment_total
            ]
        )
        for tx in extracted.subscriptions:
            self.repo.upsert_subscription(
                f"sub_{hashlib.sha256(tx.description.lower().encode()).hexdigest()[:16]}",
                {
                    "name": tx.description,
                    "amount_cents": tx.amount_cents,
                    "currency": tx.currency,
                    "last_seen_period": tx.occurred_on[:7],
                    "active": True,
                },
            )

    def _persist_payments(self, statement_id: str, extracted: extract_mod.ExtractedStatement) -> None:
        statement = self.repo.get_statement(statement_id)
        total = self._field_value(extracted, "total")
        due = self._field_value(extracted, "due_date")
        if total is None or due is None:
            return
        amount_cents = int(total)
        self.repo.upsert_payment(
            new_id("pay"),
            {
                "statement_id": statement_id,
                "card_id": statement.get("card_id") if statement else None,
                "due_date": str(due),
                "amount_cents": amount_cents,
                "currency": self._field_value(extracted, "currency") or "ARS",
                "kind": "total",
                "status": "pending",
            },
        )

    # -- revisión y confirmación -----------------------------------------
    def page_image(self, statement_id: str, page: int = 1, dpi: int = 150) -> tuple[bytes, float, float]:
        """PNG de una página del PDF y su tamaño en puntos (para mapear bboxes)."""
        statement = self.repo.get_statement(statement_id)
        if not statement:
            raise NotFoundError("Documento no encontrado")
        stored = Path(statement["stored_path"])
        if not stored.exists():
            raise NotFoundError("El PDF original ya no está disponible")
        png, _, _ = pdf_mod.page_png(stored, page, dpi=dpi)
        width, height = pdf_mod.page_size(stored, page)
        return png, width, height

    def preview_text(self, statement_id: str, page: int, rect: tuple[float, float, float, float]) -> str:
        """Texto nativo dentro de una región: lectura instantánea sin OCR."""
        statement = self.repo.get_statement(statement_id)
        if not statement:
            raise NotFoundError("Documento no encontrado")
        stored = Path(statement["stored_path"])
        try:
            return pdf_mod.page_text_in_rect(stored, page, rect)
        except Exception:
            return ""

    async def extract_regions(
        self, statement_id: str, page: int, regions: list[list[float]], prefer: str = "auto"
    ) -> dict[str, Any]:
        """Lee las regiones que marcó la persona y agrega esos consumos.

        Primero intenta el texto nativo del PDF (exacto y rápido) y, si la
        región no tiene capa de texto, cae al motor de OCR.
        """
        statement = self.repo.get_statement(statement_id)
        if not statement:
            raise NotFoundError("Documento no encontrado")
        stored = Path(statement["stored_path"])
        if not stored.exists():
            raise NotFoundError("El PDF original ya no está disponible")
        if not regions:
            raise ValidationError("Marcá al menos una región del documento")

        # Movimientos que ya tiene el documento: marcar una zona que pisa un
        # consumo ya leído no debe duplicarlo. Se compara por fecha, importe,
        # moneda y tipo, porque el recorte de la zona puede cortar la descripción.
        existing = {
            (tx["occurred_on"], tx["amount_cents"], tx["currency"], tx["kind"])
            for tx in self.repo.list_transactions()
            if tx.get("statement_id") == statement_id
        }
        rows: list[dict[str, Any]] = []
        used_ocr = False
        skipped = 0
        for region in regions:
            if len(region) != 4:
                continue
            rect = (float(region[0]), float(region[1]), float(region[2]), float(region[3]))
            zone = {"page": page, "x0": rect[0], "y0": rect[1], "x1": rect[2], "y1": rect[3]}
            extracted = extract_mod.extract_layout(stored, region=zone)
            if extracted is None:
                # PDF sin capa de texto: se recorta la zona y se la manda al OCR.
                text = pdf_mod.page_text_in_rect(stored, page, rect)
                if not text.strip():
                    used_ocr = True
                    rendered = pdf_mod.render_region(stored, page, rect)
                    if rendered is None:
                        continue
                    engine = build_engine(stored, glm_model_dir=self.glm_model_dir(), prefer=prefer)
                    text = "\n".join(p.text for p in engine.run([rendered]))
                extracted = extract_mod.extract_heuristic(
                    [extract_mod.PageText(number=page, text=text, engine="region")]
                )
            for tx in [*extracted.transactions, *extracted.installments, *extracted.subscriptions]:
                key = (tx.occurred_on, tx.amount_cents, tx.currency, tx.kind)
                if key in existing:
                    skipped += 1
                    continue
                existing.add(key)
                rows.append(
                    {
                        "id": new_id("tx"),
                        "statement_id": statement_id,
                        "occurred_on": tx.occurred_on,
                        "description": tx.description,
                        "normalized_description": tx.description.lower(),
                        "category": tx.category,
                        "amount_cents": tx.amount_cents,
                        "currency": tx.currency,
                        "installment_number": tx.installment_number,
                        "installment_total": tx.installment_total,
                        "kind": tx.kind,
                        "confirmed": 0,
                        "source_page": tx.page or page,
                        "source_bbox": tx.bbox or list(rect),
                        "confidence": tx.confidence,
                        "content_hash": hashlib.sha256(
                            f"{tx.occurred_on}|{tx.description}|{tx.amount_cents}|{page}".encode()
                        ).hexdigest(),
                    }
                )
        if rows:
            self.repo.insert_transactions(rows)
        return {
            "transactions": [
                tx
                for tx in self.repo.list_transactions()
                if tx.get("statement_id") == statement_id
            ],
            "engine": "ocr" if used_ocr else "layout",
            "regions": len(regions),
            "added": len(rows),
            "skipped": skipped,
        }

    def delete_document(self, statement_id: str) -> dict[str, Any]:
        """Borra un documento: la fila, sus movimientos, el PDF y sus fragmentos."""
        statement = self.repo.get_statement(statement_id)
        if not statement:
            raise NotFoundError("Documento no encontrado")
        stored = Path(statement["stored_path"])
        # Los fragmentos de memoria semántica no están en SQLite.
        for collection in ("statement_chunks", "transaction_notes"):
            try:
                self.memory.delete_where(collection, {"statement_id": statement_id})
            except Exception as exc:  # pragma: no cover - memoria no disponible
                logger.debug("No se pudieron borrar fragmentos de %s: %s", collection, exc)
        self.repo.delete_statement(statement_id)
        try:
            stored.unlink(missing_ok=True)
        except OSError as exc:  # pragma: no cover - permisos
            logger.warning("No se pudo borrar el PDF %s: %s", stored, exc)
        self.engine.refresh_calendar()
        refresh_insights(self.engine, period_of(today()))
        return {"deleted": True, "statementId": statement_id}

    def add_transactions(self, statement_id: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Agrega movimientos cargados a mano a un documento."""
        if not self.repo.get_statement(statement_id):
            raise NotFoundError("Documento no encontrado")
        rows = []
        for item in items:
            occurred_on = item.get("occurredOn") or today().isoformat()
            description = str(item.get("description") or "").strip()
            if not description:
                continue
            amount = item.get("amountCents")
            if amount is None:
                amount = to_cents(str(item.get("amount") or "0"))
            rows.append(
                {
                    "id": new_id("tx"),
                    "statement_id": statement_id,
                    "occurred_on": occurred_on,
                    "description": description[:120],
                    "normalized_description": description.lower(),
                    "category": item.get("category"),
                    "amount_cents": int(amount),
                    "currency": item.get("currency") or "ARS",
                    "kind": item.get("kind") or "purchase",
                    "confirmed": 0,
                    "source_page": item.get("page"),
                    "source_bbox": item.get("bbox"),
                    "confidence": 1.0,
                    "content_hash": hashlib.sha256(
                        f"{occurred_on}|{description}|{amount}|{item.get('page')}".encode()
                    ).hexdigest(),
                }
            )
        if rows:
            self.repo.insert_transactions(rows)
        return self.repo.list_transactions()

    def review(self, statement_id: str) -> dict[str, Any]:
        statement = self.repo.get_statement(statement_id)
        if not statement:
            raise NotFoundError("Documento no encontrado")
        return {
            "statement": statement,
            "fields": self.repo.list_statement_fields(statement_id),
            "transactions": self.repo.list_transactions(),
        }

    def patch_fields(self, statement_id: str, patches: list[dict[str, Any]]) -> dict[str, Any]:
        if not self.repo.get_statement(statement_id):
            raise NotFoundError("Documento no encontrado")
        updated = []
        for patch in patches:
            field_key = patch.get("fieldKey") or patch.get("field_key")
            if not field_key:
                continue
            value = patch.get("value")
            payload: dict[str, Any] = {"status": "edited", "confirmed_at": utcnow()}
            if value is not None:
                payload["field_value"] = str(value)
            field = self.repo.patch_statement_field(statement_id, field_key, payload)
            if field:
                updated.append(field)
            self._propagate_field(statement_id, field_key, value)
        return {"fields": updated}

    def _propagate_field(self, statement_id: str, field_key: str, value: Any) -> None:
        mapping = {
            "total": "total_cents",
            "minimum": "minimum_cents",
            "due_date": "due_date",
            "close_date": "close_date",
        }
        if field_key in mapping and value is not None:
            from ..core.money import to_cents

            raw: Any = value
            if field_key in {"total", "minimum"}:
                try:
                    raw = to_cents(str(value))
                except Exception:
                    return
            self.repo.update_statement(statement_id, {mapping[field_key]: raw})

    def confirm(self, statement_id: str) -> dict[str, Any]:
        statement = self.repo.get_statement(statement_id)
        if not statement:
            raise NotFoundError("Documento no encontrado")
        now = utcnow()
        self.repo.update_statement(statement_id, {"status": "confirmed", "confirmed_at": now})
        self.repo.db.execute(
            "UPDATE transactions SET confirmed = 1 WHERE statement_id = ? AND user_id = ?",
            (statement_id, self.repo.user_id),
        )
        for field in self.repo.list_statement_fields(statement_id):
            self.repo.patch_statement_field(
                statement_id, field["field_key"], {"status": "confirmed", "confirmed_at": now}
            )
        self.repo.audit("document.confirm", entity="statements", entity_id=statement_id)
        indexed = self._index_confirmed(statement_id)
        self.engine.refresh_calendar()
        refresh_insights(self.engine, statement.get("period") or period_of(today()))
        return {"statement": self.repo.get_statement(statement_id), "indexedChunks": indexed}

    def _index_confirmed(self, statement_id: str) -> int:
        statement = self.repo.get_statement(statement_id)
        if not statement:
            return 0
        period = statement.get("period")
        card_id = statement.get("card_id")
        chunks = 0
        for tx in self.repo.list_transactions(confirmed=True):
            if tx.get("statement_id") != statement_id:
                continue
            text = (
                f"{tx['occurred_on']} {tx['description']} "
                f"{cents_to_str(tx['amount_cents'])} {tx.get('category') or ''}"
            )
            self.memory.index_document(
                "transaction_notes",
                doc_id=f"tx:{tx['id']}",
                text=text,
                metadata={
                    "statement_id": statement_id,
                    "page": tx.get("source_page"),
                    "period": period,
                    "card_id": card_id,
                    "confirmed": True,
                    "source_type": "transaction",
                    "user_id": self.repo.user_id,
                },
            )
            chunks += 1
        header = (
            f"Resumen {statement['filename']} período {period} "
            f"total {cents_to_str(statement.get('total_cents') or 0)}"
        )
        self.memory.index_document(
            "statement_chunks",
            doc_id=f"stmt:{statement_id}",
            text=header,
            metadata={
                "statement_id": statement_id,
                "page": 1,
                "period": period,
                "card_id": card_id,
                "confirmed": True,
                "source_type": "statement",
                "user_id": self.repo.user_id,
            },
        )
        return chunks + 1
