/** Campos de fecha y período propios, en formato argentino (día/mes/año).

Los `<input type="date">` y `<input type="month">` nativos se dibujan con el
formato del sistema: en un equipo configurado en inglés muestran `mm/dd/aaaa`.
Estos campos muestran siempre `dd/mm/aaaa` (y `mm/aaaa`), como el resto de la
interfaz.
 */

import { useEffect, useState, type JSX } from "react";

import {
  ddmmToIso,
  isoToDdmm,
  isoToMmYyyy,
  maskDateInput,
  maskMonthInput,
  mmYyyyToPeriod,
} from "../lib/format";

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

export function MonthInput({
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
  const [text, setText] = useState(() => isoToMmYyyy(value));

  useEffect(() => {
    setText(isoToMmYyyy(value));
  }, [value]);

  return (
    <input
      type="text"
      className={className}
      value={text}
      placeholder="mm/aaaa"
      aria-label={ariaLabel ?? "Período (mes/año)"}
      inputMode="numeric"
      autoComplete="off"
      onChange={(event) => {
        const masked = maskMonthInput(event.target.value);
        setText(masked);
        const period = mmYyyyToPeriod(masked);
        if (period) onChange(period);
      }}
      onBlur={() => setText(isoToMmYyyy(value))}
    />
  );
}
