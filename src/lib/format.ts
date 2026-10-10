/** Formato de dinero, fechas y períodos (locale es-AR). */

const MONTHS = [
  "Enero",
  "Febrero",
  "Marzo",
  "Abril",
  "Mayo",
  "Junio",
  "Julio",
  "Agosto",
  "Septiembre",
  "Octubre",
  "Noviembre",
  "Diciembre",
];

export function formatCents(cents: number | null | undefined, currency = "ARS"): string {
  if (cents === null || cents === undefined) return "—";
  const negative = cents < 0;
  const value = Math.abs(cents);
  const integer = Math.floor(value / 100);
  const decimals = String(value % 100).padStart(2, "0");
  const grouped = integer.toLocaleString("es-AR");
  const prefix = currency.toUpperCase() === "USD" ? "US$" : "AR$";
  return `${negative ? "-" : ""}${prefix} ${grouped},${decimals}`;
}

export function formatCompact(cents: number | null | undefined, currency = "ARS"): string {
  if (cents === null || cents === undefined) return "—";
  const value = Math.abs(cents / 100);
  const sign = cents < 0 ? "-" : "";
  const prefix = currency.toUpperCase() === "USD" ? "US$" : "AR$";
  if (value >= 1_000_000) return `${sign}${prefix} ${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${sign}${prefix} ${Math.round(value / 1_000)}k`;
  return `${sign}${prefix} ${value.toFixed(0)}`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [year, month, day] = iso.slice(0, 10).split("-");
  if (!year || !month || !day) return iso;
  return `${day}/${month}/${year}`;
}

/** ISO (``2026-10-03``) a texto editable ``03/10/2026``. */
export function isoToDdmm(iso: string | null | undefined): string {
  if (!iso) return "";
  const [year, month, day] = iso.slice(0, 10).split("-");
  if (!year || !month || !day) return "";
  return `${day}/${month}/${year}`;
}

/** Texto ``03/10/2026`` (o ``3/10/26``) a ISO; ``null`` si no es una fecha válida. */
export function ddmmToIso(text: string): string | null {
  const parts = text.trim().split(/[/\-.]/).map((part) => part.trim());
  if (parts.length !== 3) return null;
  const day = Number(parts[0]);
  const month = Number(parts[1]);
  let year = Number(parts[2]);
  if (!Number.isInteger(day) || !Number.isInteger(month) || !Number.isInteger(year)) return null;
  if (year < 100) year += 2000;
  if (day < 1 || day > 31 || month < 1 || month > 12 || year < 1900 || year > 2200) return null;
  const candidate = new Date(Date.UTC(year, month - 1, day));
  if (candidate.getUTCDate() !== day || candidate.getUTCMonth() !== month - 1) return null;
  return `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

/** Máscara de tipeo para ``dd/mm/aaaa`` (solo dígitos y barras). */
export function maskDateInput(raw: string): string {
  const digits = raw.replace(/\D/g, "").slice(0, 8);
  if (digits.length <= 2) return digits;
  if (digits.length <= 4) return `${digits.slice(0, 2)}/${digits.slice(2)}`;
  return `${digits.slice(0, 2)}/${digits.slice(2, 4)}/${digits.slice(4)}`;
}

/** ISO de período (``2026-10``) a texto ``10/2026``. */
export function isoToMmYyyy(period: string | null | undefined): string {
  if (!period) return "";
  const [year, month] = period.split("-");
  if (!year || !month) return "";
  return `${month}/${year}`;
}

/** Texto ``10/2026`` (o ``10/26``) al período ISO ``2026-10``; ``null`` si no sirve. */
export function mmYyyyToPeriod(text: string): string | null {
  const parts = text.trim().split(/[/\-.]/).map((part) => part.trim());
  if (parts.length !== 2) return null;
  const month = Number(parts[0]);
  let year = Number(parts[1]);
  if (!Number.isInteger(month) || !Number.isInteger(year)) return null;
  if (year < 100) year += 2000;
  if (month < 1 || month > 12 || year < 1900 || year > 2200) return null;
  return `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}`;
}

/** Máscara de tipeo para ``mm/aaaa``. */
export function maskMonthInput(raw: string): string {
  const digits = raw.replace(/\D/g, "").slice(0, 6);
  if (digits.length <= 2) return digits;
  return `${digits.slice(0, 2)}/${digits.slice(2)}`;
}

export function formatDayMonth(iso: string | null | undefined): { day: string; month: string } {
  if (!iso) return { day: "--", month: "" };
  const parts = iso.slice(0, 10).split("-");
  const month = parts[1] ?? "";
  const day = parts[2] ?? "";
  const monthIndex = Number(month) - 1;
  return { day, month: (MONTHS[monthIndex] ?? "").slice(0, 3).toUpperCase() };
}

export function monthLabel(period: string): string {
  const [year, month] = period.split("-");
  const index = Number(month) - 1;
  return `${MONTHS[index] ?? month} ${year}`;
}

export function currentPeriod(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

export function percent(value: number): string {
  return `${Math.round(value)}%`;
}

export function currencyFromCents(cents: number): string {
  return cents === 0 ? "ARS" : "ARS";
}

export const MONTH_NAMES = MONTHS;
