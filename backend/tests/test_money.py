"""Tests de dinero exacto: nunca float, siempre centavos."""

from __future__ import annotations

import pytest

from finanzar_backend.core.money import (
    MoneyError,
    cents_to_str,
    format_ars,
    sum_cents,
    to_cents,
    to_decimal,
)


def test_to_cents_es_ar_format() -> None:
    assert to_cents("1.234,56") == 123456
    assert to_cents("218.450,00") == 21845000
    assert to_cents("9.990,90") == 999090


def test_to_cents_plain_and_integer() -> None:
    assert to_cents("1234.56") == 123456
    assert to_cents(500) == 50000
    assert to_cents("45") == 4500


def test_to_cents_rounds_half_up() -> None:
    assert to_cents("0.005") == 1
    assert to_cents("0.004") == 0


def test_rejects_float_money() -> None:
    with pytest.raises(MoneyError):
        to_cents(1234.56)  # type: ignore[arg-type]


def test_empty_is_error() -> None:
    with pytest.raises(MoneyError):
        to_cents("   ")


def test_decimal_and_str_roundtrip() -> None:
    assert cents_to_str(123456) == "1234.56"
    assert to_decimal("1234.56") == to_decimal(cents_to_str(123456))


def test_format_ars() -> None:
    assert format_ars(123456789) == "AR$ 1.234.567,89"
    assert format_ars(0) == "AR$ 0,00"
    assert format_ars(-50000) == "-AR$ 500,00"
    assert format_ars(100, "USD") == "US$ 1,00"


def test_sum_cents_is_exact() -> None:
    values = [to_cents("0.10"), to_cents("0.20"), to_cents("0.30")]
    assert sum_cents(values) == 60
    assert cents_to_str(sum_cents(values)) == "0.60"
