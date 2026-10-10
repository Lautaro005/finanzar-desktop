/** Dropdown propio de la app (reemplaza al `<select>` nativo).

Soporta teclado (Enter/Espacio/↑/↓/Inicio/Fin/Escape), cierre al hacer clic
afuera y roles ARIA de listbox.
*/

import { useEffect, useRef, useState, type JSX } from "react";

import { Icon } from "./Icon";

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectProps {
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  ariaLabel?: string;
  placeholder?: string;
  className?: string;
}

export function Select({ value, options, onChange, ariaLabel, placeholder, className }: SelectProps): JSX.Element {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  const selectedIndex = options.findIndex((option) => option.value === value);
  const current = selectedIndex >= 0 ? options[selectedIndex] : undefined;

  useEffect(() => {
    if (!open) return;
    const onDocumentClick = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDocumentClick);
    return () => document.removeEventListener("mousedown", onDocumentClick);
  }, [open]);

  const openList = () => {
    setActive(selectedIndex >= 0 ? selectedIndex : 0);
    setOpen(true);
  };

  const commit = (index: number) => {
    const option = options[index];
    if (option) onChange(option.value);
    setOpen(false);
    triggerRef.current?.focus();
  };

  const onTriggerKeyDown = (event: React.KeyboardEvent) => {
    switch (event.key) {
      case "Escape":
        setOpen(false);
        return;
      case "ArrowDown":
      case "ArrowUp":
      case "Enter":
      case " ":
        event.preventDefault();
        if (!open) {
          openList();
        } else if (event.key === "Enter" || event.key === " ") {
          commit(active);
        } else {
          setActive((index) => Math.min(options.length - 1, Math.max(0, index + (event.key === "ArrowDown" ? 1 : -1))));
        }
        return;
      case "Home":
        if (open) {
          event.preventDefault();
          setActive(0);
        }
        return;
      case "End":
        if (open) {
          event.preventDefault();
          setActive(options.length - 1);
        }
        return;
      case "Tab":
        setOpen(false);
        return;
      default:
        return;
    }
  };

  return (
    <div ref={rootRef} className={`app-select ${open ? "open" : ""} ${className ?? ""}`}>
      <button
        ref={triggerRef}
        type="button"
        className="app-select-trigger"
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        onClick={() => (open ? setOpen(false) : openList())}
        onKeyDown={onTriggerKeyDown}
      >
        <span className="app-select-value">{current?.label ?? placeholder ?? "Elegí una opción"}</span>
        <span className="app-select-caret" aria-hidden="true">
          <Icon name={open ? "chevron-up" : "chevron-down"} />
        </span>
      </button>

      {open && (
        <ul className="app-select-list" role="listbox" aria-label={ariaLabel} tabIndex={-1}>
          {options.map((option, index) => (
            <li
              key={option.value}
              role="option"
              aria-selected={option.value === value}
              className={`app-select-option ${index === active ? "active" : ""} ${option.value === value ? "selected" : ""}`}
              onMouseEnter={() => setActive(index)}
              onMouseDown={(event) => {
                event.preventDefault();
                commit(index);
              }}
            >
              <span>{option.label}</span>
              {option.value === value && <Icon name="check" />}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
