/** Documentos: importar PDF, ejecutar OCR, revisar y confirmar. */

import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type JSX } from "react";

import { Icon } from "../../components/Icon";
import { DateInput } from "../../components/DateField";
import { RowMenu } from "../../components/RowMenu";
import { Select } from "../../components/Select";
import { EmptyState, ErrorBlock, LoadingBlock, Modal, Panel, StatusPill } from "../../components/ui";
import { api } from "../../lib/backend";
import { ddmmToIso, formatCents, formatDate, isoToDdmm } from "../../lib/format";
import { useAsync } from "../../lib/hooks";
import { pickPdf } from "../../lib/tauri";
import { useApp } from "../../app/context";
import type { DocumentPageImage, Statement, StatementField, Transaction } from "../../types/api";

/** Campos con opciones fijas: el emisor y la moneda se eligen, no se tipean. */
const FIELD_CHOICES: Record<string, Array<{ value: string; label: string }>> = {
  brand: [
    { value: "amex", label: "American Express" },
    { value: "master", label: "Mastercard" },
    { value: "visa", label: "Visa" },
    { value: "other", label: "Otra" },
  ],
  currency: [
    { value: "ARS", label: "Pesos (AR$)" },
    { value: "USD", label: "Dólares (US$)" },
  ],
};

const FIELD_LABELS: Record<string, string> = {
  total: "Total a pagar",
  minimum: "Pago mínimo",
  due_date: "Vencimiento",
  close_date: "Fecha de cierre",
  brand: "Marca de tarjeta",
  currency: "Moneda",
  period: "Período",
  card: "Tarjeta",
};

function confidenceClass(confidence: number | null): string {
  if (confidence === null) return "low";
  if (confidence >= 0.9) return "high";
  if (confidence >= 0.75) return "medium";
  return "low";
}

