import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Dashboard } from "./Dashboard";
import { AppProvider } from "../../app/context";
import type { Dashboard as DashboardData } from "../../types/api";

const dashboardFixture: DashboardData = {
  period: "2026-10",
  balance: {
    totalCents: 132280000,
    byCurrency: { ARS: 132280000, USD: 1500 },
    accounts: [
      {
        id: "acc1",
        name: "Cuenta sueldo",
        kind: "bank",
        currency: "ARS",
        opening_balance_cents: 128000000,
        balance_cents: 128000000,
        institution: "Banco Galicia",
        masked_number: "**** 4821",
        close_day: null,
        due_day: null,
        archived: 0,
        notes: null,
      },
    ],
  },
  income: { monthCents: 95000000, recurring: [], nextCredit: { date: "2026-11-01", amount_cents: 95000000, name: "Sueldo" } },
  payments: { pendingCents: 58432000, pendingCount: 3, paidCents: 0 },
  upcomingPayments: [
    {
      id: "pay1",
      statement_id: "doc1",
      card_id: "card1",
      due_date: "2026-10-10",
      amount_cents: 21845000,
      currency: "ARS",
      kind: "total",
      status: "pending",
    },
  ],
  projection: {
    months: 1,
    cutoff: "2026-11-09",
    startBalanceCents: 132280000,
    futureIncomeCents: 0,
    futurePaymentsCents: 58432000,
    endBalanceCents: 73848000,
    assumptions: ["Saldo actual de cuentas activas", "Las cuotas y suscripciones no se descuentan dos veces: vienen dentro del resumen"],
    sources: [],
  },
  projections: {},
  commitments: { installmentsCents: 74210000, subscriptionsCents: 4890000, activeInstallments: 5, subscriptions: 3 },
  emergencyFund: {
    id: "goal1",
    name: "Fondo de emergencia",
    target_cents: 200000000,
    saved_cents: 42000000,
    currency: "ARS",
    salary_percent: 10,
    target_date: null,
    percent: 21,
    missingCents: 158000000,
  },
  lowBalanceAlert: null,
  documents: { total: 4, pending: 2, pendingList: [{ id: "doc2", filename: "mastercard.pdf", status: "review" }] },
  insights: [
    {
      id: "ins1",
      kind: "monthly_comparison",
      period: "2026-10",
      title: "Tus gastos fijos bajaron 6.2%",
      body: "El total de consumos del mes es menor que el del mes pasado.",
      severity: "good",
      query: "SELECT 1",
      evidence: [{ label: "Este mes", amountCents: 32961000 }],
    },
  ],
  calendar: [],
};

vi.mock("../../lib/backend", () => ({
  api: {
    dashboard: vi.fn(() => Promise.resolve(dashboardFixture)),
    setPaymentStatus: vi.fn(() => Promise.resolve({ payments: [] })),
  },
  ApiError: class ApiError extends Error {},
}));

function wrapper({ children }: { children: ReactNode }) {
  return <AppProvider>{children}</AppProvider>;
}

describe("Dashboard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("muestra el balance consolidado y el total a pagar", async () => {
    render(<Dashboard />, { wrapper });
    await waitFor(() => expect(screen.getAllByText("AR$ 1.322.800,00").length).toBeGreaterThan(0));
    expect(screen.getAllByText("AR$ 584.320,00").length).toBeGreaterThan(0);
    expect(screen.getByText("Cuenta sueldo")).toBeInTheDocument();
    expect(screen.getByText("Total disponible")).toBeInTheDocument();
  });

  it("muestra insights con evidencia y el fondo de emergencia", async () => {
    render(<Dashboard />, { wrapper });
    await waitFor(() => expect(screen.getByText("Tus gastos fijos bajaron 6.2%")).toBeInTheDocument());
    expect(screen.getByText("Ver evidencia")).toBeInTheDocument();
    expect(screen.getByText(/Te faltan/)).toBeInTheDocument();
  });

  it("expone los supuestos de la proyección", async () => {
    render(<Dashboard />, { wrapper });
    await waitFor(() =>
      expect(screen.getByText(/no se descuentan dos veces/)).toBeInTheDocument(),
    );
  });

  it("elige el período con un dropdown y no muestra el botón de la IA", async () => {
    render(<Dashboard />, { wrapper });
    await waitFor(() => expect(screen.getByRole("combobox", { name: "Período" })).toBeInTheDocument());
    // El encabezado ya no ofrece "Preguntarle a la IA": quedan los botones de acción.
    expect(screen.queryByText("Preguntarle a la IA")).toBeNull();
    expect(screen.getByRole("button", { name: /Agregar dinero/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Cargar resumen/ })).toBeInTheDocument();
  });

  it("muestra los dólares debajo de los pesos cuando hay saldo en USD", async () => {
    render(<Dashboard />, { wrapper });
    await waitFor(() =>
      expect(screen.getAllByText("US$ 15,00 en dólares").length).toBeGreaterThan(0),
    );
  });
});
