/** Cuentas: listado, creación, edición y archivado. */

import { useState, type JSX } from "react";

import { Icon } from "../../components/Icon";
import { Select } from "../../components/Select";
import { EmptyState, ErrorBlock, LoadingBlock, Panel, StatusPill } from "../../components/ui";
import { api } from "../../lib/backend";
import { formatCents } from "../../lib/format";
import { useAsync } from "../../lib/hooks";
import { useApp } from "../../app/context";

const KINDS = [
  { value: "bank", label: "Banco" },
  { value: "wallet", label: "Billetera" },
  { value: "cash", label: "Efectivo" },
  { value: "savings", label: "Ahorro" },
  { value: "card", label: "Tarjeta" },
];

export function Accounts(): JSX.Element {
  const { toast, refresh, refreshKey } = useApp();
  const accounts = useAsync(() => api.accounts(), [refreshKey]);
  const [name, setName] = useState("");
  const [kind, setKind] = useState("bank");
  const [opening, setOpening] = useState("");
  const [institution, setInstitution] = useState("");
  const [saving, setSaving] = useState(false);

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
        openingBalance: opening || "0",
        institution: institution.trim() || null,
      });
      toast(`Cuenta «${name}» creada.`);
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
          <p className="heading-copy">Cada lugar donde tenés plata, con su saldo real.</p>
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
              <span>Saldo inicial</span>
              <input value={opening} onChange={(event) => setOpening(event.target.value)} placeholder="0" inputMode="decimal" />
            </label>
            <label>
              <span>Institución (opcional)</span>
              <input value={institution} onChange={(event) => setInstitution(event.target.value)} placeholder="Banco Galicia" />
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
                    <strong>{account.name}</strong>
                    <small>
                      {KINDS.find((option) => option.value === account.kind)?.label ?? account.kind}
                      {account.institution ? ` · ${account.institution}` : ""}
                    </small>
                  </span>
                  <strong className="account-balance">{formatCents(account.opening_balance_cents)}</strong>
                  <button
                    type="button"
                    className="inline-link"
                    onClick={() => archive(account.id, Boolean(account.archived))}
                  >
                    {account.archived ? "Reactivar" : "Archivar"}
                  </button>
                  {Boolean(account.archived) && <StatusPill status="error" />}
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>
    </>
  );
}
