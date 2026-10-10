/** Ingresos: sueldo recurrente (activar/pausar) e historial de ingresos. */

import { useState, type JSX } from "react";

import { Icon } from "../../components/Icon";
import { DateInput } from "../../components/DateField";
import { RowMenu } from "../../components/RowMenu";
import { EmptyState, ErrorBlock, LoadingBlock, Modal, Panel } from "../../components/ui";
import { api } from "../../lib/backend";
import { formatCents, formatDate } from "../../lib/format";
import { useAsync } from "../../lib/hooks";
import { useApp } from "../../app/context";
import type { IncomeEntry } from "../../types/api";

export function Income(): JSX.Element {
  const { toast, refresh, refreshKey, openMoney } = useApp();
  const incomes = useAsync(() => api.incomes(), [refreshKey]);
  const [punctualAmount, setPunctualAmount] = useState("");
  const [punctualSource, setPunctualSource] = useState("");
  const [punctualDate, setPunctualDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState<IncomeEntry | null>(null);
  const [deleting, setDeleting] = useState<IncomeEntry | null>(null);

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

  const removeIncome = async (entry: IncomeEntry) => {
    try {
      await api.deleteIncome(entry.id);
      toast("Ingreso borrado.");
      setDeleting(null);
      refresh();
    } catch (error) {
      toast(error instanceof Error ? error.message : "No se pudo borrar", "error");
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
              <DateInput value={punctualDate} onChange={setPunctualDate} />
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
                  <th className="align-right">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {incomes.data.entries.map((entry) => (
                  <tr key={entry.id}>
                    <td>{formatDate(entry.occurred_on)}</td>
                    <td className="movement-name">{entry.source}</td>
                    <td>{entry.kind}</td>
                    <td className="amount-cell">{formatCents(entry.amount_cents, entry.currency)}</td>
                    <td className="align-right">
                      <RowMenu
                        label={`Acciones para ${entry.source}`}
                        actions={[
                          { label: "Editar", icon: "pencil", onSelect: () => setEditing(entry) },
                          { label: "Borrar", icon: "trash", danger: true, onSelect: () => setDeleting(entry) },
                        ]}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState icon="arrow-down" title="Sin ingresos registrados" />
        )}
      </Panel>

      {editing && (
        <EditIncomeModal
          entry={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            toast("Ingreso actualizado.");
            setEditing(null);
            refresh();
          }}
          onError={(message) => toast(message, "error")}
        />
      )}

      {deleting && (
        <Modal
          title="Borrar ingreso"
          eyebrow="Historial de ingresos"
          size="compact"
          onClose={() => setDeleting(null)}
          footer={
            <>
              <button type="button" className="secondary-button" onClick={() => setDeleting(null)}>
                Cancelar
              </button>
              <button type="button" className="danger-button" onClick={() => void removeIncome(deleting)}>
                <Icon name="trash" /> Borrar
              </button>
            </>
          }
        >
          <div className="confirm-body">
            <p className="confirm-copy">
              ¿Borrar <strong>{deleting.source}</strong> por {formatCents(deleting.amount_cents, deleting.currency)}{" "}
              del {formatDate(deleting.occurred_on)}?
            </p>
            {deleting.recurring_income_id && (
              <p className="confirm-note">
                Viene del sueldo automático: se anula para que no vuelva a aparecer.
              </p>
            )}
          </div>
        </Modal>
      )}
    </>
  );
}

function EditIncomeModal({
  entry,
  onClose,
  onSaved,
  onError,
}: {
  entry: IncomeEntry;
  onClose: () => void;
  onSaved: () => void;
  onError: (message: string) => void;
}): JSX.Element {
  const [amount, setAmount] = useState(() =>
    (entry.amount_cents / 100).toFixed(2).replace(".", ","),
  );
  const [source, setSource] = useState(entry.source);
  const [occurredOn, setOccurredOn] = useState(entry.occurred_on.slice(0, 10));
  const [saving, setSaving] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    const parsed = Number(amount.replace(/\./g, "").replace(",", "."));
    if (!Number.isFinite(parsed) || parsed <= 0) {
      onError("Ingresá un importe válido.");
      return;
    }
    setSaving(true);
    try {
      await api.patchIncome(entry.id, {
        amountCents: Math.round(parsed * 100),
        source: source.trim() || entry.source,
        occurredOn,
      });
      onSaved();
    } catch (error) {
      onError(error instanceof Error ? error.message : "No se pudo guardar");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title="Editar ingreso"
      eyebrow="Historial de ingresos"
      onClose={onClose}
      size="money"
      footer={
        <>
          <button type="button" className="secondary-button" onClick={onClose}>
            Cancelar
          </button>
          <button type="submit" form="edit-income-form" className="primary-button" disabled={saving}>
            <Icon name="check" /> {saving ? "Guardando…" : "Guardar"}
          </button>
        </>
      }
    >
      <form id="edit-income-form" className="money-form-grid" onSubmit={submit}>
        <label>
          <span>Importe</span>
          <input
            type="text"
            inputMode="decimal"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
            required
          />
        </label>
        <label>
          <span>Origen</span>
          <input type="text" value={source} onChange={(event) => setSource(event.target.value)} />
        </label>
        <label>
          <span>Fecha</span>
          <DateInput value={occurredOn} onChange={setOccurredOn} />
        </label>
      </form>
    </Modal>
  );
}
