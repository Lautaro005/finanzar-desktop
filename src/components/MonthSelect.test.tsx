/** Selector de período: es una lista desplegable, no un campo para tipear. */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { MonthSelect } from "./DateField";

describe("MonthSelect", () => {
  it("ofrece los meses y años en una lista y devuelve el período elegido", async () => {
    const onChange = vi.fn();
    render(<MonthSelect value="2026-10" onChange={onChange} ariaLabel="Período" />);

    await userEvent.click(screen.getByRole("combobox", { name: "Período" }));
    expect(screen.getByRole("listbox")).toBeTruthy();
    expect(screen.getByRole("option", { name: /Octubre 2026/ })).toBeTruthy();

    await userEvent.click(screen.getByRole("option", { name: /Noviembre 2026/ }));
    expect(onChange).toHaveBeenCalledWith("2026-11");
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("no es un campo de texto editable", () => {
    render(<MonthSelect value="2026-10" onChange={vi.fn()} ariaLabel="Período" />);
    expect(screen.queryByRole("textbox")).toBeNull();
  });
});
