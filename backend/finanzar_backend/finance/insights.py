"""Insights automáticos y explicables.

Cada insight conserva la consulta que lo originó y la evidencia (importes,
períodos, tarjetas, documentos). Nunca se inventan importes: todo sale de datos
confirmados en SQLite.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from ..core.ids import new_id
from .engine import FinanceEngine, add_months, month_bounds, period_of

MIN_DUPLICATE_CENTS = 100


def _previous_period(period: str) -> str:
    year, month = (int(part) for part in period.split("-"))
    return period_of(add_months(date(year, month, 1), -1))


def _sum_by_period(engine: FinanceEngine, period: str) -> dict[str, int]:
    rows = engine.repo.db.query(
        "SELECT category, COALESCE(SUM(amount_cents), 0) AS total FROM transactions "
        "WHERE user_id = ? AND substr(occurred_on, 1, 7) = ? "
        "AND kind IN ('purchase','installment','subscription','fee','tax') "
        "GROUP BY category",
        (engine.repo.user_id, period),
    )
    return {(row["category"] or "Sin categoría"): int(row["total"]) for row in rows}


def _biggest_change(
    current: dict[str, int], previous: dict[str, int]
) -> tuple[str, int, int] | None:
    """Categoría con la variación más grande en pesos respecto del mes anterior."""
    best: tuple[str, int, int] | None = None
    for category in set(current) | set(previous):
        delta = current.get(category, 0) - previous.get(category, 0)
        if best is None or abs(delta) > abs(best[2]):
            best = (category, previous.get(category, 0), delta)
    if best is None or best[2] == 0:
        return None
    return best


def _currency_totals(engine: FinanceEngine, period: str) -> dict[str, int]:
    rows = engine.repo.db.query(
        "SELECT COALESCE(currency, 'ARS') AS currency, COALESCE(SUM(amount_cents), 0) AS total, "
        "COUNT(*) AS count FROM transactions "
        "WHERE user_id = ? AND substr(occurred_on, 1, 7) = ? "
        "AND kind IN ('purchase','installment','subscription','fee','tax') "
        "GROUP BY currency",
        (engine.repo.user_id, period),
    )
    return {str(row["currency"]).upper(): int(row["total"]) for row in rows}


def find_duplicates(engine: FinanceEngine, period: str) -> list[dict[str, Any]]:
    start, end = month_bounds(period)
    rows = engine.repo.db.query(
        "SELECT id, description, amount_cents, occurred_on, card_id FROM transactions "
        "WHERE user_id = ? AND occurred_on >= ? AND occurred_on <= ? ORDER BY occurred_on",
        (engine.repo.user_id, start.isoformat(), end.isoformat()),
    )
    groups: dict[tuple[str, int], list[Any]] = {}
    for row in rows:
        if row["amount_cents"] < MIN_DUPLICATE_CENTS:
            continue
        key = (row["description"].strip().lower(), row["amount_cents"])
        groups.setdefault(key, []).append(row)
    duplicates = []
    for (description, amount), items in groups.items():
        if len(items) > 1:
            duplicates.append(
                {
                    "description": description,
                    "amountCents": amount,
                    "count": len(items),
                    "dates": [item["occurred_on"] for item in items],
                    "transactionIds": [item["id"] for item in items],
                }
            )
    return duplicates


def detect_subscriptions(engine: FinanceEngine, period: str) -> list[dict[str, Any]]:
    """Suscripciones repetidas: mismo texto e importe en dos períodos distintos."""
    current = _sum_by_period(engine, period)
    previous = _sum_by_period(engine, _previous_period(period))
    repeated = []
    for category, total in current.items():
        prev = previous.get(category)
        if prev and abs(prev - total) <= max(100, prev // 20):
            repeated.append({"category": category, "currentCents": total, "previousCents": prev})
    return repeated


def generate_insights(engine: FinanceEngine, period: str) -> list[dict[str, Any]]:
    insights: list[dict[str, Any]] = []
    current = _sum_by_period(engine, period)
    previous = _sum_by_period(engine, _previous_period(period))

    current_total = sum(current.values())
    previous_total = sum(previous.values())
    if previous_total > 0:
        delta = previous_total - current_total
        percent = round(abs(delta) / previous_total * 100, 1)
        change = _biggest_change(current, previous)
        # La señal nombra la categoría que explica la diferencia: sin eso es un
        # aviso genérico que no dice nada de los datos de la persona.
        detail = ""
        if change and change[2] != 0:
            category, _, category_delta = change
            direction = "más" if category_delta > 0 else "menos"
            detail = (
                f" La mayor diferencia está en {category}: "
                f"{abs(category_delta) / 100:,.2f} {direction}.".replace(",", ".")
            )
        if delta > 0:
            insights.append(
                {
                    "id": new_id("ins"),
                    "kind": "monthly_comparison",
                    "period": period,
                    "title": f"Gastaste {percent}% menos que el mes pasado",
                    "body": (
                        f"En {period} sumaste AR$ {current_total / 100:,.2f} y el mes anterior "
                        f"AR$ {previous_total / 100:,.2f}.{detail}"
                    ).replace(",", "."),
                    "severity": "good",
                    "query": "SELECT category, SUM(amount_cents) FROM transactions GROUP BY category",
                    "evidence": [
                        {"label": "Este mes", "amountCents": current_total},
                        {"label": "Mes anterior", "amountCents": previous_total},
                        {"label": "Diferencia", "amountCents": delta},
                    ],
                }
            )
        elif delta < 0:
            insights.append(
                {
                    "id": new_id("ins"),
                    "kind": "monthly_comparison",
                    "period": period,
                    "title": f"Gastaste {percent}% más que el mes pasado",
                    "body": (
                        f"En {period} sumaste AR$ {current_total / 100:,.2f} y el mes anterior "
                        f"AR$ {previous_total / 100:,.2f}.{detail}"
                    ).replace(",", "."),
                    "severity": "review",
                    "query": "SELECT category, SUM(amount_cents) FROM transactions GROUP BY category",
                    "evidence": [
                        {"label": "Este mes", "amountCents": current_total},
                        {"label": "Mes anterior", "amountCents": previous_total},
                    ],
                }
            )

    if current:
        top_category, top_total = max(current.items(), key=lambda item: item[1])
        insights.append(
            {
                "id": new_id("ins"),
                "kind": "top_category",
                "period": period,
                "title": f"Tu mayor gasto del mes fue {top_category}",
                "body": (
                    f"Sumó AR$ {top_total / 100:,.2f} sobre un total de AR$ {current_total / 100:,.2f} "
                    f"en consumos del resumen."
                ).replace(",", "."),
                "severity": "info",
                "query": "SELECT category, SUM(amount_cents) FROM transactions GROUP BY category LIMIT 1",
                "evidence": [
                    {"label": "Categoría", "text": top_category},
                    {"label": "Total de la categoría", "amountCents": top_total},
                    {"label": "Total del mes", "amountCents": current_total},
                ],
            }
        )

    currencies = _currency_totals(engine, period)
    if currencies.get("USD"):
        insights.append(
            {
                "id": new_id("ins"),
                "kind": "usd_spending",
                "period": period,
                "title": "Este mes tuviste consumos en dólares",
                "body": (
                    f"Consumiste US$ {currencies['USD'] / 100:,.2f}, además de "
                    f"AR$ {currencies.get('ARS', 0) / 100:,.2f} en pesos."
                ).replace(",", "."),
                "severity": "info",
                "query": "SELECT currency, SUM(amount_cents) FROM transactions GROUP BY currency",
                "evidence": [
                    {"label": "Dólares", "amountCents": currencies["USD"]},
                    {"label": "Pesos", "amountCents": currencies.get("ARS", 0)},
                ],
            }
        )

    for duplicate in find_duplicates(engine, period):
        insights.append(
            {
                "id": new_id("ins"),
                "kind": "duplicate",
                "period": period,
                "title": "Hay un consumo que se repite",
                "body": f"Detectamos {duplicate['count']} cargos similares de «{duplicate['description']}».",
                "severity": "review",
                "query": (
                    "SELECT description, amount_cents, COUNT(*) FROM transactions "
                    "GROUP BY 1, 2 HAVING COUNT(*) > 1"
                ),
                "evidence": [
                    {"label": "Descripción", "text": duplicate["description"]},
                    {"label": "Importe", "amountCents": duplicate["amountCents"]},
                    {"label": "Fechas", "text": ", ".join(duplicate["dates"])},
                ],
                "transactionIds": duplicate["transactionIds"],
            }
        )

    next_period = period_of(add_months(date(*map(int, period.split("-")), 1), 1))
    commitments = engine.commitments()
    if commitments["installmentsCents"]:
        insights.append(
            {
                "id": new_id("ins"),
                "kind": "projection",
                "period": next_period,
                "title": "Ya tenés comprometido para el mes que viene",
                "body": "Incluye cuotas activas, antes de sumar nuevos consumos.",
                "severity": "info",
                "query": "SELECT SUM(amount_cents) FROM installments WHERE remaining > 0",
                "evidence": [
                    {"label": "Cuotas activas", "amountCents": commitments["installmentsCents"]},
                    {"label": "Suscripciones", "amountCents": commitments["subscriptionsCents"]},
                ],
            }
        )

    alert = engine.low_balance_alert()
    if alert:
        insights.append(
            {
                "id": new_id("ins"),
                "kind": "low_balance",
                "period": period,
                "title": alert["title"],
                "body": alert["body"],
                "severity": "alert",
                "query": "projection(1).endBalance < threshold",
                "evidence": [
                    {"label": "Saldo proyectado", "amountCents": alert["projectedCents"]},
                    {"label": "Umbral", "amountCents": alert["thresholdCents"]},
                ],
            }
        )

    return insights


def refresh_insights(engine: FinanceEngine, period: str) -> int:
    return engine.repo.replace_insights(generate_insights(engine, period))
