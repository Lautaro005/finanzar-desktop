import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Select } from "./Select";

const OPTIONS = [
  { value: "a", label: "Alfa" },
  { value: "b", label: "Beta" },
  { value: "c", label: "Gamma" },
];

describe("Select", () => {
  it("muestra la opción elegida y no la lista hasta abrir", () => {
    render(<Select value="b" options={OPTIONS} onChange={() => undefined} ariaLabel="Elegir" />);
    expect(screen.getByRole("combobox", { name: "Elegir" })).toHaveTextContent("Beta");
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("abre la lista y notifica la opción elegida", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Select value="a" options={OPTIONS} onChange={onChange} ariaLabel="Elegir" />);

    await user.click(screen.getByRole("combobox", { name: "Elegir" }));
    expect(screen.getByRole("listbox")).toBeInTheDocument();

    await user.click(screen.getByRole("option", { name: "Gamma" }));
    expect(onChange).toHaveBeenCalledWith("c");
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("marca la opción activa con las flechas y confirma con Enter", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Select value="a" options={OPTIONS} onChange={onChange} ariaLabel="Elegir" />);

    const trigger = screen.getByRole("combobox", { name: "Elegir" });
    trigger.focus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("listbox")).toBeInTheDocument();

    await user.keyboard("{ArrowDown}{Enter}");
    expect(onChange).toHaveBeenCalledWith("b");
  });

  it("cierra con Escape sin elegir", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Select value="a" options={OPTIONS} onChange={onChange} ariaLabel="Elegir" />);

    await user.click(screen.getByRole("combobox", { name: "Elegir" }));
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(onChange).not.toHaveBeenCalled();
  });

  it("expone aria-expanded y aria-selected", async () => {
    const user = userEvent.setup();
    render(<Select value="b" options={OPTIONS} onChange={() => undefined} ariaLabel="Elegir" />);

    const trigger = screen.getByRole("combobox", { name: "Elegir" });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    await user.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("option", { name: /Beta/ })).toHaveAttribute("aria-selected", "true");
  });
});