export function Documents(): JSX.Element {
  const { toast, refresh, refreshKey } = useApp();
  const documents = useAsync(() => api.documents(), [refreshKey]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [deletingDoc, setDeletingDoc] = useState<Statement | null>(null);

  const list = documents.data?.documents ?? [];
  const selected = useMemo(
    () => list.find((doc) => doc.id === selectedId) ?? list[0] ?? null,
    [list, selectedId],
  );

  const review = useAsync(
    () => (selected ? api.review(selected.id) : Promise.resolve(null)),
    [selected?.id, refreshKey],
  );

  const runImport = useCallback(async () => {
    const path = await pickPdf();
    if (!path) {
      if (typeof window !== "undefined" && !("__TAURI_INTERNALS__" in window)) {
        toast("Importar un PDF requiere abrir la app de escritorio.", "error");
      }
      return;
    }
    setBusy("import");
    try {
      const result = await api.importDocument(path);
      toast("Resumen importado. Iniciando OCR local…");
      setSelectedId(result.document.id);
      setBusy(`ocr:${result.document.id}`);
      const ocr = await api.runOcr(result.document.id, "auto");
      toast(`Extracción lista con ${ocr.engine}: ${ocr.transactions} movimientos.`);
      refresh();
    } catch (error) {
      toast(error instanceof Error ? error.message : "No se pudo importar el PDF", "error");
    } finally {
      setBusy(null);
    }
  }, [refresh, toast]);

  const removeDocument = async (doc: Statement) => {
    try {
      await api.deleteDocument(doc.id);
      toast(`Se borró ${doc.filename}.`);
      setDeletingDoc(null);
      setSelectedId(null);
      setReviewOpen(false);
      refresh();
    } catch (error) {
      toast(error instanceof Error ? error.message : "No se pudo borrar el documento", "error");
    }
  };

  const runOcr = async (id: string) => {
    setBusy(`ocr:${id}`);
    try {
      const result = await api.runOcr(id, "auto");
      toast(`OCR con ${result.engine}: ${result.fields} campos y ${result.transactions} movimientos.`);
      refresh();
    } catch (error) {
      toast(error instanceof Error ? error.message : "Falló el OCR", "error");
    } finally {
      setBusy(null);
    }
  };

  const confirm = async (id: string) => {
    setBusy(`confirm:${id}`);
    try {
      const result = await api.confirmDocument(id);
      toast(`Resumen confirmado e indexado (${result.indexedChunks} fragmentos).`);
      setReviewOpen(false);
      refresh();
    } catch (error) {
      toast(error instanceof Error ? error.message : "No se pudo confirmar", "error");
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Bóveda local · {list.length} documentos</p>
          <h1>Tus documentos.</h1>
          <p className="heading-copy">Cada resumen queda en tu dispositivo y conserva su trazabilidad.</p>
        </div>
        <button type="button" className="primary-button" onClick={runImport} disabled={busy === "import"}>
          <Icon name="plus" /> {busy === "import" ? "Importando…" : "Cargar resumen PDF"}
        </button>
      </div>

      <div className="document-layout">
        <Panel title="Resúmenes" subtitle="Ordenados por fecha de importación." className="document-list-panel">
          {documents.loading && !documents.data ? (
            <LoadingBlock />
          ) : documents.error ? (
            <ErrorBlock message={documents.error} onRetry={documents.reload} />
          ) : list.length === 0 ? (
            <EmptyState
              icon="scan"
              title="Todavía no cargaste resúmenes"
              body="Importá un PDF de tarjeta para procesarlo con OCR local."
              action={
                <button type="button" className="secondary-button" onClick={runImport}>
                  <Icon name="plus" /> Cargar resumen
                </button>
              }
            />
          ) : (
            <div className="document-list">
              {list.map((doc) => (
                <div
                  key={doc.id}
                  className={`document-item ${selected?.id === doc.id ? "active" : ""}`}
                  role="button"
                  tabIndex={0}
                  onClick={() => setSelectedId(doc.id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setSelectedId(doc.id);
                    }
                  }}
                >
                  <span className="doc-type">PDF</span>
                  <span className="doc-copy">
                    <strong>{doc.filename}</strong>
                    <small>
                      {formatDate(doc.imported_at.slice(0, 10))} · {doc.pages} pág.
                    </small>
                  </span>
                  <StatusPill status={doc.status} />
                  <RowMenu
                    label={`Acciones para ${doc.filename}`}
                    actions={[
                      { label: "Borrar documento", icon: "trash", danger: true, onSelect: () => setDeletingDoc(doc) },
                    ]}
                  />
                </div>
              ))}
            </div>
          )}
        </Panel>

        <Panel className="document-detail">
          {!selected ? (
            <EmptyState icon="file" title="Seleccioná un documento" body="Elegí un resumen de la lista para revisarlo." />
          ) : (
            <DocumentDetail
              statement={selected}
              fields={review.data?.fields ?? []}
              busy={busy}
              onOcr={() => runOcr(selected.id)}
              onReview={() => setReviewOpen(true)}
              onConfirm={() => confirm(selected.id)}
            />
          )}
        </Panel>
      </div>

      {deletingDoc && (
        <Modal
          title="Borrar documento"
          eyebrow="Documento local"
          size="compact"
          onClose={() => setDeletingDoc(null)}
          footer={
            <>
              <button type="button" className="secondary-button" onClick={() => setDeletingDoc(null)}>
                Cancelar
              </button>
              <button type="button" className="danger-button" onClick={() => void removeDocument(deletingDoc)}>
                <Icon name="trash" /> Borrar
              </button>
            </>
          }
        >
          <div className="confirm-body">
            <p className="confirm-copy">
              ¿Borrar <strong>{deletingDoc.filename}</strong> con sus movimientos y su PDF?
            </p>
            <p className="confirm-note">
              El resumen, sus movimientos, su pago del período y los fragmentos de memoria se eliminan del equipo.
            </p>
          </div>
        </Modal>
      )}

      {reviewOpen && selected && (
        <ReviewModal
          statement={selected}
          fields={review.data?.fields ?? []}
          transactions={review.data?.transactions ?? []}
          onClose={() => setReviewOpen(false)}
          onConfirm={() => confirm(selected.id)}
          onSaved={() => {
            toast("Cambios guardados.");
            refresh();
          }}
          onError={(message) => toast(message, "error")}
          saving={busy === `confirm:${selected.id}`}
        />
      )}
    </>
  );
}

function DocumentDetail({
  statement,
  fields,
  busy,
  onOcr,
  onReview,
  onConfirm,
}: {
  statement: Statement;
  fields: StatementField[];
  busy: string | null;
  onOcr: () => void;
  onReview: () => void;
  onConfirm: () => void;
}): JSX.Element {
  const stages = ["imported", "ocr", "extracted", "review", "confirmed"];
  const currentIndex = Math.max(0, stages.indexOf(statement.status === "error" ? "review" : statement.status));
  const critical = fields.filter((field) => ["total", "minimum", "due_date", "close_date"].includes(field.field_key));

  return (
    <div className="document-detail-inner">
      <div className="detail-header">
        <div>
          <p className="eyebrow">{statement.status} · documento local</p>
          <h2>{statement.filename}</h2>
          <p>
            {statement.period ?? "sin período"} · {statement.pages} páginas
          </p>
        </div>
        <div className="detail-actions">
          <button type="button" className="secondary-button" onClick={onOcr} disabled={busy?.startsWith("ocr")}>
            <Icon name="scan" /> {busy?.startsWith("ocr") ? "Procesando…" : "Ejecutar OCR"}
          </button>
          <button type="button" className="primary-button" onClick={onReview}>
            <Icon name="eye" /> Revisar campos
          </button>
        </div>
      </div>

      <div className="extract-panel">
        {critical.length === 0 ? (
          <EmptyState icon="scan" title="Sin campos extraídos" body="Ejecutá el OCR para extraer los datos del resumen." />
        ) : (
          <div className="field-grid">
            {critical.map((field) => (
              <div className="detail-field" key={field.field_key}>
                <span>{FIELD_LABELS[field.field_key] ?? field.field_key}</span>
                <strong>
                  {field.value_type === "money" && field.field_value
                    ? formatCents(Math.round(Number(field.field_value) * 100))
                    : field.field_value ?? "—"}
                </strong>
                <em className={`confidence ${confidenceClass(field.confidence)}`}>
                  {field.confidence !== null ? `${Math.round(field.confidence * 100)}%` : "sin confianza"}
                </em>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="detail-stages">
        {stages.map((stage, index) => (
          <Fragment key={stage}>
            <span className={`stage ${index < currentIndex ? "done" : index === currentIndex ? "active" : ""}`}>
              <span className="stage-dot">{index <= currentIndex ? <Icon name="check" /> : index + 1}</span>
              {stage === "imported" ? "Importado" : stage === "ocr" ? "OCR" : stage === "extracted" ? "Extracción" : stage === "review" ? "Revisión" : "Confirmado"}
            </span>
            {index < stages.length - 1 && <i className={`stage-line ${index < currentIndex ? "done" : ""}`} />}
          </Fragment>
        ))}
      </div>

      {statement.status !== "confirmed" && (
        <div className="detail-footer">
          <button type="button" className="primary-button" onClick={onConfirm} disabled={busy?.startsWith("confirm")}>
            <Icon name="check" /> Confirmar resumen
          </button>
        </div>
      )}
    </div>
  );
}

function ReviewModal({
  statement,
  fields,
  transactions,
  onClose,
  onConfirm,
  onSaved,
  onError,
  saving,
}: {
  statement: Statement;
  fields: StatementField[];
  transactions: Transaction[];
  onClose: () => void;
  onConfirm: () => void;
  onSaved: () => void;
  onError: (message: string) => void;
  saving: boolean;
}): JSX.Element {
  const [draft, setDraft] = useState<Record<string, string>>(
    Object.fromEntries(fields.map((field) => [field.field_key, field.field_value ?? ""])),
  );
  const [rows, setRows] = useState(transactions);
  const [editingTx, setEditingTx] = useState<Transaction | null>(null);
  const [deletingTx, setDeletingTx] = useState<Transaction | null>(null);
  const { toast, refresh } = useApp();

  useEffect(() => {
    setRows(transactions);
  }, [transactions]);

  const save = async () => {
    try {
      const payload = Object.entries(draft).map(([fieldKey, value]) => ({
        fieldKey,
        // Las fechas se muestran y se editan como dd/mm/aaaa: se guardan en ISO.
        value: isDateField(fieldKey) ? (ddmmToIso(value) ?? value) : value,
      }));
      await api.patchFields(statement.id, payload);
      onSaved();
    } catch (error) {
      onError(error instanceof Error ? error.message : "No se pudo guardar");
    }
  };

  return (
    <Modal
      title={statement.filename}
      eyebrow="Revisión asistida · documento local"
      onClose={onClose}
      size="review"
      footer={
        <>
          <button type="button" className="secondary-button" onClick={save}>
            <Icon name="save" /> Guardar cambios
          </button>
          <button type="button" className="primary-button" onClick={onConfirm} disabled={saving}>
            <Icon name="check" /> {saving ? "Confirmando…" : "Confirmar resumen"}
          </button>
        </>
      }
    >
      <div className="review-content">
        <PdfViewer
          statement={statement}
          transactions={rows}
          onTransactions={setRows}
          onError={onError}
          onToast={toast}
        />

        <div className="extracted-fields">
          <div className="extract-heading">
            <div>
              <h3>Datos extraídos</h3>
              <p>Editá lo que haga falta y confirmá.</p>
            </div>
          </div>
          <div className="field-list">
            {fields.map((field) => (
              <label className="field-row" key={field.field_key}>
                <span>{FIELD_LABELS[field.field_key] ?? field.field_key}</span>
                {isDateField(field.field_key) ? (
                  <DateInput
                    value={ddmmToIso(draft[field.field_key] ?? "") ?? draft[field.field_key]}
                    onChange={(iso) => setDraft((current) => ({ ...current, [field.field_key]: isoToDdmm(iso) }))}
                    ariaLabel={FIELD_LABELS[field.field_key] ?? field.field_key}
                  />
                ) : FIELD_CHOICES[field.field_key] ? (
                  <Select
                    value={draft[field.field_key] ?? ""}
                    options={FIELD_CHOICES[field.field_key]}
                    onChange={(value) => setDraft((current) => ({ ...current, [field.field_key]: value }))}
                    ariaLabel={FIELD_LABELS[field.field_key] ?? field.field_key}
                  />
                ) : (
                  <input
                    value={draft[field.field_key] ?? ""}
                    onChange={(event) => setDraft((current) => ({ ...current, [field.field_key]: event.target.value }))}
                  />
                )}
                <em className={`confidence ${confidenceClass(field.confidence)}`}>
                  {field.confidence !== null ? `${Math.round(field.confidence * 100)}%` : "—"}
                </em>
                {field.evidence_text && (
                  <small className="field-evidence">
                    <Icon name="quote" /> {field.evidence_text}
                  </small>
                )}
              </label>
            ))}
          </div>

          <div className="extract-heading">
            <div>
              <h3>Movimientos del resumen ({rows.length})</h3>
              <p>Los que leyó la app, más los que marques en el PDF.</p>
            </div>
            <button type="button" className="ghost-button" onClick={refresh}>
              <Icon name="refresh" /> Recargar
            </button>
          </div>
          {rows.length === 0 ? (
            <EmptyState
              icon="scan"
              title="Sin movimientos"
              body="Ejecutá el OCR o marcá una zona del PDF para extraer un consumo."
            />
          ) : (
            <ul className="doc-movements">
              {[...rows]
                .sort((a, b) => b.occurred_on.localeCompare(a.occurred_on))
                .map((row) => (
                  <li key={row.id}>
                    <span className="doc-movement-date">{formatDate(row.occurred_on)}</span>
                    <span className="doc-movement-copy">
                      <strong>{row.description}</strong>
                      <small>
                        {KIND_LABELS[row.kind] ?? row.kind}
                        {row.currency === "USD" ? " · dólares" : ""}
                      </small>
                    </span>
                    <span className="doc-movement-amount">{formatCents(row.amount_cents, row.currency)}</span>
                    <RowMenu
                      label={`Acciones para ${row.description}`}
                      actions={[
                        { label: "Editar", icon: "pencil", onSelect: () => setEditingTx(row) },
                        { label: "Borrar", icon: "trash", danger: true, onSelect: () => setDeletingTx(row) },
                      ]}
                    />
                  </li>
                ))}
            </ul>
          )}

          <div className="source-note">
            <Icon name="quote" />
            <span>
              Página {fields[0]?.source_page ?? 1} · evidencia conservada del documento original.
            </span>
          </div>
        </div>
      </div>

      {editingTx && (
        <TransactionEditModal
          transaction={editingTx}
          onClose={() => setEditingTx(null)}
          onSaved={(updated) => {
            setRows((current) => current.map((row) => (row.id === updated.id ? updated : row)));
            setEditingTx(null);
            toast("Movimiento actualizado.");
            refresh();
          }}
          onError={onError}
        />
      )}

      {deletingTx && (
        <Modal
          title="Borrar movimiento"
          eyebrow="Documento local"
          size="compact"
          onClose={() => setDeletingTx(null)}
          footer={
            <>
              <button type="button" className="secondary-button" onClick={() => setDeletingTx(null)}>
                Cancelar
              </button>
              <button
                type="button"
                className="danger-button"
                onClick={() => {
                  void removeTransaction(deletingTx, setRows, () => setDeletingTx(null), toast, onError);
                }}
              >
                <Icon name="trash" /> Borrar
              </button>
            </>
          }
        >
          <div className="confirm-body">
            <p className="confirm-copy">
              ¿Borrar <strong>{deletingTx.description}</strong> por{" "}
              {formatCents(deletingTx.amount_cents, deletingTx.currency)}?
            </p>
            <p className="confirm-note">
              Si volvés a correr el OCR sobre este resumen, el movimiento puede aparecer de nuevo.
            </p>
          </div>
        </Modal>
      )}
    </Modal>
  );
}

async function removeTransaction(
  row: Transaction,
  setRows: (updater: (current: Transaction[]) => Transaction[]) => void,
  done: () => void,
  toast: (message: string, tone?: "info" | "error") => void,
  onError: (message: string) => void,
): Promise<void> {
  try {
    await api.deleteTransaction(row.id);
    setRows((current) => current.filter((item) => item.id !== row.id));
    done();
    toast("Movimiento borrado.");
  } catch (error) {
    onError(error instanceof Error ? error.message : "No se pudo borrar el movimiento");
  }
}

/** Edición de un movimiento leído del resumen. */
function TransactionEditModal({
  transaction,
  onClose,
  onSaved,
  onError,
}: {
  transaction: Transaction;
  onClose: () => void;
  onSaved: (updated: Transaction) => void;
  onError: (message: string) => void;
}): JSX.Element {
  const [description, setDescription] = useState(transaction.description);
  const [amount, setAmount] = useState(() => (transaction.amount_cents / 100).toFixed(2).replace(".", ","));
  const [occurredOn, setOccurredOn] = useState(transaction.occurred_on.slice(0, 10));
  const [currency, setCurrency] = useState(transaction.currency);
  const [kind, setKind] = useState(transaction.kind);
  const [saving, setSaving] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    const parsed = Number(amount.replace(/\./g, "").replace(",", "."));
    if (!Number.isFinite(parsed)) {
      onError("Ingresá un importe válido.");
      return;
    }
    setSaving(true);
    try {
      const result = await api.patchTransaction(transaction.id, {
        description: description.trim(),
        amountCents: Math.round(parsed * 100),
        occurredOn,
        kind,
      });
      onSaved({ ...transaction, ...result.transaction, currency });
    } catch (error) {
      onError(error instanceof Error ? error.message : "No se pudo guardar el movimiento");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title="Editar movimiento"
      eyebrow="Documento local"
      size="money"
      onClose={onClose}
      footer={
        <>
          <button type="button" className="secondary-button" onClick={onClose}>
            Cancelar
          </button>
          <button type="submit" form="edit-tx-form" className="primary-button" disabled={saving}>
            <Icon name="check" /> {saving ? "Guardando…" : "Guardar"}
          </button>
        </>
      }
    >
      <form id="edit-tx-form" className="money-form-grid" onSubmit={submit}>
        <label>
          <span>Descripción</span>
          <input type="text" value={description} onChange={(event) => setDescription(event.target.value)} required />
        </label>
        <label>
          <span>Importe</span>
          <input type="text" inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} />
        </label>
        <label>
          <span>Fecha</span>
          <DateInput value={occurredOn} onChange={setOccurredOn} />
        </label>
        <label>
          <span>Moneda</span>
          <Select
            value={currency}
            options={[
              { value: "ARS", label: "Pesos (AR$)" },
              { value: "USD", label: "Dólares (US$)" },
            ]}
            onChange={setCurrency}
            ariaLabel="Moneda"
          />
        </label>
        <label>
          <span>Tipo</span>
          <Select
            value={kind}
            options={Object.entries(KIND_LABELS).map(([value, label]) => ({ value, label }))}
            onChange={setKind}
            ariaLabel="Tipo de movimiento"
          />
        </label>
      </form>
    </Modal>
  );
}

const KIND_LABELS: Record<string, string> = {
  purchase: "Consumo",
  installment: "Cuota",
  subscription: "Suscripción",
  tax: "Impuesto / percepción",
  fee: "Comisión",
  payment: "Pago",
};

function isDateField(key: string): boolean {
  return key === "due_date" || key === "close_date";
}

interface PdfRegion {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

/** Visor del PDF importado con zonas leídas y marcado de consumos. */
function PdfViewer({
  statement,
  transactions,
  onTransactions,
  onError,
  onToast,
}: {
  statement: Statement;
  transactions: Transaction[];
  onTransactions: (rows: Transaction[]) => void;
  onError: (message: string) => void;
  onToast: (message: string, tone?: "info" | "error") => void;
}): JSX.Element {
  const [page, setPage] = useState(1);
  const [image, setImage] = useState<DocumentPageImage | null>(null);
  const [loading, setLoading] = useState(true);
  const [showRead, setShowRead] = useState(true);
  const [regions, setRegions] = useState<PdfRegion[]>([]);
  const [drag, setDrag] = useState<PdfRegion | null>(null);
  const [reading, setReading] = useState(false);
  const surfaceRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .documentPage(statement.id, page)
      .then((result) => {
        if (!cancelled) setImage(result);
      })
      .catch((error: unknown) => {
        if (!cancelled) onError(error instanceof Error ? error.message : "No se pudo abrir el PDF");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    setRegions([]);
    return () => {
      cancelled = true;
    };
  }, [statement.id, page, onError]);

  const pointFor = (event: React.PointerEvent): { x: number; y: number } | null => {
    const surface = surfaceRef.current;
    if (!surface) return null;
    const box = surface.getBoundingClientRect();
    if (box.width === 0 || box.height === 0) return null;
    return {
      x: Math.min(1, Math.max(0, (event.clientX - box.left) / box.width)),
      y: Math.min(1, Math.max(0, (event.clientY - box.top) / box.height)),
    };
  };

  const readRegions = async () => {
    if (regions.length === 0) return;
    setReading(true);
    try {
      const rects = regions.map((region) => [
        region.x0 * (image?.width ?? 1),
        region.y0 * (image?.height ?? 1),
        region.x1 * (image?.width ?? 1),
        region.y1 * (image?.height ?? 1),
      ]);
      const result = await api.extractRegions(statement.id, page, rects);
      onTransactions(result.transactions);
      onToast(
        result.transactions.length > 0
          ? `Zonas leídas: ${result.transactions.length} movimientos en el resumen.`
          : "No se detectaron consumos en las zonas marcadas.",
        result.transactions.length > 0 ? "info" : "error",
      );
      setRegions([]);
    } catch (error) {
      onError(error instanceof Error ? error.message : "No se pudieron leer las zonas");
    } finally {
      setReading(false);
    }
  };

  const highlights = showRead
    ? transactions
        .filter((row) => (row.source_page ?? 1) === page && row.source_bbox && row.source_bbox.length === 4)
        .map((row) => {
          const [x0, y0, x1, y1] = row.source_bbox as number[];
          const width = image?.width || 1;
          const height = image?.height || 1;
          return { x0: x0 / width, y0: y0 / height, x1: x1 / width, y1: y1 / height };
        })
    : [];

  const rectStyle = (region: PdfRegion): React.CSSProperties => ({
    left: `${region.x0 * 100}%`,
    top: `${region.y0 * 100}%`,
    width: `${Math.abs(region.x1 - region.x0) * 100}%`,
    height: `${Math.abs(region.y1 - region.y0) * 100}%`,
  });

  return (
    <div className="pdf-preview pdf-viewer">
      <div className="pdf-viewer-bar">
        <button
          type="button"
          className="round-button"
          aria-label="Página anterior"
          disabled={page <= 1}
          onClick={() => setPage((current) => Math.max(1, current - 1))}
        >
          <Icon name="chevron-left" />
        </button>
        <span>
          Página {page}
          {image?.pageCount ? ` de ${image.pageCount}` : ""}
        </span>
        <button
          type="button"
          className="round-button"
          aria-label="Página siguiente"
          disabled={Boolean(image?.pageCount) && page >= (image?.pageCount ?? 1)}
          onClick={() => setPage((current) => current + 1)}
        >
          <Icon name="chevron-right" />
        </button>
      </div>

      {loading ? (
        <LoadingBlock message="Abriendo el PDF…" />
      ) : image ? (
        <div className="pdf-surface">
          <div
            className="pdf-page"
            ref={surfaceRef}
            onPointerDown={(event) => {
              const point = pointFor(event);
              if (!point) return;
              (event.target as HTMLElement).setPointerCapture?.(event.pointerId);
              setDrag({ x0: point.x, y0: point.y, x1: point.x, y1: point.y });
            }}
            onPointerMove={(event) => {
              if (!drag) return;
              const point = pointFor(event);
              if (!point) return;
              setDrag({ ...drag, x1: point.x, y1: point.y });
            }}
            onPointerUp={() => {
              if (!drag) return;
              const width = Math.abs(drag.x1 - drag.x0);
              const height = Math.abs(drag.y1 - drag.y0);
              if (width > 0.02 && height > 0.008) {
                setRegions((current) => [
                  ...current,
                  {
                    x0: Math.min(drag.x0, drag.x1),
                    y0: Math.min(drag.y0, drag.y1),
                    x1: Math.max(drag.x0, drag.x1),
                    y1: Math.max(drag.y0, drag.y1),
                  },
                ]);
              }
              setDrag(null);
            }}
          >
            <img src={image.dataUrl} alt={`Página ${page} de ${statement.filename}`} draggable={false} />
            {highlights.map((region, index) => (
              <span key={`read-${index}`} className="pdf-highlight" style={rectStyle(region)} />
            ))}
            {regions.map((region, index) => (
              <span key={`mark-${index}`} className="pdf-mark" style={rectStyle(region)}>
                <button
                  type="button"
                  aria-label="Quitar marca"
                  onClick={(event) => {
                    event.stopPropagation();
                    setRegions((current) => current.filter((_, position) => position !== index));
                  }}
                >
                  <Icon name="close" />
                </button>
              </span>
            ))}
            {drag && <span className="pdf-mark drawing" style={rectStyle(drag)} />}
          </div>
        </div>
      ) : (
        <EmptyState icon="file" title="No pudimos mostrar el PDF" body="El archivo original puede no estar disponible." />
      )}

      <div className="pdf-viewer-actions">
        <button
          type="button"
          className="secondary-button"
          onClick={readRegions}
          disabled={regions.length === 0 || reading}
        >
          <Icon name="scan" /> {reading ? "Leyendo…" : `Leer zonas marcadas (${regions.length})`}
        </button>
        {regions.length > 0 && (
          <button type="button" className="ghost-button" onClick={() => setRegions([])}>
            <Icon name="close" /> Borrar marcas
          </button>
        )}
        <button
          type="button"
          className={`ghost-button ${showRead ? "active" : ""}`}
          aria-pressed={showRead}
          onClick={() => setShowRead((current) => !current)}
        >
          <Icon name="eye" /> Zonas leídas
        </button>
      </div>
      <p className="pdf-viewer-hint">
        Arrastrá sobre el resumen para marcar un consumo y después tocá «Leer zonas marcadas».
      </p>
      <div className="scan-caption">
        <span>
          <Icon name="file" /> PDF local
        </span>
        <span>
          <Icon name="lock" /> Solo en tu equipo
        </span>
      </div>
    </div>
  );
}
