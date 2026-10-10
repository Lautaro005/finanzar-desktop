/** Ingresos: sueldo recurrente (activar/pausar) e historial de ingresos. */

import { useState, type JSX } from "react";

import { Icon } from "../../components/Icon";
import { EmptyState, ErrorBlock, LoadingBlock, Panel } from "../../components/ui";
import { api } from "../../lib/backend";
import { formatCents, formatDate } from "../../lib/format";
import { useAsync } from "../../lib/hooks";
import { useApp } from "../../app/context";

export function Income(): JSX.Element {
  const { toast, refresh, refreshKey, openMoney } = useApp();
  const incomes = useAsync(() => api.incomes(), [refreshKey]);
  const [punctualAmount, setPunctualAmount] = useState("");
  const [punctualSource, setPunctualSource] = useState("");
  const [punctualDate, setPunctualDate] = useState(new Date().toISOString().slice(0, 10));
  const [saving, setSaving] = useState(false);

  const addPunctual = async (event: React.FormEvent) => {
    event.preventDefault();
    const parsed = Number(punctualAmount.replace(/\./g, "").replace(",", "."));
    if (!Number.isFinite(parsed) || parsed <= 0) {
      toast("Ingresá un importe válido.", "error");
      return;
    }
    setSaving(true);
    try {
      await api.createIncome({
        amountCents: Math.round(parsed * 100),
        source: punctualSource.trim() || "Ingreso",
        kind: "punctual",
        occurredOn: punctualDate,
      });
      toast("Ingreso puntual registrado.");
      setPunctualAmount("");
      setPunctualSource("");
      refresh();
    } catch (error) {
      toast(error instanceof Error ? error.message : "No se pudo registrar", "error");
    } finally {
      setSaving(false);
    }
  };

  const toggleRecurring = async (id: string, active: boolean) => {
    try {
      await api.patchRecurring(id, { active: !active });
      toast(active ? "Sueldo pausado." : "Sueldo activado.");
      refresh();
    } catch (error) {
      toast(error instanceof Error ? error.message : "No se pudo actualizar", "error");
    }
  };

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Ingresos y sueldo automático</p>
          <h1>Ingresos.</h1>
          <p className="heading-copy">El sueldo entra al balance sin cargarlo cada mes.</p>
        </div>
        <div className="heading-actions">
          <button type="button" className="secondary-button" onClick={() => openMoney("income")}>
            <Icon name="plus" /> Ingreso puntual
          </button>
          <button type="button" className="primary-button" onClick={() => openMoney("salary")}>
            <Icon name="repeat" /> Configurar sueldo
          </button>
        </div>
      </div>

      <div className="two-column">
        <Panel title="Ingresos recurrentes" subtitle="Sueldo, freelance, alquiler y bonos.">
          {incomes.loading && !incomes.data ? (
            <LoadingBlock />
          ) : incomes.error ? (
            <ErrorBlock message={incomes.error} onRetry={incomes.reload} />
          ) : !incomes.data || incomes.data.recurring.length === 0 ? (
            <EmptyState
              icon="repeat"
              title="Sin ingresos automáticos"
              body="Configurá tu sueldo para que se sume solo cada mes."
              action={
                <button type="button" className="secondary-button" onClick={() => openMoney("salary")}>
                  <Icon name="plus" /> Configurar sueldo
                </button>
              }
            />
          ) : (
            <div className="stack-list">
              {incomes.data.recurring.map((item) => (
                <div className="list-row" key={item.id}>
                  <span className="salary-avatar">$</span>
                  <div className="list-row-copy">
                    <strong>{item.name}</strong>
                    <small>
                      {formatCents(item.amount_cents)} · día {item.day_of_month} de cada mes
                    </small>
                  </div>
                  <button
                    type="button"
                    className={`toggle ${item.active ? "on" : ""}`}
                    aria-label={`${item.active ? "Pausar" : "Activar"} ${item.name}`}
                    onClick={() => toggleRecurring(item.id, Boolean(item.active))}
                  >
                    <i />
                  </button>
                </div>
              ))}
            </div>
          )}
        </Panel>

        <Panel title="Registrar un ingreso" subtitle="Puntual, bono o transferencia.">
          <form className="stack-form" onSubmit={addPunctual}>
            <label>
              <span>Importe</span>
              <input
                value={punctualAmount}
                onChange={(event) => setPunctualAmount(event.target.value)}
                inputMode="decimal"
                placeholder="0"
                required
              />
            </label>
            <label>
              <span>Origen</span>
              <input value={punctualSource} onChange={(event) => setPunctualSource(event.target.value)} placeholder="Freelance" />
            </label>
            <label>
              <span>Fecha</span>
              <input type="date" value={punctualDate} onChange={(event) => setPunctualDate(event.target.value)} />
            </label>
            <button type="submit" className="primary-button" disabled={saving}>
              <Icon name="check" /> {saving ? "Guardando…" : "Registrar ingreso"}
            </button>
          </form>
        </Panel>
      </div>

      <Panel title="Historial de ingresos" subtitle="Todo lo que entró, confirmado.">
        {incomes.data && incomes.data.entries.length > 0 ? (
          <div className="movement-table-wrap">
            <table className="movement-table">
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>Origen</th>
                  <th>Tipo</th>
                  <th className="align-right">Importe</th>
                </tr>
              </thead>
              <tbody>
                {incomes.data.entries.map((entry) => (
                  <tr key={entry.id}>
                    <td>{formatDate(entry.occurred_on)}</td>
                    <td className="movement-name">{entry.source}</td>
                    <td>{entry.kind}</td>
                    <td className="amount-cell">{formatCents(entry.amount_cents, entry.currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState icon="arrow-down" title="Sin ingresos registrados" />
        )}
      </Panel>
    </>
  );
}
