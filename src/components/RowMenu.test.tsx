/** El menú de fila se dibuja en un portal: no lo recorta el contenedor. */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { RowMenu } from "./RowMenu";

describe("RowMenu", () => {
  it("abre el menú fuera del contenedor y ejecuta la acción", async () => {
    const onSelect = vi.fn();
    const { container } = render(
      <div style={{ overflow: "hidden", height: 40 }}>
        <RowMenu
          label="Acciones"
          actions={[
            { label: "Editar", icon: "pencil", onSelect },
            { label: "Borrar", icon: "trash", danger: true, onSelect: vi.fn() },
          ]}
        />
      </div>,
    );

    await userEvent.click(screen.getByRole("button", { name: "Acciones" }));
    const menu = screen.getByRole("menu");
    // El menú vive en el body, no dentro del contenedor con overflow.
    expect(container.contains(menu)).toBe(false);
    expect(document.body.contains(menu)).toBe(true);

    await userEvent.click(screen.getByRole("menuitem", { name: /Editar/ }));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("acepta la tecla Escape para cerrar", async () => {
    render(<RowMenu label="Acciones" actions={[{ label: "Editar", icon: "pencil", onSelect: vi.fn() }]} />);
    await userEvent.click(screen.getByRole("button", { name: "Acciones" }));
    expect(screen.getByRole("menu")).toBeTruthy();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).toBeNull();
  });
});