"""Rutas HTTP del backend local.

Todas las respuestas usan el envelope ``{ok, data, error, request_id}``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .. import __version__
from ..core.envelope import ok
from ..core.errors import NotFoundError, ValidationError
from ..core.money import to_cents
from ..db.sqlite import utcnow
from ..finance.engine import month_bounds, period_of, today
from ..finance.insights import refresh_insights
from ..llm.copilot import detect_intents
from .deps import AppContext

router = APIRouter()


def ctx(request: Request) -> AppContext:
    return request.app.state.ctx  # type: ignore[no-any-return]


def _money(cents: int | None, amount: str | None) -> int:
    if cents is not None:
        return int(cents)
    if amount is not None:
        return to_cents(amount)
    raise ValidationError("Falta el importe (amountCents o amount)")


def _require_account(context: AppContext, account_id: str | None) -> str:
    """Un ingreso o sueldo va a una cuenta.

    Sin cuenta, la plata entra al balance pero no aparece en ninguna cuenta (esa
    fue la confusión: el sueldo se registraba y las cuentas quedaban en cero).
    """
    if not context.repo.list_accounts():
        raise ValidationError(
            "Primero agregá una cuenta: el ingreso se acredita en la cuenta que elijas.",
            code="account_required",
        )
    if not account_id:
        raise ValidationError("Elegí la cuenta donde entra el ingreso", code="account_required")
    if context.repo.get_account(account_id) is None:
        raise ValidationError("La cuenta elegida no existe", code="account_not_found")
    return account_id


# --- modelos de entrada -------------------------------------------------
class AccountCreate(BaseModel):
    name: str
    kind: str = "bank"
    currency: str = "ARS"
    openingBalanceCents: int | None = None
    openingBalance: str | None = None
    institution: str | None = None
    maskedNumber: str | None = None
    closeDay: int | None = None
    dueDay: int | None = None
    notes: str | None = None


class AccountPatch(BaseModel):
    name: str | None = None
    kind: str | None = None
    currency: str | None = None
    openingBalanceCents: int | None = None
    institution: str | None = None
    maskedNumber: str | None = None
    closeDay: int | None = None
    dueDay: int | None = None
    archived: bool | None = None
    notes: str | None = None


class CardCreate(BaseModel):
    name: str
    brand: str = "other"
    last4: str | None = None
    accountId: str | None = None
    currency: str = "ARS"
    closeDay: int | None = None
    dueDay: int | None = None


class IncomeCreate(BaseModel):
    amountCents: int | None = None
    amount: str | None = None
    source: str = "Ingreso"
    kind: str = "punctual"
    accountId: str | None = None
    currency: str = "ARS"
    occurredOn: str | None = None
    note: str | None = None


class RecurringIncomeCreate(BaseModel):
    name: str
    source: str | None = None
    kind: str = "salary"
    amountCents: int | None = None
    amount: str | None = None
    accountId: str | None = None
    currency: str = "ARS"
    dayOfMonth: int = Field(default=1, ge=1, le=31)
    startDate: str
    endDate: str | None = None
    active: bool = True
    repeatRule: str = "monthly"
    inflationPct: float = 0.0


class TransactionCreate(BaseModel):
    occurredOn: str
    description: str
    amountCents: int | None = None
    amount: str | None = None
    category: str | None = None
    kind: str = "purchase"
    cardId: str | None = None
    statementId: str | None = None
    confirmed: bool = False


class TransactionPatch(BaseModel):
    category: str | None = None
    description: str | None = None
    kind: str | None = None
    confirmed: bool | None = None
    occurredOn: str | None = None
    currency: str | None = None
    amountCents: int | None = None
    amount: str | None = None


class GoalCreate(BaseModel):
    name: str
    targetCents: int | None = None
    target: str | None = None
    savedCents: int = 0
    currency: str = "ARS"
    accountId: str | None = None
    salaryPercent: float | None = None
    targetDate: str | None = None


class IncomePatch(BaseModel):
    amountCents: int | None = None
    amount: str | None = None
    source: str | None = None
    kind: str | None = None
    accountId: str | None = None
    currency: str | None = None
    occurredOn: str | None = None
    note: str | None = None


class RegionExtract(BaseModel):
    page: int = 1
    regions: list[list[float]] = Field(default_factory=list)


class DocumentTransactionCreate(BaseModel):
    occurredOn: str
    description: str
    amountCents: int | None = None
    amount: str | None = None
    currency: str = "ARS"
    kind: str = "purchase"
    page: int | None = None
    bbox: list[float] | None = None


class DocumentTransactionsBody(BaseModel):
    transactions: list[DocumentTransactionCreate] = Field(default_factory=list)


class CopilotChat(BaseModel):
    question: str
    month: str | None = None


class ModelsDownload(BaseModel):
    modelId: str
    quantization: str | None = None


class ModelsCancel(BaseModel):
    modelId: str


class ExportRequest(BaseModel):
    month: str | None = None
    path: str | None = None


class SettingsPatch(BaseModel):
    values: dict[str, Any]


class FieldPatch(BaseModel):
    fields: list[dict[str, Any]]


class PaymentPatch(BaseModel):
    status: str


# --- salud y bootstrap --------------------------------------------------
@router.get("/health")
async def health(request: Request) -> Any:
    context = ctx(request)
    return ok(
        {
            "status": "ok",
            "version": __version__,
            "schemaVersion": context.db.schema_version(),
            "llmAvailable": bool(context.llama_client and context.llama_client.available()),
            "llmPort": context.llama_port,
            "memoryBackend": context.memory.backend,
            "clientRequests": context.request_stats,
            "time": utcnow(),
        }
    )


@router.get("/api/llm/status")
async def llm_status(request: Request) -> Any:
    context = ctx(request)
    return ok(
        {
            "available": bool(context.llama_client and context.llama_client.available()),
            "baseUrl": context.llama_client.base_url if context.llama_client else None,
            "port": context.llama_port,
        }
    )


@router.get("/api/llm/embeddings")
async def embeddings_status(request: Request) -> Any:
    """Estado de los embeddings locales (embeddinggemma-2) y de la memoria."""
    return ok(ctx(request).embeddings_status())


@router.post("/api/llm/embeddings/start")
async def embeddings_start(request: Request) -> Any:
    """Levanta el servidor de embeddings si el modelo está descargado."""
    return ok(await asyncio.to_thread(ctx(request).start_embeddings))


@router.get("/api/bootstrap")
async def bootstrap(request: Request) -> Any:
    context = ctx(request)
    return ok(
        {
            "version": __version__,
            "schemaVersion": context.db.schema_version(),
            "dataDir": str(context.settings.data_dir),
            "models": context.downloader.statuses(),
            "runtime": context.downloader.runtime_status(_target()),
            "llmAvailable": bool(context.llama_client and context.llama_client.available()),
            "embeddings": context.embeddings_status(),
            "settings": context.repo.all_settings(),
            "period": period_of(today()),
        }
    )


def _target() -> str:
    from ..llm.llama_server import current_target

    return current_target()


# --- modelos ------------------------------------------------------------
@router.get("/api/models/status")
async def models_status(request: Request, quantization: str | None = None) -> Any:
    context = ctx(request)
    return ok(
        {
            "models": context.downloader.statuses(quantization),
            "runtime": context.downloader.runtime_status(_target()),
            "llmAvailable": bool(context.llama_client and context.llama_client.available()),
        }
    )


@router.post("/api/models/download")
async def models_download(request: Request, payload: ModelsDownload) -> Any:
    context = ctx(request)
    result = await context.downloader.download(payload.modelId, payload.quantization)
    if payload.modelId == "spark-x2.5-1.7b":
        context.start_llama()
    return ok(result)


@router.post("/api/models/cancel")
async def models_cancel(request: Request, payload: ModelsCancel) -> Any:
    context = ctx(request)
    return ok({"cancelled": context.downloader.cancel(payload.modelId)})


@router.post("/api/models/runtime/download")
async def runtime_download(request: Request) -> Any:
    context = ctx(request)
    status = await context.downloader.download_runtime(_target())
    return ok(status)


@router.post("/api/llm/start")
async def llm_start(request: Request) -> Any:
    context = ctx(request)
    return ok(context.start_llama())


# --- cuentas y tarjetas -------------------------------------------------
@router.get("/api/accounts")
async def list_accounts(request: Request, includeArchived: bool = False) -> Any:
    context = ctx(request)
    return ok({"accounts": context.repo.list_accounts(include_archived=includeArchived)})


@router.post("/api/accounts")
async def create_account(request: Request, payload: AccountCreate) -> Any:
    from ..core.ids import new_id

    context = ctx(request)
    data = payload.model_dump()
    if payload.openingBalanceCents is not None:
        data["opening_balance_cents"] = int(payload.openingBalanceCents)
    elif payload.openingBalance:
        data["opening_balance_cents"] = to_cents(payload.openingBalance)
    else:
        data["opening_balance_cents"] = 0
    data["masked_number"] = payload.maskedNumber
    data["close_day"] = payload.closeDay
    data["due_day"] = payload.dueDay
    account = context.repo.create_account(new_id("acc"), data)
    return ok({"account": account})


@router.patch("/api/accounts/{account_id}")
async def patch_account(request: Request, account_id: str, payload: AccountPatch) -> Any:
    context = ctx(request)
    patch = {
        "name": payload.name,
        "kind": payload.kind,
        "currency": payload.currency,
        "opening_balance_cents": payload.openingBalanceCents,
        "institution": payload.institution,
        "masked_number": payload.maskedNumber,
        "close_day": payload.closeDay,
        "due_day": payload.dueDay,
        "archived": payload.archived,
        "notes": payload.notes,
    }
    patch = {k: v for k, v in patch.items() if v is not None}
    account = context.repo.update_account(account_id, patch)
    if account is None:
        raise NotFoundError("Cuenta no encontrada")
    return ok({"account": account})


@router.get("/api/cards")
async def list_cards(request: Request) -> Any:
    context = ctx(request)
    return ok({"cards": context.repo.list_cards()})


@router.post("/api/cards")
async def create_card(request: Request, payload: CardCreate) -> Any:
    from ..core.ids import new_id

    context = ctx(request)
    card = context.repo.create_card(
        new_id("card"),
        {
            "name": payload.name,
            "brand": payload.brand,
            "last4": payload.last4,
            "account_id": payload.accountId,
            "currency": payload.currency,
            "close_day": payload.closeDay,
            "due_day": payload.dueDay,
        },
    )
    return ok({"card": card})


# --- ingresos -----------------------------------------------------------
@router.get("/api/incomes")
async def list_incomes(request: Request) -> Any:
    context = ctx(request)
    return ok(
        {
            "entries": context.repo.list_income_entries(),
            "recurring": context.repo.list_recurring_income(),
        }
    )


@router.post("/api/incomes")
async def create_income(request: Request, payload: IncomeCreate) -> Any:
    from ..core.ids import new_id

    context = ctx(request)
    amount_cents = _money(payload.amountCents, payload.amount)
    account_id = _require_account(context, payload.accountId)
    entry = context.repo.upsert_income_entry(
        new_id("inc"),
        {
            "account_id": account_id,
            "source": payload.source,
            "kind": payload.kind,
            "amount_cents": amount_cents,
            "currency": payload.currency,
            "occurred_on": payload.occurredOn or today().isoformat(),
            "note": payload.note,
        },
    )
    return ok({"entry": entry, "balanceCents": context.engine.consolidated_balance()})


@router.post("/api/incomes/recurring")
async def create_recurring_income(request: Request, payload: RecurringIncomeCreate) -> Any:
    from ..core.ids import new_id

    context = ctx(request)
    account_id = _require_account(context, payload.accountId)
    income = context.repo.create_recurring_income(
        new_id("rec"),
        {
            "name": payload.name,
            "source": payload.source or payload.name,
            "kind": payload.kind,
            "amount_cents": _money(payload.amountCents, payload.amount),
            "account_id": account_id,
            "currency": payload.currency,
            "day_of_month": payload.dayOfMonth,
            "start_date": payload.startDate,
            "end_date": payload.endDate,
            "active": payload.active,
            "repeat_rule": payload.repeatRule,
            "inflation_pct": payload.inflationPct,
        },
    )
    created = context.engine.apply_recurring_income()
    context.engine.refresh_calendar()
    return ok({"recurring": income, "applied": created, "balanceCents": context.engine.consolidated_balance()})


@router.patch("/api/incomes/recurring/{income_id}")
async def patch_recurring_income(request: Request, income_id: str, payload: dict[str, Any]) -> Any:
    context = ctx(request)
    if payload.get("accountId"):
        _require_account(context, payload["accountId"])
    mapping = {
        "name": "name",
        "source": "source",
        "kind": "kind",
        "amountCents": "amount_cents",
        "accountId": "account_id",
        "currency": "currency",
        "dayOfMonth": "day_of_month",
        "startDate": "start_date",
        "endDate": "end_date",
        "active": "active",
        "repeatRule": "repeat_rule",
        "inflationPct": "inflation_pct",
    }
    patch = {mapping[k]: v for k, v in payload.items() if k in mapping and v is not None}
    income = context.repo.update_recurring_income(income_id, patch)
    if income is None:
        raise NotFoundError("Ingreso recurrente no encontrado")
    context.engine.refresh_calendar()
    return ok({"recurring": income})


@router.delete("/api/incomes/recurring/{income_id}")
async def delete_recurring_income(request: Request, income_id: str) -> Any:
    """Elimina el ingreso automático. El historial ya acreditado se conserva."""
    context = ctx(request)
    if not context.repo.delete_recurring_income(income_id):
        raise NotFoundError("Ingreso recurrente no encontrado")
    context.engine.refresh_calendar()
    refresh_insights(context.engine, period_of(today()))
    return ok({"deleted": True, "balanceCents": context.engine.consolidated_balance()})


@router.patch("/api/incomes/{entry_id}")
async def patch_income(request: Request, entry_id: str, payload: IncomePatch) -> Any:
    context = ctx(request)
    if payload.accountId is not None:
        _require_account(context, payload.accountId)
    patch: dict[str, Any] = {
        "source": payload.source,
        "kind": payload.kind,
        "currency": payload.currency,
        "occurred_on": payload.occurredOn,
        "account_id": payload.accountId,
        "note": payload.note,
    }
    if payload.amountCents is not None or payload.amount is not None:
        patch["amount_cents"] = _money(payload.amountCents, payload.amount)
    patch = {k: v for k, v in patch.items() if v is not None}
    entry = context.repo.update_income_entry(entry_id, patch)
    if entry is None:
        raise NotFoundError("Ingreso no encontrado")
    return ok({"entry": entry, "balanceCents": context.engine.consolidated_balance()})


@router.delete("/api/incomes/{entry_id}")
async def delete_income(request: Request, entry_id: str) -> Any:
    context = ctx(request)
    if not context.repo.delete_income_entry(entry_id):
        raise NotFoundError("Ingreso no encontrado")
    return ok({"deleted": True, "balanceCents": context.engine.consolidated_balance()})


# --- dashboard ----------------------------------------------------------
@router.get("/api/dashboard")
async def dashboard(request: Request, month: str | None = None) -> Any:
    context = ctx(request)
    period = month or period_of(today())
    context.engine.refresh_calendar()
    refresh_insights(context.engine, period)
    return ok(context.engine.dashboard(period))


@router.get("/api/insights")
async def insights(request: Request, month: str | None = None) -> Any:
    context = ctx(request)
    period = month or period_of(today())
    refresh_insights(context.engine, period)
    return ok({"insights": context.repo.list_insights(), "period": period})


@router.get("/api/installments")
async def list_installments(request: Request) -> Any:
    context = ctx(request)
    return ok({"installments": context.repo.list_installments()})


@router.get("/api/subscriptions")
async def list_subscriptions(request: Request) -> Any:
    context = ctx(request)
    return ok({"subscriptions": context.repo.list_subscriptions()})


@router.get("/api/commitments")
async def commitments(request: Request) -> Any:
    context = ctx(request)
    return ok(context.engine.commitments())


@router.get("/api/goals")
async def list_goals(request: Request) -> Any:
    context = ctx(request)
    return ok({"goals": context.repo.list_goals(), "emergencyFund": context.engine.emergency_fund()})


@router.post("/api/goals")
async def create_goal(request: Request, payload: GoalCreate) -> Any:
    from ..core.ids import new_id

    context = ctx(request)
    goal = context.repo.upsert_goal(
        new_id("goal"),
        {
            "name": payload.name,
            "target_cents": _money(payload.targetCents, payload.target),
            "saved_cents": payload.savedCents,
            "currency": payload.currency,
            "account_id": payload.accountId,
            "salary_percent": payload.salaryPercent,
            "target_date": payload.targetDate,
        },
    )
    return ok({"goal": goal})


# --- documentos ---------------------------------------------------------
@router.get("/api/documents")
async def list_documents(request: Request) -> Any:
    context = ctx(request)
    return ok({"documents": context.repo.list_statements()})


@router.post("/api/documents/import")
async def import_document(request: Request, file: UploadFile = File(...)) -> Any:
    context = ctx(request)
    content = await file.read()
    statement = context.pipeline.import_document(file.filename or "resumen.pdf", content)
    return ok({"document": statement})


@router.post("/api/documents/{document_id}/ocr")
async def document_ocr(request: Request, document_id: str, prefer: str = "auto") -> Any:
    context = ctx(request)
    # El copiloto local se usa como complemento del extractor (system prompt con
    # el contexto de los resúmenes argentinos).
    context.pipeline.llm_client = context.llama_client
    result = await context.pipeline.run_ocr(document_id, prefer=prefer)
    return ok(result)


@router.get("/api/documents/{document_id}/review")
async def document_review(request: Request, document_id: str) -> Any:
    context = ctx(request)
    review = context.pipeline.review(document_id)
    review["transactions"] = [
        tx for tx in review["transactions"] if tx.get("statement_id") == document_id
    ]
    return ok(review)


@router.delete("/api/documents/{document_id}")
async def document_delete(request: Request, document_id: str) -> Any:
    """Borra un documento con sus movimientos y su PDF."""
    context = ctx(request)
    return ok(context.pipeline.delete_document(document_id))


@router.get("/api/documents/{document_id}/page")
async def document_page(request: Request, document_id: str, page: int = 1, dpi: int = 150) -> Any:
    """Imagen de una página del PDF importado, como data URL.

    Se devuelve en base64 dentro del envelope para que la ventana de la app la
    muestre sin pedir un binario aparte al puente de Tauri.
    """
    import base64

    from ..ocr import pdf as pdf_mod

    context = ctx(request)
    png, width, height = context.pipeline.page_image(document_id, page=page, dpi=dpi)
    statement = context.repo.get_statement(document_id)
    page_count = 0
    if statement:
        try:
            page_count = pdf_mod.page_count(Path(statement["stored_path"]))
        except Exception:
            page_count = 0
    image_width, image_height = 0, 0
    with contextlib.suppress(Exception):  # pragma: no cover - PNG siempre válido
        image_width, image_height = _png_size(png)
    return ok(
        {
            "page": page,
            "pageCount": page_count,
            "width": width,
            "height": height,
            "imageWidth": image_width,
            "imageHeight": image_height,
            "dataUrl": "data:image/png;base64," + base64.b64encode(png).decode("ascii"),
        }
    )


def _png_size(png: bytes) -> tuple[int, int]:
    """Ancho y alto de un PNG leyendo su cabecera IHDR."""
    import struct

    if len(png) < 24 or png[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("No es un PNG")
    width, height = struct.unpack(">II", png[16:24])
    return int(width), int(height)


@router.post("/api/documents/{document_id}/extract-regions")
async def document_extract_regions(request: Request, document_id: str, payload: RegionExtract) -> Any:
    """Lee las regiones que marcó la persona y agrega esos consumos."""
    context = ctx(request)
    result = await context.pipeline.extract_regions(document_id, payload.page, payload.regions)
    result["transactions"] = [
        tx for tx in result.get("transactions", []) if tx.get("statement_id") == document_id
    ]
    return ok(result)


@router.post("/api/documents/{document_id}/transactions")
async def document_add_transactions(
    request: Request, document_id: str, payload: DocumentTransactionsBody
) -> Any:
    """Agrega movimientos cargados a mano al documento."""
    context = ctx(request)
    items = [item.model_dump() for item in payload.transactions]
    rows = context.pipeline.add_transactions(document_id, items)
    return ok({"transactions": [tx for tx in rows if tx.get("statement_id") == document_id]})


@router.patch("/api/documents/{document_id}/fields")
async def document_patch_fields(request: Request, document_id: str, payload: FieldPatch) -> Any:
    context = ctx(request)
    return ok(context.pipeline.patch_fields(document_id, payload.fields))


@router.post("/api/documents/{document_id}/confirm")
async def document_confirm(request: Request, document_id: str) -> Any:
    context = ctx(request)
    return ok(context.pipeline.confirm(document_id))


# --- movimientos --------------------------------------------------------
@router.get("/api/transactions")
async def list_transactions(
    request: Request,
    month: str | None = None,
    cardId: str | None = None,
    kind: str | None = None,
) -> Any:
    context = ctx(request)
    return ok({"transactions": context.repo.list_transactions(period=month, card_id=cardId, kind=kind)})


@router.post("/api/transactions")
async def create_transaction(request: Request, payload: TransactionCreate) -> Any:
    from ..core.ids import new_id

    context = ctx(request)
    row = {
        "id": new_id("tx"),
        "statement_id": payload.statementId,
        "card_id": payload.cardId,
        "occurred_on": payload.occurredOn,
        "description": payload.description,
        "normalized_description": payload.description.lower(),
        "category": payload.category,
        "amount_cents": _money(payload.amountCents, payload.amount),
        "kind": payload.kind,
        "confirmed": payload.confirmed,
    }
    context.repo.insert_transactions([row])
    return ok({"transaction": context.repo.list_transactions()[:1]})


@router.delete("/api/transactions/{tx_id}")
async def delete_transaction(request: Request, tx_id: str) -> Any:
    context = ctx(request)
    if not context.repo.delete_transaction(tx_id):
        raise NotFoundError("Movimiento no encontrado")
    return ok({"deleted": True})


@router.patch("/api/transactions/{tx_id}")
async def patch_transaction(request: Request, tx_id: str, payload: TransactionPatch) -> Any:
    context = ctx(request)
    patch = {
        "category": payload.category,
        "description": payload.description,
        "kind": payload.kind,
        "confirmed": payload.confirmed,
        "occurred_on": payload.occurredOn,
        "currency": payload.currency,
    }
    if payload.amountCents is not None or payload.amount is not None:
        patch["amount_cents"] = _money(payload.amountCents, payload.amount)
    patch = {k: v for k, v in patch.items() if v is not None}
    tx = context.repo.update_transaction(tx_id, patch)
    if tx is None:
        raise NotFoundError("Movimiento no encontrado")
    return ok({"transaction": tx})


# --- calendario ---------------------------------------------------------
@router.get("/api/calendar")
async def calendar(
    request: Request,
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = None,
) -> Any:
    context = ctx(request)
    if from_ and to:
        start_date = date.fromisoformat(from_)
        end_date = date.fromisoformat(to)
    else:
        start_date, end_date = month_bounds(period_of(today()))
    events = context.engine.build_calendar(start_date, end_date)
    return ok({"from": start_date.isoformat(), "to": end_date.isoformat(), "events": events})


@router.get("/api/payments")
async def list_payments(request: Request, status: str | None = None) -> Any:
    context = ctx(request)
    return ok({"payments": context.repo.list_payments(status=status)})


@router.post("/api/payments/{payment_id}")
async def update_payment(request: Request, payment_id: str, payload: PaymentPatch) -> Any:
    context = ctx(request)
    if payload.status not in {"pending", "paid", "scheduled"}:
        raise ValidationError("Estado de pago inválido")
    context.repo.db.execute(
        "UPDATE payments SET status = ?, paid_at = ? WHERE id = ? AND user_id = ?",
        (payload.status, utcnow() if payload.status == "paid" else None, payment_id, context.repo.user_id),
    )
    context.engine.refresh_calendar()
    return ok({"payments": context.repo.list_payments()})


# --- copiloto -----------------------------------------------------------
@router.post("/api/copilot/chat")
async def copilot_chat(request: Request, payload: CopilotChat) -> Any:
    from ..core.ids import new_id

    context = ctx(request)
    if not payload.question.strip():
        raise ValidationError("La pregunta está vacía")
    copilot = context.copilot()
    answer = await asyncio.to_thread(copilot.answer, payload.question, payload.month)
    context.repo.add_copilot_message(new_id("msg"), "user", payload.question, [])
    context.repo.add_copilot_message(
        new_id("msg"), "assistant", answer.answer, [s.to_dict() for s in answer.sources]
    )
    return ok({"detectedIntents": detect_intents(payload.question), **answer.to_dict()})


@router.get("/api/copilot/history")
async def copilot_history(request: Request) -> Any:
    context = ctx(request)
    return ok({"messages": context.repo.list_copilot_messages()})


@router.delete("/api/copilot/history")
async def copilot_clear(request: Request) -> Any:
    context = ctx(request)
    context.repo.clear_copilot_messages()
    return ok({"cleared": True})


# --- export -------------------------------------------------------------
@router.get("/api/export/preview")
async def export_preview(request: Request, month: str | None = None) -> Any:
    from ..export.xlsx import preview

    context = ctx(request)
    period = month or period_of(today())
    return ok(preview(context.repo, context.engine, period))


@router.post("/api/export/xlsx")
async def export_xlsx(request: Request, payload: ExportRequest) -> Any:
    from ..export.xlsx import export_xlsx

    context = ctx(request)
    period = payload.month or period_of(today())
    destination = Path(payload.path) if payload.path else context.settings.data_dir / f"finanzar-{period}.xlsx"
    result = await asyncio.to_thread(export_xlsx, context.repo, context.engine, period, destination)
    context.repo.audit("export.xlsx", entity="export", entity_id=period, details={"path": str(destination)})
    return ok(result)


# --- actualizaciones ----------------------------------------------------
@router.get("/api/app/update-status")
async def update_status(request: Request) -> Any:
    context = ctx(request)
    last = context.repo.get_setting("update_last_status")
    payload: dict[str, Any] = {"currentVersion": __version__}
    if last:
        with contextlib.suppress(json.JSONDecodeError):
            payload.update(json.loads(last))
    return ok(payload)


@router.post("/api/app/update-check")
async def update_check(request: Request) -> Any:
    context = ctx(request)
    info = await asyncio.to_thread(context.update_checker.check)
    data = info.to_dict()
    context.repo.set_setting("update_last_status", json.dumps(data, ensure_ascii=False))
    context.repo.set_setting("update_checked_at", info.checked_at)
    return ok(data)


@router.post("/api/app/update-install")
async def update_install(request: Request) -> Any:
    context = ctx(request)
    context.repo.audit("update.install_requested", entity="updates")
    return ok(
        {
            "message": "La instalación la realiza el updater firmado de la app con tu confirmación explícita.",
            "requiresConsent": True,
            "currentVersion": __version__,
        }
    )


# --- configuración y eventos -------------------------------------------
@router.get("/api/settings")
async def get_settings_route(request: Request) -> Any:
    context = ctx(request)
    return ok({"settings": context.repo.all_settings()})


@router.patch("/api/settings")
async def patch_settings(request: Request, payload: SettingsPatch) -> Any:
    context = ctx(request)
    for key, value in payload.values.items():
        context.repo.set_setting(key, str(value))
    return ok({"settings": context.repo.all_settings()})


@router.get("/api/events")
async def events(request: Request) -> StreamingResponse:
    context = ctx(request)

    async def generator():
        yield "retry: 3000\n\n"
        async with context.bus.subscribe() as queue:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(generator(), media_type="text/event-stream")


@router.get("/api/jobs")
async def jobs(request: Request, kind: str | None = None) -> Any:
    context = ctx(request)
    return ok({"jobs": [job.to_dict() for job in context.bus.list_jobs(kind)]})


@router.post("/api/dev/seed")
async def dev_seed(request: Request) -> Any:
    """Carga datos demo. Deshabilitado salvo que FINANZAR_ALLOW_SEED=1."""
    import os

    if os.environ.get("FINANZAR_ALLOW_SEED") != "1":
        raise NotFoundError("El seed está deshabilitado")

    from ..core.seed import seed_demo

    context = ctx(request)
    return ok(seed_demo(context.repo, context.engine))
