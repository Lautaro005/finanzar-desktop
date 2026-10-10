/** Componentes de UI reutilizables (paneles, estados, progreso, toasts). */

import type { JSX, ReactNode } from "react";
import { Icon } from "./Icon";

export function Panel({
  title,
  subtitle,
  action,
  children,
  className,
}: {
  title?: string;
  subtitle?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}): JSX.Element {
  return (
    <section className={`panel ${className ?? ""}`}>
      {(title || action) && (
        <div className="panel-heading">
          <div>
            {title && <h2>{title}</h2>}
            {subtitle && <p>{subtitle}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function ProgressBar({ value, label }: { value: number; label?: string }): JSX.Element {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div className="progress-track" role="progressbar" aria-valuenow={Math.round(clamped)} aria-valuemin={0} aria-valuemax={100} aria-label={label ?? "Progreso"}>
      <i style={{ width: `${clamped}%` }} />
    </div>
  );
}

export type LoadState = "idle" | "loading" | "ready" | "error";

export function LoadingBlock({ message = "Cargando…" }: { message?: string }): JSX.Element {
  return (
    <div className="state-block" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span>{message}</span>
    </div>
  );
}

export function ErrorBlock({ message, onRetry }: { message: string; onRetry?: () => void }): JSX.Element {
  return (
    <div className="state-block error" role="alert">
      <Icon name="alert" className="state-icon" />
      <div>
        <strong>No pudimos completar la operación</strong>
        <p>{message}</p>
      </div>
      {onRetry && (
        <button type="button" className="secondary-button" onClick={onRetry}>
          <Icon name="refresh" /> Reintentar
        </button>
      )}
    </div>
  );
}

export function EmptyState({
  icon = "info",
  title,
  body,
  action,
}: {
  icon?: string;
  title: string;
  body?: string;
  action?: ReactNode;
}): JSX.Element {
  return (
    <div className="state-block empty">
      <Icon name={icon} className="state-icon" />
      <div>
        <strong>{title}</strong>
        {body && <p>{body}</p>}
      </div>
      {action}
    </div>
  );
}

export function StatusPill({ status }: { status: string }): JSX.Element {
  const map: Record<string, { label: string; className: string }> = {
    imported: { label: "Importado", className: "review" },
    ocr: { label: "OCR en curso", className: "review" },
    extracted: { label: "Extraído", className: "review" },
    review: { label: "Revisar", className: "review" },
    confirmed: { label: "Confirmado", className: "confirmed" },
    error: { label: "Error", className: "error" },
    paid: { label: "Pagado", className: "confirmed" },
    pending: { label: "Pendiente", className: "review" },
    scheduled: { label: "Programado", className: "review" },
  };
  const entry = map[status] ?? { label: status, className: "" };
  return <span className={`document-status ${entry.className}`}>{entry.label}</span>;
}

export interface ToastMessage {
  id: number;
  text: string;
  tone?: "info" | "error";
}

export function ToastStack({ messages, onDismiss }: { messages: ToastMessage[]; onDismiss: (id: number) => void }): JSX.Element {
  return (
    <div className="toast-stack" aria-live="polite">
      {messages.map((message) => (
        <div key={message.id} className={`toast show ${message.tone === "error" ? "toast-error" : ""}`} role="status">
          <span className="toast-icon">
            <Icon name={message.tone === "error" ? "alert" : "check"} />
          </span>
          <span>{message.text}</span>
          <button type="button" className="toast-close" aria-label="Cerrar aviso" onClick={() => onDismiss(message.id)}>
            <Icon name="close" />
          </button>
        </div>
      ))}
    </div>
  );
}

export function Modal({
  title,
  eyebrow,
  onClose,
  children,
  footer,
  size,
}: {
  title: string;
  eyebrow?: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  size?: "money" | "review";
}): JSX.Element {
  return (
    <div className="modal-backdrop open" role="presentation" onClick={(event) => event.target === event.currentTarget && onClose()}>
      <div className={`${size === "money" ? "money-modal" : "review-modal"}`} role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-header">
          <div>
            {eyebrow && <span className="eyebrow">{eyebrow}</span>}
            <h2>{title}</h2>
          </div>
          <button type="button" className="icon-button" aria-label="Cerrar" onClick={onClose}>
            <Icon name="close" />
          </button>
        </div>
        {children}
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  );
}
