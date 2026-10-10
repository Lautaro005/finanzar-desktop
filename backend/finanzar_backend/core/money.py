"""Utilidades de dinero y precisión.

Regla dura del proyecto: **nunca** usar ``float`` para dinero. Los importes se
almacenan como enteros en centavos (``*_cents``) y se serializan como cadenas
decimales exactas cuando la API los expone.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENTS = Decimal("0.01")


class MoneyError(ValueError):
    """Importe inválido."""


def to_cents(value: str | int | Decimal) -> int:
    """Convierte un importe a centavos enteros.

    Acepta strings como ``"1234.56"``, ``"1.234,56"`` (formato es-AR) o enteros.
    Usa ``Decimal`` para evitar el error binario de ``float``.
    """
    decimal_value = to_decimal(value)
    cents = (decimal_value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(cents)


def to_decimal(value: str | int | Decimal) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):  # pragma: no cover - se evita a propósito
        raise MoneyError("No se aceptan floats para dinero; usá centavos o string decimal")
    text = str(value).strip().replace(" ", "").replace("AR$", "").replace("US$", "").strip()
    if not text:
        raise MoneyError("Importe vacío")
    # Formato es-AR: 1.234.567,89
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    elif text.count(".") > 1:
        text = text.replace(".", "")
    try:
        return Decimal(text)
    except InvalidOperation as exc:  # pragma: no cover - defensivo
        raise MoneyError(f"Importe inválido: {value!r}") from exc


def cents_to_decimal(cents: int) -> Decimal:
    return (Decimal(cents) / 100).quantize(CENTS)


def cents_to_str(cents: int) -> str:
    """Cadena decimal estable para JSON (nunca notación científica)."""
    return format(cents_to_decimal(cents), "f")


def format_ars(cents: int, currency: str = "ARS") -> str:
    """Formato humano ``AR$ 1.234.567,89`` (solo para presentación/texto)."""
    value = cents_to_decimal(cents)
    negative = value < 0
    if negative:
        value = -value
    integer, _, decimals = format(value, "f").partition(".")
    grouped = ""
    for index, char in enumerate(reversed(integer)):
        if index and index % 3 == 0:
            grouped = "." + grouped
        grouped = char + grouped
    prefix = "US$" if currency.upper() in {"USD", "US$"} else "AR$"
    sign = "-" if negative else ""
    return f"{sign}{prefix} {grouped},{decimals}"


def sum_cents(values: list[int]) -> int:
    return int(sum(values))
