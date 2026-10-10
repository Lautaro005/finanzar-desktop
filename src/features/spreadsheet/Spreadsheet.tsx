/** Vista tipo planilla "Datos": ordenar, filtrar, editar y exportar XLSX. */

import { useMemo, useState, type JSX } from "react";

import { Icon } from "../../components/Icon";
import { MonthSelect } from "../../components/DateField";
import { EmptyState, ErrorBlock, LoadingBlock, Panel } from "../../components/ui";
import { api } from "../../lib/backend";
import { formatCents, formatDate, monthLabel } from "../../lib/format";
import { useAsync } from "../../lib/hooks";
import { openPath, saveFileDialog } from "../../lib/tauri";
import { useApp } from "../../app/context";
import type { Transaction } from "../../types/api";

type SortKey = "occurred_on" | "description" | "category" | "amount_cents";

export function Spreadsheet(): JSX.Element {
  const { period, setPeriod, toast, refresh, refreshKey } = useApp();
  const [sort, setSort] = useState<{ key: SortKey; dir: "asc" | "desc" }>({ key: "occurred_on", dir: "desc" });
  const [filter, setFilter] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [exporting, setExporting] = useState(false);

  const transactions = useAsync(() => api.transactions({ month: period }), [period, refreshKey]);
  const preview = useAsync(() => api.exportPreview(period), [period, refreshKey]);

  const rows = useMemo(() => {
    const list = (transactions.data?.transactions ?? []).filter((tx) => {
      if (!filter.trim()) return true;
      const needle = filter.toLowerCase();
      return (
        tx.description.toLowerCase().includes(needle) ||
        (tx.category ?? "").toLowerCase().includes(needle) ||
        formatCents(tx.amount_cents).toLowerCase().includes(needle)
      );
    });
    return list.sort((a, b) => {
      const valueA = a[sort.key];
      const valueB = b[sort.key];
      const comparison =
        typeof valueA === "number" && typeof valueB === "number"
          ? valueA - valueB
          : String(valueA).localeCompare(String(valueB));
      return sort.dir === "asc" ? comparison : -comparison;
    });
  }, [transactions.data, filter, sort]);

  const toggleSort = (key: SortKey) => {
    setSort((current) => ({ key, dir: current.key === key && current.dir === "asc" ? "desc" : "asc" }));
  };

  const commitEdit = async (tx: Transaction) => {
    try {
      await api.patchTransaction(tx.id, { category: draft });
      toast("Fila actualizada.");
      setEditing(null);
      refresh();
    } catch (error) {
      toast(error instanceof Error ? error.message : "No se pudo actualizar", "error");
    }
  };

  const exportWorkbook = async () => {
    setExporting(true);
    try {
      const suggested = `finanzar-${period}.xlsx`;
      const destination = await saveFileDialog(suggested);
      const result = await api.exportXlsx(period, destination ?? undefined);
      toast(`XLSX generado con ${result.sheets.length} hojas.`);
      if (destination) void openPath(destination);
    } catch (error) {
      toast(error instanceof Error ? error.message : "No se pudo exportar", "error");
    } finally {
      setExporting(false);
    }
  };

  // Los importes no se convierten: el total se informa por moneda.
  const totals = rows.reduce<Record<string, number>>((acc, tx) => {
    const currency = (tx.currency ?? "ARS").toUpperCase();
    acc[currency] = (acc[currency] ?? 0) + tx.amount_cents;
    return acc;
  }, {});
  const totalsLabel = Object.entries(totals)
    .map(([currency, cents]) => formatCents(cents, currency))
    .join(" · ");

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Planilla editable · {monthLabel(period)}</p>
          <h1>Datos.</h1>
          <p className="heading-copy">Filtrá, ordená, editá los campos permitidos y llevate tu planilla.</p>
        </div>
        <div className="heading-actions">
          <div className="period-picker">
            <Icon name="calendar" />
            <MonthSelect value={period} onChange={(next) => setPeriod(next)} ariaLabel="Período" />
          </div>
          <button type="button" className="primary-button" onClick={exportWorkbook} disabled={exporting}>
            <Icon name="download" /> {exporting ? "Exportando…" : "Exportar XLSX"}
          </button>
        </div>
      </div>

      <Panel
        title="Movimientos"
        subtitle={`${rows.length} filas · total ${totalsLabel || formatCents(0)}`}
        action={
          <label className="search-field">
            <Icon name="search" />
            <input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Filtrar…" aria-label="Filtrar filas" />
          </label>
        }
      >
        {transactions.loading && !transactions.data ? (
          <LoadingBlock />
        ) : transactions.error ? (
          <ErrorBlock message={transactions.error} onRetry={transactions.reload} />
        ) : rows.length === 0 ? (
          <EmptyState icon="table" title="Sin filas para este período" body="Importá y confirmá un resumen para ver datos acá." />
        ) : (
          <div className="movement-table-wrap">
            <table className="movement-table spreadsheet">
              <thead>
                <tr>
                  <th>
                    <button type="button" className="th-sort" onClick={() => toggleSort("occurred_on")}>
                      Fecha {sort.key === "occurred_on" ? (sort.dir === "asc" ? "↑" : "↓") : ""}
                    </button>
                  </th>
                  <th>
                    <button type="button" className="th-sort" onClick={() => toggleSort("description")}>
                      Descripción {sort.key === "description" ? (sort.dir === "asc" ? "↑" : "↓") : ""}
                    </button>
                  </th>
                  <th>
                    <button type="button" className="th-sort" onClick={() => toggleSort("category")}>
                      Categoría {sort.key === "category" ? (sort.dir === "asc" ? "↑" : "↓") : ""}
                    </button>
                  </th>
                  <th>Tipo</th>
                  <th className="align-right">
                    <button type="button" className="th-sort" onClick={() => toggleSort("amount_cents")}>
                      Importe {sort.key === "amount_cents" ? (sort.dir === "asc" ? "↑" : "↓") : ""}
                    </button>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((tx) => (
                  <tr key={tx.id}>
                    <td>{formatDate(tx.occurred_on)}</td>
                    <td className="movement-name">{tx.description}</td>
                    <td>
                      {editing === tx.id ? (
                        <span className="inline-edit">
                          <input value={draft} onChange={(event) => setDraft(event.target.value)} aria-label="Categoría" />
                          <button type="button" className="inline-link" onClick={() => commitEdit(tx)}>
                            Guardar
                          </button>
                        </span>
                      ) : (
                        <button
                          type="button"
                          className="category-tag editable"
                          onClick={() => {
                            setEditing(tx.id);
                            setDraft(tx.category ?? "");
                          }}
                        >
                          {tx.category ?? "Sin categoría"}
                        </button>
                      )}
                    </td>
                    <td>{tx.kind}</td>
                    <td className="amount-cell">{formatCents(tx.amount_cents, tx.currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel title="Hojas del workbook" subtitle="Se exportan diez hojas con formato y filtros.">
        {preview.data ? (
          <div className="sheet-grid">
            {preview.data.sheets.map((sheet) => (
              <div className="sheet-chip" key={sheet}>
                <Icon name="table" />
                <span>{sheet}</span>
                <small>{preview.data?.rowCounts[sheet] ?? 0} filas</small>
              </div>
            ))}
          </div>
        ) : (
          <LoadingBlock message="Preparando vista previa…" />
        )}
      </Panel>
    </>
  );
}
