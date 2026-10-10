/** Cuentas: listado, creación, edición (nombre, tipo, moneda y saldo) y archivado. */

import { useState, type JSX } from "react";

import { Icon } from "../../components/Icon";
import { RowMenu } from "../../components/RowMenu";
import { Select } from "../../components/Select";
import { EmptyState, ErrorBlock, LoadingBlock, Modal, Panel, StatusPill } from "../../components/ui";
import { api } from "../../lib/backend";
import { formatCents } from "../../lib/format";
import { useAsync } from "../../lib/hooks";
import { useApp } from "../../app/context";
import type { Account } from "../../types/api";

const KINDS = [
  { value: "bank", label: "Banco" },
  { value: "wallet", label: "Billetera" },
  { value: "cash", label: "Efectivo" },
  { value: "savings", label: "Ahorro" },
  { value: "card", label: "Tarjeta" },
];

const CURRENCIES = [
  { value: "ARS", label: "Pesos (AR$)" },
  { value: "USD", label: "Dólares (US$)" },
];

export function Accounts(): JSX.Element {
  const { toast, refresh, refreshKey } = useApp();
  const accounts = useAsync(() => api.accounts(), [refreshKey]);
  const [name, setName] = useState("");
  const [kind, setKind] = useState("bank");
  const [currency, setCurrency] = useState("ARS");
  const [opening, setOpening] = useState("");
  const [institution, setInstitution] = useState("");
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState<Account | null>(null);

  const create = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!name.trim()) {
      toast("Poné un nombre para la cuenta.", "error");
      return;
    }
    setSaving(true);
    try {
      await api.createAccount({
        name: name.trim(),
        kind,
        currency,
        openingBalance: opening || "0",
        institution: institution.trim() || null,
      });
      toast(`Cuenta «${name}» creada en ${currency === "USD" ? "dólares" : "pesos"}.`);
      setName("");
      setOpening("");
      setInstitution("");
      refresh();
    } catch (error) {
      toast(error instanceof Error ? error.message : "No se pudo crear la cuenta", "error");
    } finally {
      setSaving(false);
    }
  };

  const archive = async (id: string, archived: boolean) => {
    try {
      await api.patchAccount(id, { archived: !archived });
      toast(archived ? "Cuenta reactivada." : "Cuenta archivada.");
      refresh();
    } catch (error) {
      toast(error instanceof Error ? error.message : "No se pudo actualizar", "error");
    }
  };

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Balance consolidado</p>
          <h1>Cuentas.</h1>
          <p className="heading-copy">Cada lugar donde tenés plata, con su saldo real en pesos o en dólares.</p>
        </div>
      </div>

      <div className="two-column">
        <Panel title="Nueva cuenta" subtitle="Banco, billetera, efectivo, ahorro o tarjeta.">
          <form className="stack-form" onSubmit={create}>
            <label>
              <span>Nombre</span>
              <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Cuenta sueldo" required />
            </label>
            <label>
              <span>Tipo</span>
              <Select value={kind} options={KINDS} onChange={setKind} ariaLabel="Tipo de cuenta" />
            </label>
            <label>
              <span>Moneda</span>
              <Select value={currency} options={CURRENCIES} onChange={setCurrency} ariaLabel="Moneda de la cuenta" />
            </label>
            <label>
              <span>Saldo inicial</span>
              <input
                value={opening}
                onChange={(event) => setOpening(event.target.value)}
                placeholder="0"
                inputMode="decimal"
              />
            </label>
            <label>
              <span>Institución (opcional)</span>
              <input
                value={institution}
                onChange={(event) => setInstitution(event.target.value)}
                placeholder="Banco Galicia"
              />
            </label>
            <button type="submit" className="primary-button" disabled={saving}>
              <Icon name="plus" /> {saving ? "Creando…" : "Crear cuenta"}
            </button>
          </form>
        </Panel>

        <Panel title="Tus cuentas" subtitle="Saldo disponible por cuenta.">
          {accounts.loading && !accounts.data ? (
            <LoadingBlock />
          ) : accounts.error ? (
            <ErrorBlock message={accounts.error} onRetry={accounts.reload} />
          ) : !accounts.data || accounts.data.accounts.length === 0 ? (
            <EmptyState icon="wallet" title="Sin cuentas todavía" body="Creá la primera para empezar." />
          ) : (
            <div className="accounts-list">
              {accounts.data.accounts.map((account) => (
                <div className="account-row" key={account.id}>
                  <span className={`account-icon ${account.kind}`}>
                    <Icon name={account.kind === "bank" ? "building" : "wallet"} />
                  </span>
                  <span className="account-copy">
                    <strong>
                      {account.name}
                      {account.currency === "USD" && <span className="currency-tag">US$</span>}
                    </strong>
                    <small>
                      {KINDS.find((option) => option.value === account.kind)?.label ?? account.kind}
                      {account.institution ? ` · ${account.institution}` : ""}
                    </small>
                  </span>
                  <strong className="account-balance">
                    {formatCents(account.balance_cents ?? account.opening_balance_cents, account.currency)}
                  </strong>
                  <RowMenu
                    label={`Acciones para ${account.name}`}
                    actions={[
                      { label: "Editar", icon: "pencil", onSelect: () => setEditing(account) },
                      {
                        label: account.archived ? "Reactivar" : "Archivar",
                        icon: "eye",
                        danger: !account.archived,
                        onSelect: () => void archive(account.id, Boolean(account.archived)),
                      },
                    ]}
                  />
                  {Boolean(account.archived) && <StatusPill status="error" />}
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>

      {editing && (
        <EditAccountModal
          account={editing}
          onClose={() => setEditing(null)}
          onSaved={(message) => {
            toast(message);
            setEditing(null);
            refresh();
          }}
          onError={(message) => toast(message, "error")}
        />
      )}
    </>
  );
}

function EditAccountModal({
  account,
  onClose,
  onSaved,
  onError,
}: {
  account: Account;
  onClose: () => void;
  onSaved: (message: string) => void;
  onError: (message: string) => void;
}): JSX.Element {
  const [name, setName] = useState(account.name);
  const [kind, setKind] = useState(account.kind);
  const [currency, setCurrency] = useState(account.currency || "ARS");
  const [opening, setOpening] = useState(() => (account.opening_balance_cents / 100).toFixed(2).replace(".", ","));
  const [institution, setInstitution] = useState(account.institution ?? "");
  const [saving, setSaving] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!name.trim()) {
      onError("Poné un nombre para la cuenta.");
      return;
    }
    const parsed = Number(opening.replace(/\./g, "").replace(",", "."));
    if (!Number.isFinite(parsed)) {
      onError("El saldo inicial no es un importe válido.");
      return;
    }
    setSaving(true);
    try {
      await api.patchAccount(account.id, {
        name: name.trim(),
        kind,
        currency,
        openingBalanceCents: Math.round(parsed * 100),
        institution: institution.trim() || null,
      });
      onSaved("Cuenta actualizada.");
    } catch (error) {
      onError(error instanceof Error ? error.message : "No se pudo guardar la cuenta");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title={`Editar ${account.name}`}
      eyebrow="Cuentas"
      onClose={onClose}
      size="money"
      footer={
        <>
          <button type="button" className="secondary-button" onClick={onClose}>
            Cancelar
          </button>
          <button type="submit" form="edit-account-form" className="primary-button" disabled={saving}>
            <Icon name="check" /> {saving ? "Guardando…" : "Guardar"}
          </button>
        </>
      }
    >
      <form id="edit-account-form" className="money-form-grid" onSubmit={submit}>
        <label>
          <span>Nombre</span>
          <input type="text" value={name} onChange={(event) => setName(event.target.value)} required />
        </label>
        <label>
          <span>Tipo</span>
          <Select value={kind} options={KINDS} onChange={(next) => setKind(next as Account["kind"])} ariaLabel="Tipo de cuenta" />
        </label>
        <label>
          <span>Moneda</span>
          <Select value={currency} options={CURRENCIES} onChange={setCurrency} ariaLabel="Moneda de la cuenta" />
        </label>
        <label>
          <span>Saldo inicial</span>
          <input
            type="text"
            inputMode="decimal"
            value={opening}
            onChange={(event) => setOpening(event.target.value)}
          />
        </label>
        <label>
          <span>Institución (opcional)</span>
          <input type="text" value={institution} onChange={(event) => setInstitution(event.target.value)} />
        </label>
      </form>
    </Modal>
  );
}
