/** Ingresos: sueldo recurrente (activar/pausar) e historial de ingresos. */

import { useEffect, useMemo, useState, type JSX } from "react";

import { Icon } from "../../components/Icon";
import { DateInput } from "../../components/DateField";
import { RowMenu } from "../../components/RowMenu";
import { Select } from "../../components/Select";
import { EmptyState, ErrorBlock, LoadingBlock, Modal, Panel } from "../../components/ui";
import { api } from "../../lib/backend";
import { formatCents, formatDate } from "../../lib/format";
import { useAsync } from "../../lib/hooks";
import { useApp } from "../../app/context";
import type { IncomeEntry, RecurringIncome } from "../../types/api";

const CURRENCY_OPTIONS = [
  { value: "ARS", label: "Pesos (AR$)" },
  { value: "USD", label: "Dólares (US$)" },
];

export function Income(): JSX.Element {
  const { toast, refresh, refreshKey, openMoney, setRoute } = useApp();
  const incomes = useAsync(() => api.incomes(), [refreshKey]);
  const accounts = useAsync(() => api.accounts(), [refreshKey]);
  const [punctualAmount, setPunctualAmount] = useState("");
  const [punctualSource, setPunctualSource] = useState("");
  const [punctualDate, setPunctualDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [punctualAccount, setPunctualAccount] = useState("");
  const [punctualCurrency, setPunctualCurrency] = useState("ARS");
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState<IncomeEntry | null>(null);
  const [deleting, setDeleting] = useState<IncomeEntry | null>(null);
  const [deletingRecurring, setDeletingRecurring] = useState<RecurringIncome | null>(null);

  const accountList = accounts.data?.accounts ?? [];
  const accountOptions = useMemo(
    () => accountList.map((account) => ({ value: account.id, label: `${account.name} (${account.currency})` })),
    [accountList],
  );
  const accountNames = useMemo(
    () => new Map(accountList.map((account) => [account.id, account.name])),
    [accountList],
  );

  useEffect(() => {
    if (!punctualAccount && accountList.length > 0) {
      setPunctualAccount(accountList[0].id);
      setPunctualCurrency(accountList[0].currency || "ARS");
    }
  }, [accountList, punctualAccount]);

  const addPunctual = async (event: React.FormEvent) => {
    event.preventDefault();
    const parsed = Number(punctualAmount.replace(/\./g, "").replace(",", "."));
    if (!Number.isFinite(parsed) || parsed <= 0) {
      toast("Ingresá un importe válido.", "error");
      return;
    }
    if (!punctualAccount) {
      toast("Elegí la cuenta donde entra el ingreso.", "error");
      return;
    }
    setSaving(true);
    try {
      await api.createIncome({
        amountCents: Math.round(parsed * 100),
        source: punctualSource.trim() || "Ingreso",
        kind: "punctual",
        accountId: punctualAccount,
        currency: punctualCurrency,
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

  const removeRecurring = async (recurring: RecurringIncome) => {
    try {
      await api.deleteRecurring(recurring.id);
      toast(`Ingreso automático «${recurring.name}» eliminado.`);
      setDeletingRecurring(null);
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
                      {formatCents(item.amount_cents, item.currency)} · día {item.day_of_month} de cada mes ·{" "}
                      {item.account_id ? (accountNames.get(item.account_id) ?? "Cuenta") : "Sin cuenta"}
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
                  <RowMenu
                    label={`Acciones para ${item.name}`}
                    actions={[
                      { label: "Borrar", icon: "trash", danger: true, onSelect: () => setDeletingRecurring(item) },
                    ]}
                  />
                </div>
              ))}
            </div>
          )}
        </Panel>

        <Panel title="Registrar un ingreso" subtitle="Puntual, bono o transferencia.">
          {accounts.data && accountList.length === 0 ? (
            <div className="form-notice" role="alert">
              <Icon name="wallet" />
              <div>
                <strong>Primero agregá una cuenta</strong>
                <span>El ingreso se acredita en una cuenta; si no, las cuentas quedan en cero.</span>
              </div>
              <button type="button" className="secondary-button" onClick={() => setRoute("accounts")}>
                <Icon name="plus" /> Crear cuenta
              </button>
            </div>
          ) : (
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
                <span>Cuenta</span>
                <Select
                  value={punctualAccount}
                  options={accountOptions}
                  onChange={(next) => {
                    setPunctualAccount(next);
                    const found = accountList.find((account) => account.id === next);
                    if (found?.currency) setPunctualCurrency(found.currency);
                  }}
                  ariaLabel="Cuenta donde entra el ingreso"
                />
              </label>
              <label>
                <span>Moneda</span>
                <Select
                  value={punctualCurrency}
                  options={CURRENCY_OPTIONS}
                  onChange={setPunctualCurrency}
                  ariaLabel="Moneda del ingreso"
                />
              </label>
              <label>
                <span>Origen</span>
                <input
                  value={punctualSource}
                  onChange={(event) => setPunctualSource(event.target.value)}
                  placeholder="Freelance"
                />
              </label>
              <label>
                <span>Fecha</span>
                <DateInput value={punctualDate} onChange={setPunctualDate} />
              </label>
              <button type="submit" className="primary-button" disabled={saving || accountList.length === 0}>
                <Icon name="check" /> {saving ? "Guardando…" : "Registrar ingreso"}
              </button>
            </form>
          )}
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
                  <th>Cuenta</th>
                  <th className="align-right">Importe</th>
                  <th className="actions-column" aria-label="Acciones"></th>
                </tr>
              </thead>
              <tbody>
                {incomes.data.entries.map((entry) => (
                  <tr key={entry.id}>
                    <td>{formatDate(entry.occurred_on)}</td>
                    <td className="movement-name">{entry.source}</td>
                    <td>{entry.kind}</td>
                    <td>{entry.account_id ? (accountNames.get(entry.account_id) ?? "Cuenta") : "Sin cuenta"}</td>
                    <td className="amount-cell">{formatCents(entry.amount_cents, entry.currency)}</td>
                    <td className="align-right actions-cell">
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
          accounts={accountOptions}
          accountCurrency={(id) => accountList.find((account) => account.id === id)?.currency ?? "ARS"}
          onClose={() => setEditing(null)}
          onSaved={() => {
            toast("Ingreso actualizado.");
            setEditing(null);
            refresh();
          }}
          onError={(message) => toast(message, "error")}
        />
      )}

      {deletingRecurring && (
        <Modal
          title="Borrar ingreso automático"
          eyebrow="Ingresos recurrentes"
          size="compact"
          onClose={() => setDeletingRecurring(null)}
          footer={
            <>
              <button type="button" className="secondary-button" onClick={() => setDeletingRecurring(null)}>
                Cancelar
              </button>
              <button type="button" className="danger-button" onClick={() => void removeRecurring(deletingRecurring)}>
                <Icon name="trash" /> Borrar
              </button>
            </>
          }
        >
          <div className="confirm-body">
            <p className="confirm-copy">
              ¿Eliminar <strong>{deletingRecurring.name}</strong> por{" "}
              {formatCents(deletingRecurring.amount_cents, deletingRecurring.currency)} de cada mes?
            </p>
            <p className="confirm-note">
              Deja de acreditarse desde ahora. Los ingresos que ya entraron quedan en el historial.
            </p>
          </div>
        </Modal>
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
  accounts,
  accountCurrency,
  onClose,
  onSaved,
  onError,
}: {
  entry: IncomeEntry;
  accounts: Array<{ value: string; label: string }>;
  accountCurrency: (id: string) => string;
  onClose: () => void;
  onSaved: () => void;
  onError: (message: string) => void;
}): JSX.Element {
  const [amount, setAmount] = useState(() =>
    (entry.amount_cents / 100).toFixed(2).replace(".", ","),
  );
  const [source, setSource] = useState(entry.source);
  const [occurredOn, setOccurredOn] = useState(entry.occurred_on.slice(0, 10));
  const [accountId, setAccountId] = useState(entry.account_id ?? "");
  const [currency, setCurrency] = useState(entry.currency);
  const [saving, setSaving] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    const parsed = Number(amount.replace(/\./g, "").replace(",", "."));
    if (!Number.isFinite(parsed) || parsed <= 0) {
      onError("Ingresá un importe válido.");
      return;
    }
    if (!accountId) {
      onError("Elegí la cuenta donde entra el ingreso.");
      return;
    }
    setSaving(true);
    try {
      await api.patchIncome(entry.id, {
        amountCents: Math.round(parsed * 100),
        source: source.trim() || entry.source,
        accountId,
        currency,
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
          <span>Cuenta</span>
          <Select
            value={accountId}
            options={accounts}
            onChange={(next) => {
              setAccountId(next);
              setCurrency(accountCurrency(next));
            }}
            ariaLabel="Cuenta donde entra el ingreso"
          />
        </label>
        <label>
          <span>Moneda</span>
          <Select value={currency} options={CURRENCY_OPTIONS} onChange={setCurrency} ariaLabel="Moneda del ingreso" />
        </label>
        <label>
          <span>Fecha</span>
          <DateInput value={occurredOn} onChange={setOccurredOn} />
        </label>
      </form>
    </Modal>
  );
}
