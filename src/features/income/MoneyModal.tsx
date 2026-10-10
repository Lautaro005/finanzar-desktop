/** Modal para agregar dinero puntual o configurar el sueldo recurrente.

Un ingreso siempre va a una cuenta: sin cuenta la plata entra al balance pero no
aparece en ningún lado (por eso el modal pide la cuenta y, si no hay ninguna,
manda a crearla antes).
*/

import { useEffect, useMemo, useState, type JSX } from "react";

import { Icon } from "../../components/Icon";
import { DateInput } from "../../components/DateField";
import { Select } from "../../components/Select";
import { ErrorBlock, LoadingBlock, Modal } from "../../components/ui";
import { api } from "../../lib/backend";
import { currentPeriod, formatCents } from "../../lib/format";
import { useAsync } from "../../lib/hooks";
import { useApp } from "../../app/context";

const CURRENCY_OPTIONS = [
  { value: "ARS", label: "Pesos (AR$)" },
  { value: "USD", label: "Dólares (US$)" },
];

export function MoneyModal({ mode, onClose }: { mode: "income" | "salary"; onClose: () => void }): JSX.Element {
  const { toast, refresh, setRoute } = useApp();
  const accounts = useAsync(() => api.accounts(), []);
  const [kind, setKind] = useState<"income" | "salary" | "transfer">(mode === "salary" ? "salary" : "income");
  const [amount, setAmount] = useState("950000");
  const [source, setSource] = useState(mode === "salary" ? "Sueldo" : "");
  const [dayOfMonth, setDayOfMonth] = useState(1);
  const [occurredOn, setOccurredOn] = useState(`${currentPeriod()}-01`);
  const [repeat, setRepeat] = useState(mode === "salary");
  const [accountId, setAccountId] = useState("");
  const [currency, setCurrency] = useState("ARS");
  const [saving, setSaving] = useState(false);

  const list = accounts.data?.accounts ?? [];
  const accountOptions = useMemo(
    () => list.map((account) => ({ value: account.id, label: `${account.name} (${account.currency})` })),
    [list],
  );

  useEffect(() => {
    if (!accountId && list.length > 0) {
      setAccountId(list[0].id);
      setCurrency(list[0].currency || "ARS");
    }
  }, [accountId, list]);

  const cents = useMemo(() => {
    const parsed = Number(String(amount).replace(/\./g, "").replace(",", "."));
    return Number.isFinite(parsed) ? Math.round(parsed * 100) : 0;
  }, [amount]);

  const goToAccounts = () => {
    onClose();
    setRoute("accounts");
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (cents <= 0) {
      toast("Ingresá un importe mayor a cero.", "error");
      return;
    }
    if (!accountId) {
      toast("Elegí la cuenta donde entra el ingreso.", "error");
      return;
    }
    setSaving(true);
    try {
      if (kind === "salary") {
        await api.createRecurring({
          name: source || "Sueldo",
          source: source || "Sueldo",
          kind: "salary",
          amountCents: cents,
          currency,
          accountId,
          dayOfMonth,
          startDate: `${currentPeriod()}-01`,
          active: repeat,
        });
        toast(`Sueldo configurado: ${formatCents(cents, currency)} el día ${dayOfMonth}.`);
      } else {
        await api.createIncome({
          amountCents: cents,
          source: source || (kind === "transfer" ? "Transferencia" : "Ingreso"),
          kind: kind === "transfer" ? "adjustment" : "punctual",
          currency,
          accountId,
          occurredOn,
        });
        toast(`Ingreso registrado: ${formatCents(cents, currency)}.`);
      }
      refresh();
      onClose();
    } catch (error) {
      toast(error instanceof Error ? error.message : "No se pudo guardar", "error");
    } finally {
      setSaving(false);
    }
  };

  const loadingAccounts = accounts.loading && !accounts.data;

  return (
    <Modal
      title={kind === "salary" ? "Configurar sueldo" : "Agregar dinero"}
      eyebrow="Balance local · operación segura"
      onClose={onClose}
      size="money"
      footer={
        <>
          <button type="button" className="secondary-button" onClick={onClose}>
            Cancelar
          </button>
          <button type="submit" form="money-form" className="primary-button" disabled={saving || list.length === 0}>
            <Icon name="check" /> {saving ? "Guardando…" : "Guardar"}
          </button>
        </>
      }
    >
      {loadingAccounts ? (
        <LoadingBlock />
      ) : accounts.error ? (
        <ErrorBlock message={accounts.error} onRetry={accounts.reload} />
      ) : list.length === 0 ? (
        <div className="form-notice" role="alert">
          <Icon name="wallet" />
          <div>
            <strong>Primero agregá una cuenta</strong>
            <span>El ingreso se acredita en la cuenta que elijas, así aparece en tu balance y en tus cuentas.</span>
          </div>
          <button type="button" className="secondary-button" onClick={goToAccounts}>
            <Icon name="plus" /> Crear cuenta
          </button>
        </div>
      ) : (
        <>
          <form id="money-form" className="money-form-grid" onSubmit={submit}>
            <label>
              <span>Qué querés registrar</span>
              <Select
                value={kind}
                options={[
                  { value: "income", label: "Ingreso puntual" },
                  { value: "salary", label: "Sueldo recurrente" },
                  { value: "transfer", label: "Dinero inicial / transferencia" },
                ]}
                onChange={(next) => setKind(next as typeof kind)}
                ariaLabel="Qué querés registrar"
              />
            </label>
            <label>
              <span>Cuenta</span>
              <Select
                value={accountId}
                options={accountOptions}
                onChange={(next) => {
                  setAccountId(next);
                  const found = list.find((account) => account.id === next);
                  if (found?.currency) setCurrency(found.currency);
                }}
                ariaLabel="Cuenta donde entra el ingreso"
              />
            </label>
            <label>
              <span>Moneda</span>
              <Select
                value={currency}
                options={CURRENCY_OPTIONS}
                onChange={setCurrency}
                ariaLabel="Moneda del ingreso"
              />
            </label>
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
              <input
                type="text"
                value={source}
                placeholder="Sueldo, freelance, bono…"
                onChange={(event) => setSource(event.target.value)}
              />
            </label>
            {kind === "salary" ? (
              <label>
                <span>Día del mes</span>
                <input
                  type="number"
                  min={1}
                  max={31}
                  value={dayOfMonth}
                  onChange={(event) => setDayOfMonth(Number(event.target.value))}
                />
              </label>
            ) : (
              <label>
                <span>Fecha de acreditación</span>
                <DateInput value={occurredOn} onChange={setOccurredOn} />
              </label>
            )}
          </form>
          <label className="money-check">
            <input type="checkbox" checked={repeat} onChange={(event) => setRepeat(event.target.checked)} />
            <span>
              <strong>Repetir automáticamente</strong>
              <small>Se suma al balance el mismo día de cada mes.</small>
            </span>
          </label>
          <div className="money-preview">
            <span className="preview-icon">
              <Icon name="trend" />
            </span>
            <div>
              <strong>Impacto estimado</strong>
              <small>El balance reflejará este ingreso y se verá en tu calendario.</small>
            </div>
            <strong>{formatCents(cents, currency)}</strong>
          </div>
        </>
      )}
    </Modal>
  );
}
