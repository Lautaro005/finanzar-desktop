"""Pipeline de documentos: importar, OCR, extraer, persistir y confirmar.

Trazabilidad completa: cada campo y movimiento guarda confianza, página y bbox.
Nada se indexa en la memoria semántica hasta que el usuario confirma.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from ..chroma_store.store import MemoryStore
from ..config import Settings
from ..core.errors import ConflictError, NotFoundError
from ..core.events import EventBus
from ..core.ids import new_id
from ..core.money import cents_to_str
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


def _dedupe_transactions(items: list[Any]) -> list[Any]:
    """Elimina movimientos repetidos que el OCR puede devolver dos veces.

    Normaliza la descripción (solo alfanuméricos, minúsculas) y le quita
    puntuación colgante, para que variantes como ``Cuota notebook`` y
    ``Cuota notebook /`` colapsen en una sola. Se conserva la descripción más
    informativa (la más larga).
    """
    import re as _re

    seen: dict[tuple[str, int, str], Any] = {}
    for item in items:
        cleaned = _re.sub(r"\s+", " ", item.description.strip())
        cleaned = _re.sub(r"[\s\-·:|/.,]+$", "", cleaned)
        if cleaned:
            item.description = cleaned
        normalized = _re.sub(r"[^0-9a-záéíóúñ]+", "", item.description.lower())
        key = (item.occurred_on, item.amount_cents, normalized)
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

            extracted = extract_mod.extract_heuristic(page_texts)
            extracted.engine = engine.name

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

    def _period_from(self, extracted: extract_mod.ExtractedStatement) -> str | None:
        due = self._field_value(extracted, "due_date")
        if due:
            return str(due)[:7]
        return None

    def _persist_extraction(self, statement_id: str, extracted: extract_mod.ExtractedStatement) -> None:
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
        # El OCR puede devolver la misma línea dos veces; se deduplica antes de guardar.
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
