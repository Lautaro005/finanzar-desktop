/** Calendario: "Próximos eventos" no muestra lo que ya pasó. */

import { render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { CalendarScreen } from "./CalendarScreen";
import { AppProvider } from "../../app/context";

function iso(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

const today = new Date();
const past = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 4);
const future = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 4);

const events = [
  {
    id: "ev-past",
    event_date: iso(past),
    kind: "due",
    title: "Vencimiento viejo",
    amount_cents: 1000,
    currency: "ARS",
  },
  {
    id: "ev-future",
    event_date: iso(future),
    kind: "due",
    title: "Vencimiento próximo",
    amount_cents: 2000,
    currency: "ARS",
  },
];

vi.mock("../../lib/backend", () => ({
  api: {
    calendar: vi.fn(() => Promise.resolve({ events })),
  },
  ApiError: class ApiError extends Error {},
}));

function wrapper({ children }: { children: ReactNode }) {
  return <AppProvider>{children}</AppProvider>;
}

describe("CalendarScreen", () => {
  it("deja fuera del panel de próximos eventos los que ya pasaron", async () => {
    render(<CalendarScreen />, { wrapper });
    await waitFor(() => expect(screen.getByText("Próximos eventos")).toBeInTheDocument());

    const agenda = document.querySelector(".agenda-list");
    expect(agenda).not.toBeNull();
    const panel = within(agenda as HTMLElement);
    await waitFor(() => expect(panel.getByText("Vencimiento próximo")).toBeInTheDocument());
    expect(panel.queryByText("Vencimiento viejo")).toBeNull();
  });
});
