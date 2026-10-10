/** Menú de tres puntos por fila (editar / borrar).

El menú se dibuja en un portal con posición fija calculada desde el botón: si se
renderizara dentro de la fila, el contenedor con scroll lo recortaría y habría
que scrollear para ver las opciones.
 */

import { useEffect, useLayoutEffect, useRef, useState, type JSX } from "react";
import { createPortal } from "react-dom";

import { Icon } from "./Icon";

export interface RowMenuAction {
  label: string;
  icon: "pencil" | "trash" | "eye";
  onSelect: () => void;
  danger?: boolean;
}

export function RowMenu({
  label,
  actions,
}: {
  label: string;
  actions: RowMenuAction[];
}): JSX.Element {
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState<{ top: number; right: number } | null>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  useLayoutEffect(() => {
    if (!open || !buttonRef.current) return;
    const box = buttonRef.current.getBoundingClientRect();
    setCoords({ top: box.bottom + 6, right: Math.max(8, window.innerWidth - box.right) });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        className="icon-button"
        aria-label={label}
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={(event) => {
          // La fila que lo contiene puede tener su propio onClick (seleccionar).
          event.stopPropagation();
          setOpen((current) => !current);
        }}
      >
        <Icon name="more" />
      </button>
      {open &&
        coords &&
        createPortal(
          <>
            <div className="row-menu-backdrop" role="presentation" onClick={() => setOpen(false)} />
            <div className="row-menu-list" role="menu" style={{ top: coords.top, right: coords.right }}>
              {actions.map((action) => (
                <button
                  key={action.label}
                  type="button"
                  role="menuitem"
                  className={action.danger ? "row-menu-danger" : undefined}
                  onClick={(event) => {
                    event.stopPropagation();
                    setOpen(false);
                    action.onSelect();
                  }}
                >
                  <Icon name={action.icon} /> {action.label}
                </button>
              ))}
            </div>
          </>,
          document.body,
        )}
    </>
  );
}
