/** Campos de fecha y período propios, en formato argentino (día/mes/año).

Los `<input type="date">` y `<input type="month">` nativos se dibujan con el
formato del sistema: en un equipo configurado en inglés muestran `mm/dd/aaaa`.
Estos campos muestran siempre `dd/mm/aaaa` (y `mm/aaaa`), como el resto de la
interfaz.
 */

import { useEffect, useMemo, useState, type JSX } from "react";

import { ddmmToIso, isoToDdmm, maskDateInput, monthLabel } from "../lib/format";
import { Select } from "./Select";

export function DateInput({
  value,
  onChange,
  name,
  className,
  ariaLabel,
  required,
}: {
  value: string | null | undefined;
  onChange: (iso: string) => void;
  name?: string;
  className?: string;
  ariaLabel?: string;
  required?: boolean;
}): JSX.Element {
  const [text, setText] = useState(() => isoToDdmm(value));

  useEffect(() => {
    setText(isoToDdmm(value));
  }, [value]);

  return (
    <input
      type="text"
      name={name}
      className={className}
      value={text}
      placeholder="dd/mm/aaaa"
      aria-label={ariaLabel ?? "Fecha (día/mes/año)"}
      inputMode="numeric"
      autoComplete="off"
      required={required}
      onChange={(event) => {
        const masked = maskDateInput(event.target.value);
        setText(masked);
        const iso = ddmmToIso(masked);
        if (iso) onChange(iso);
      }}
      onBlur={() => setText(isoToDdmm(value))}
    />
  );
}

/** Cantidad de años hacia atrás y hacia adelante que ofrece el selector. */
const MONTH_RANGE_BACK = 3;
const MONTH_RANGE_FORWARD = 2;

/**
 * Selector de período con lista desplegable.
 *
 * El campo de texto obligaba a tipear números; acá se elige el mes y el año de
 * una lista (Enero 2024 … Diciembre 2028), incluido siempre el período activo.
 */
export function MonthSelect({
  value,
  onChange,
  className,
  ariaLabel,
}: {
  value: string;
  onChange: (period: string) => void;
  className?: string;
  ariaLabel?: string;
}): JSX.Element {
  const options = useMemo(() => {
    const [year, month] = value.split("-").map(Number);
    const anchor = Number.isFinite(year) && Number.isFinite(month) ? { year, month } : null;
    const today = new Date();
    const start = anchor ? anchor : { year: today.getFullYear(), month: today.getMonth() + 1 };
    const list: Array<{ value: string; label: string }> = [];
    const add = (offset: number) => {
      const date = new Date(Date.UTC(start.year, start.month - 1 + offset, 1));
      const period = `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}`;
      list.push({ value: period, label: monthLabel(period) });
    };
    for (let offset = -MONTH_RANGE_BACK * 12; offset <= MONTH_RANGE_FORWARD * 12; offset += 1) {
      add(offset);
    }
    if (!value) list.push({ value, label: monthLabel(value) });
    const unique = new Map(list.map((option) => [option.value, option]));
    if (!unique.has(value)) {
      unique.set(value, { value, label: monthLabel(value) });
    }
    return [...unique.values()].sort((a, b) => a.value.localeCompare(b.value));
  }, [value]);

  return (
    <Select
      value={value}
      options={options}
      onChange={onChange}
      ariaLabel={ariaLabel ?? "Período (mes y año)"}
      className={className ?? "month-select"}
    />
  );
}
