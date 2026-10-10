import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Icon } from "./Icon";

describe("Icon", () => {
  it("renderiza un SVG para un ícono conocido", () => {
    const { container } = render(<Icon name="wallet" />);
    expect(container.querySelector("svg")).toBeInTheDocument();
  });

  it("devuelve null para un ícono desconocido", () => {
    const { container } = render(<Icon name="no-existe" />);
    expect(container.querySelector("svg")).toBeNull();
  });

  it("el SVG es decorativo (aria-hidden)", () => {
    const { container } = render(<Icon name="check" />);
    expect(container.querySelector("svg")?.getAttribute("aria-hidden")).toBe("true");
  });

  it("mantiene el conjunto de íconos del prototipo", () => {
    const { container } = render(
      <div>
        <Icon name="grid" />
        <Icon name="file" />
        <Icon name="calendar" />
        <Icon name="receipt" />
        <Icon name="sliders" />
        <Icon name="spark" />
      </div>,
    );
    expect(container.querySelectorAll("svg")).toHaveLength(6);
    expect(screen.queryByText("algo")).toBeNull();
  });
});
