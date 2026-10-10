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

  it("expone data-icon para que el CSS del prototipo lo dimensione y coloree", () => {
    const { container } = render(<Icon name="wallet" />);
    expect(container.querySelector("svg")?.getAttribute("data-icon")).toBe("wallet");
  });

  it("usa stroke currentColor y fill none (evita íconos negros)", () => {
    const { container } = render(<Icon name="check" />);
    const svg = container.querySelector("svg");
    expect(svg?.getAttribute("stroke")).toBe("currentColor");
    expect(svg?.getAttribute("fill")).toBe("none");
  });

  it("respeta un tamaño explícito cuando se pasa size", () => {
    const { container } = render(<Icon name="info" size={22} />);
    const svg = container.querySelector("svg") as SVGSVGElement;
    expect(svg.style.width).toBe("22px");
    expect(svg.style.height).toBe("22px");
  });
});
