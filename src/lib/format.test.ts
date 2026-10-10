import { describe, expect, it } from "vitest";

import {
  ddmmToIso,
  formatCents,
  formatCompact,
  formatDate,
  formatDayMonth,
  isoToDdmm,
  isoToMmYyyy,
  maskDateInput,
  maskMonthInput,
  mmYyyyToPeriod,
  monthLabel,
  percent,
} from "./format";

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

  it("muestra y lee fechas como dd/mm/aaaa (formato argentino)", () => {
    expect(isoToDdmm("2026-10-03")).toBe("03/10/2026");
    expect(ddmmToIso("03/10/2026")).toBe("2026-10-03");
    expect(ddmmToIso("3/10/26")).toBe("2026-10-03");
    // Fechas imposibles no pasan.
    expect(ddmmToIso("31/02/2026")).toBeNull();
    expect(ddmmToIso("hola")).toBeNull();
  });

  it("enmascara el tipeo de la fecha con barras", () => {
    expect(maskDateInput("03102026")).toBe("03/10/2026");
    expect(maskDateInput("03")).toBe("03");
    expect(maskDateInput("0310")).toBe("03/10");
    // Ignora lo que no sean dígitos y corta en 8.
    expect(maskDateInput("03-10-2026xx")).toBe("03/10/2026");
  });

  it("muestra y lee períodos como mm/aaaa", () => {
    expect(isoToMmYyyy("2026-10")).toBe("10/2026");
    expect(mmYyyyToPeriod("10/2026")).toBe("2026-10");
    expect(mmYyyyToPeriod("10/26")).toBe("2026-10");
    expect(mmYyyyToPeriod("13/2026")).toBeNull();
    expect(maskMonthInput("102026")).toBe("10/2026");
  });
});
