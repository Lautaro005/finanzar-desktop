import { describe, expect, it } from "vitest";

import { formatCents, formatCompact, formatDate, formatDayMonth, monthLabel, percent } from "./format";

describe("formatCents", () => {
  it("formatea pesos con dos decimales y separador de miles", () => {
    expect(formatCents(123456789)).toBe("AR$ 1.234.567,89");
    expect(formatCents(0)).toBe("AR$ 0,00");
    expect(formatCents(100)).toBe("AR$ 1,00");
  });

  it("muestra negativos y dólares", () => {
    expect(formatCents(-50000)).toBe("-AR$ 500,00");
    expect(formatCents(2900, "USD")).toBe("US$ 29,00");
  });

  it("devuelve guion para valores nulos", () => {
    expect(formatCents(null)).toBe("—");
    expect(formatCents(undefined)).toBe("—");
  });
});

describe("formatCompact", () => {
  it("abrevia miles y millones", () => {
    expect(formatCompact(95000000)).toBe("AR$ 950k");
    expect(formatCompact(200000000)).toBe("AR$ 2.0M");
  });
});

describe("fechas y períodos", () => {
  it("formatea ISO a dd/mm/yyyy", () => {
    expect(formatDate("2026-10-09")).toBe("09/10/2026");
    expect(formatDate(null)).toBe("—");
  });

  it("extrae día y mes abreviado", () => {
    expect(formatDayMonth("2026-10-10")).toEqual({ day: "10", month: "OCT" });
  });

  it("etiqueta el período en español", () => {
    expect(monthLabel("2026-10")).toBe("Octubre 2026");
  });

  it("formatea porcentajes", () => {
    expect(percent(21.4)).toBe("21%");
  });
});
