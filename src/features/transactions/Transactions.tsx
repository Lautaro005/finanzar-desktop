/** Movimientos: filtros, búsqueda y edición de campos permitidos. */

import { useMemo, useState, type JSX } from "react";

import { Icon } from "../../components/Icon";
import { EmptyState, ErrorBlock, LoadingBlock, Panel } from "../../components/ui";
import { api } from "../../lib/backend";
import { formatCents, formatDate } from "../../lib/format";
import { useAsync } from "../../lib/hooks";
import { useApp } from "../../app/context";

const KINDS = [
  { value: "", label: "Todos" },
  { value: "installment", label: "Cuotas" },
  { value: "subscription", label: "Suscripciones" },
];

export function Transactions(): JSX.Element {
  const { period, toast, refresh, refreshKey } = useApp();
  const [kind, setKind] = useState("");
  const [cardId, setCardId] = useState("");
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [draftCategory, setDraftCategory] = useState("");

  const cards = useAsync(() => api.cards(), [refreshKey]);
  const transactions = useAsync(() => {
    const params: { month: string; cardId?: string; kind?: string } = { month: period };
    if (kind) params.kind = kind;
    if (cardId) params.cardId = cardId;
    return api.transactions(params);
  }, [period, kind, cardId, refreshKey]);

  const rows = useMemo(() => {
    const list = transactions.data?.transactions ?? [];
    if (!query.trim()) return list;
    const needle = query.toLowerCase();
    return list.filter(
      (tx) => tx.description.toLowerCase().includes(needle) || (tx.category ?? "").toLowerCase().includes(needle),
    );
  }, [transactions.data, query]);

  const saveCategory = async (id: string) => {
    try {
      await api.patchTransaction(id, { category: draftCategory });
      toast("Categoría actualizada.");
      setEditing(null);
      refresh();
    } catch (error) {
      toast(error instanceof Error ? error.message : "No se pudo actualizar", "error");
    }
  };

  const total = rows.reduce((acc, tx) => acc + tx.amount_cents, 0);

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">{period} · movimientos confirmados</p>
          <h1>Movimientos.</h1>
          <p className="heading-copy">Todo lo que entra en tus resúmenes, ordenado y categorizado.</p>
        </div>
      </div>

      <div className="movement-summary">
        <div>
          <span>Movimientos</span>
          <strong>{rows.length}</strong>
        </div>
        <div>
          <span>Total listado</span>
          <strong>{formatCents(total)}</strong>
        </div>
      </div>

      <Panel>
        <div className="movement-toolbar">
          <div className="filter-tabs">
            {KINDS.map((option) => (
              <button
                key={option.value}
                type="button"
                className={kind === option.value ? "active" : ""}
                onClick={() => setKind(option.value)}
              >
                {option.label}
              </button>
            ))}
          </div>
          <div className="filter-actions">
            <select value={cardId} onChange={(event) => setCardId(event.target.value)} aria-label="Filtrar por tarjeta">
              <option value="">Todas las tarjetas</option>
              {(cards.data?.cards ?? []).map((card) => (
                <option key={card.id} value={card.id}>
                  {card.name}
                </option>
              ))}
            </select>
            <label className="search-field">
              <Icon name="search" />
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Buscar…" aria-label="Buscar movimientos" />
            </label>
          </div>
        </div>

        {transactions.loading && !transactions.data ? (
          <LoadingBlock />
        ) : transactions.error ? (
          <ErrorBlock message={transactions.error} onRetry={transactions.reload} />
        ) : rows.length === 0 ? (
          <EmptyState icon="receipt" title="No hay movimientos con estos filtros" body="Probá cambiar el período o la tarjeta." />
        ) : (
          <div className="movement-table-wrap">
            <table className="movement-table">
              <thead>
                <tr>
                  <th>Movimiento</th>
                  <th>Fecha</th>
                  <th>Categoría</th>
                  <th>Cuotas</th>
                  <th>Estado</th>
                  <th className="align-right">Importe</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((tx) => (
                  <tr key={tx.id}>
                    <td className="movement-name">
                      {tx.description}
                      <small>{tx.kind}</small>
                    </td>
                    <td>{formatDate(tx.occurred_on)}</td>
                    <td>
                      {editing === tx.id ? (
                        <span className="inline-edit">
                          <input
                            value={draftCategory}
                            onChange={(event) => setDraftCategory(event.target.value)}
                            aria-label="Categoría"
                          />
                          <button type="button" className="inline-link" onClick={() => saveCategory(tx.id)}>
                            Guardar
                          </button>
                        </span>
                      ) : (
                        <button
                          type="button"
                          className="category-tag editable"
                          onClick={() => {
                            setEditing(tx.id);
                            setDraftCategory(tx.category ?? "");
                          }}
                        >
                          {tx.category ?? "Sin categoría"}
                        </button>
                      )}
                    </td>
                    <td>
                      {tx.installment_number && tx.installment_total
                        ? `${tx.installment_number} / ${tx.installment_total}`
                        : "—"}
                    </td>
                    <td>{tx.confirmed ? "Confirmado" : "Pendiente"}</td>
                    <td className="amount-cell">{formatCents(tx.amount_cents, tx.currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}
