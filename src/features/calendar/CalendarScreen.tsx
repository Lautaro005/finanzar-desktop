/** Calendario financiero: vencimientos, cierres, cuotas e ingresos. */

import { useMemo, useState, type JSX } from "react";

import { Icon } from "../../components/Icon";
import { EmptyState, ErrorBlock, LoadingBlock, Panel } from "../../components/ui";
import { api } from "../../lib/backend";
import { MONTH_NAMES, formatCents, formatDate, monthLabel } from "../../lib/format";
import { useAsync } from "../../lib/hooks";

const WEEKDAYS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

const KIND_LABEL: Record<string, string> = {
  due: "Vencimiento",
  close: "Cierre de tarjeta",
  installment: "Cuota",
  subscription: "Suscripción",
  income: "Ingreso automático",
  goal: "Meta de ahorro",
};

/** El CSS del prototipo nombra las clases de evento por tipo visual. */
const KIND_CLASS: Record<string, string> = {
  due: "payment",
  close: "close",
  installment: "installment",
  subscription: "subscription",
  income: "income",
  goal: "goal",
};

function buildGrid(year: number, month: number): Array<{ date: Date; inMonth: boolean }> {
  const first = new Date(year, month, 1);
  const offset = (first.getDay() + 6) % 7;
  const days: Array<{ date: Date; inMonth: boolean }> = [];
  for (let index = 0; index < 42; index += 1) {
    const date = new Date(year, month, index - offset + 1);
    days.push({ date, inMonth: date.getMonth() === month });
  }
  return days;
}

function iso(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

export function CalendarScreen(): JSX.Element {
  const today = new Date();
  const [cursor, setCursor] = useState({ year: today.getFullYear(), month: today.getMonth() });

  const grid = useMemo(() => buildGrid(cursor.year, cursor.month), [cursor]);
  const from = iso(grid[0].date);
  const to = iso(grid[grid.length - 1].date);

  const calendar = useAsync(() => api.calendar(from, to), [from, to]);

  const eventsByDate = useMemo(() => {
    const map = new Map<string, typeof events>();
    const events = calendar.data?.events ?? [];
    for (const event of events) {
      const key = event.event_date.slice(0, 10);
      map.set(key, [...(map.get(key) ?? []), event]);
    }
    return map;
  }, [calendar.data]);

  const agenda = (calendar.data?.events ?? [])
    .slice()
    .sort((a, b) => a.event_date.localeCompare(b.event_date));

  const shift = (delta: number) => {
    const next = new Date(cursor.year, cursor.month + delta, 1);
    setCursor({ year: next.getFullYear(), month: next.getMonth() });
  };

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Tu agenda financiera</p>
          <h1>Calendario.</h1>
          <p className="heading-copy">Vencimientos, cierres y cuotas en una sola vista.</p>
        </div>
        <button
          type="button"
          className="secondary-button"
          onClick={() => setCursor({ year: today.getFullYear(), month: today.getMonth() })}
        >
          <Icon name="target" /> Volver a hoy
        </button>
      </div>

      <div className="calendar-layout">
        <Panel className="calendar-main">
          <div className="calendar-toolbar">
            <button type="button" className="round-button" aria-label="Mes anterior" onClick={() => shift(-1)}>
              <Icon name="chevron-left" />
            </button>
            <div>
              <h2>
                {monthLabel(`${cursor.year}-${String(cursor.month + 1).padStart(2, "0")}`)}
              </h2>
              <span>{agenda.length} eventos</span>
            </div>
            <button type="button" className="round-button" aria-label="Mes siguiente" onClick={() => shift(1)}>
              <Icon name="chevron-right" />
            </button>
          </div>
          <div className="calendar-weekdays">
            {WEEKDAYS.map((day) => (
              <span key={day}>{day}</span>
            ))}
          </div>
          <div className="calendar-grid">
            {grid.map(({ date, inMonth }) => {
              const key = iso(date);
              const events = eventsByDate.get(key) ?? [];
              const isToday = key === iso(today);
              return (
                <div key={key} className={`calendar-day ${inMonth ? "" : "muted-day"} ${isToday ? "today" : ""}`}>
                  <span className="day-number">{date.getDate()}</span>
                  {events.slice(0, 3).map((event) => (
                    <span
                      key={event.id}
                      className={`calendar-event ${KIND_CLASS[event.kind] ?? "payment"}`}
                      title={`${KIND_LABEL[event.kind] ?? event.kind}: ${event.title}`}
                    >
                      {event.title}
                    </span>
                  ))}
                </div>
              );
            })}
          </div>
        </Panel>

        <Panel title="Próximos eventos" subtitle="Ordenados por fecha." className="agenda-panel">
          {calendar.loading && !calendar.data ? (
            <LoadingBlock />
          ) : calendar.error ? (
            <ErrorBlock message={calendar.error} onRetry={calendar.reload} />
          ) : agenda.length === 0 ? (
            <EmptyState icon="calendar" title="Sin eventos este mes" body="Cargá ingresos y resúmenes confirmados para verlos." />
          ) : (
            <div className="agenda-list">
              {agenda.map((event) => (
                <div key={event.id} className={`agenda-item ${KIND_CLASS[event.kind] ?? "payment"}`}>
                  <div className="agenda-date">
                    <strong>{event.event_date.slice(-2)}</strong>
                    <span>{MONTH_NAMES[Number(event.event_date.slice(5, 7)) - 1]?.slice(0, 3).toUpperCase()}</span>
                  </div>
                  <div>
                    <strong>{event.title}</strong>
                    <span>
                      {KIND_LABEL[event.kind] ?? event.kind}
                      {event.amount_cents ? ` · ${formatCents(event.amount_cents, event.currency ?? "ARS")}` : ""}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
          <div className="calendar-legend">
            <span>
              <i className="dot payment" /> Vencimiento
            </span>
            <span>
              <i className="dot close" /> Cierre
            </span>
            <span>
              <i className="dot installment" /> Cuota
            </span>
            <span>
              <i className="dot income" /> Ingreso
            </span>
          </div>
        </Panel>
      </div>
      <p className="calendar-footnote">Hoy es {formatDate(iso(today))}.</p>
    </>
  );
}
