/** Documentos: importar PDF, ejecutar OCR, revisar y confirmar. */

import { useCallback, useMemo, useState, type JSX } from "react";

import { Icon } from "../../components/Icon";
import { EmptyState, ErrorBlock, LoadingBlock, Modal, Panel, StatusPill } from "../../components/ui";
import { api } from "../../lib/backend";
import { formatCents, formatDate } from "../../lib/format";
import { useAsync } from "../../lib/hooks";
import { pickPdf } from "../../lib/tauri";
import { useApp } from "../../app/context";
import type { Statement, StatementField } from "../../types/api";

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
                <button
                  key={doc.id}
                  type="button"
                  className={`document-item ${selected?.id === doc.id ? "active" : ""}`}
                  onClick={() => setSelectedId(doc.id)}
                >
                  <span className="doc-type">PDF</span>
                  <span className="doc-copy">
                    <strong>{doc.filename}</strong>
                    <small>
                      {formatDate(doc.imported_at.slice(0, 10))} · {doc.pages} pág.
                    </small>
                  </span>
                  <StatusPill status={doc.status} />
                </button>
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

      {reviewOpen && selected && (
        <ReviewModal
          statement={selected}
          fields={review.data?.fields ?? []}
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
          <span key={stage} className="stage-wrapper">
            <span className={`stage ${index < currentIndex ? "done" : index === currentIndex ? "active" : ""}`}>
              <span className="stage-dot">{index <= currentIndex ? <Icon name="check" /> : index + 1}</span>
              {stage === "imported" ? "Importado" : stage === "ocr" ? "OCR" : stage === "extracted" ? "Extracción" : stage === "review" ? "Revisión" : "Confirmado"}
            </span>
            {index < stages.length - 1 && <i className={`stage-line ${index < currentIndex ? "done" : ""}`} />}
          </span>
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
  onClose,
  onConfirm,
  onSaved,
  onError,
  saving,
}: {
  statement: Statement;
  fields: StatementField[];
  onClose: () => void;
  onConfirm: () => void;
  onSaved: () => void;
  onError: (message: string) => void;
  saving: boolean;
}): JSX.Element {
  const [draft, setDraft] = useState<Record<string, string>>(
    Object.fromEntries(fields.map((field) => [field.field_key, field.field_value ?? ""])),
  );

  const save = async () => {
    try {
      const payload = Object.entries(draft).map(([fieldKey, value]) => ({ fieldKey, value }));
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
        <div className="pdf-preview">
          <div className="pdf-top">
            <span className="pdf-logo">{statement.filename.slice(0, 12).toUpperCase()}</span>
            <span>Resumen de cuenta</span>
          </div>
          <div className="pdf-line long" />
          <div className="pdf-line medium" />
          <div className="pdf-total">
            <span>Total a pagar</span>
            <strong>
              {statement.total_cents !== null ? formatCents(statement.total_cents) : "a confirmar"}
            </strong>
          </div>
          <div className="pdf-line short" />
          <div className="pdf-line long" />
          <div className="pdf-stamp">
            {statement.currency}
            <br />
            {statement.period ?? ""}
          </div>
          <div className="scan-caption">
            <span>
              <Icon name="file" /> PDF local
            </span>
            <span>
              <Icon name="lock" /> Solo en tu equipo
            </span>
          </div>
        </div>

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
                <input
                  value={draft[field.field_key] ?? ""}
                  onChange={(event) => setDraft((current) => ({ ...current, [field.field_key]: event.target.value }))}
                />
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
          <div className="source-note">
            <Icon name="quote" />
            <span>
              Página {fields[0]?.source_page ?? 1} · evidencia conservada del documento original.
            </span>
          </div>
        </div>
      </div>
    </Modal>
  );
}
