/** Perfil: nombre, tarjetas y categorías que se guardan en app_settings. */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Profile } from "./Profile";
import { AppProvider } from "../../app/context";

const patchSettings = vi.fn((values: Record<string, string>) =>
  Promise.resolve({ settings: values }),
);

vi.mock("../../lib/backend", () => ({
  api: {
    settings: vi.fn(() =>
      Promise.resolve({ settings: { user_name: "Lautaro", user_categories: '["Alimentación"]' } }),
    ),
    patchSettings: (values: Record<string, string>) => patchSettings(values),
    bootstrap: vi.fn(() => Promise.resolve({ settings: {} })),
  },
  ApiError: class ApiError extends Error {},
}));

function wrapper({ children }: { children: ReactNode }) {
  return <AppProvider>{children}</AppProvider>;
}

describe("Profile", () => {
  beforeEach(() => {
    patchSettings.mockClear();
  });

  it("guarda el nombre, las tarjetas y las categorías", async () => {
    render(<Profile />, { wrapper });
    await waitFor(() => expect(screen.getByDisplayValue("Lautaro")).toBeInTheDocument());

    await userEvent.type(screen.getByLabelText("Agregar categoría"), "Mascotas");
    // El primer "Agregar" es el de tarjetas; el segundo, el de categorías.
    await userEvent.click(screen.getAllByRole("button", { name: /Agregar/ })[1]);
    expect(screen.getByText("Mascotas")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /Guardar perfil/ }));
    await waitFor(() => expect(patchSettings).toHaveBeenCalled());
    const values = patchSettings.mock.calls[0][0];
    expect(values.user_name).toBe("Lautaro");
    expect(JSON.parse(values.user_categories)).toContain("Mascotas");
    expect(JSON.parse(values.user_brands)).toContain("American Express");
  });
});
