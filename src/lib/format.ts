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
