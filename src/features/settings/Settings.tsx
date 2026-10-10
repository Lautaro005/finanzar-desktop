/** Configuración: privacidad, modelos, copiloto, metas y umbral de saldo. */

import { useState, type JSX } from "react";

import { Icon } from "../../components/Icon";
import { EmptyState, ErrorBlock, LoadingBlock, Panel, ProgressBar } from "../../components/ui";
import { api } from "../../lib/backend";
import { formatCents } from "../../lib/format";
import { useAsync } from "../../lib/hooks";
import { invoke, isTauri } from "../../lib/tauri";
import { Updates } from "../updates/Updates";
import { useApp } from "../../app/context";
import type { RuntimeStatus } from "../../types/api";

function humanBytes(bytes: number | null | undefined): string {
  if (!bytes) return "—";
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(0)} MB`;
  return `${(bytes / 1024).toFixed(0)} KB`;
}

export function Settings(): JSX.Element {
  const { toast, refresh, refreshKey } = useApp();
  const models = useAsync(() => api.models(), [refreshKey]);
  const goals = useAsync(() => api.goals(), [refreshKey]);
  const settings = useAsync(() => api.settings(), [refreshKey]);
  const [busy, setBusy] = useState<string | null>(null);
  const [threshold, setThreshold] = useState("");
  const [goalName, setGoalName] = useState("Fondo de emergencia");
  const [goalTarget, setGoalTarget] = useState("");
  const [goalSaved, setGoalSaved] = useState("");
  const [paths, setPaths] = useState<{ dataDir?: string; version?: string; target?: string } | null>(null);

  if (!paths) {
    void invoke<{ dataDir: string; target: string; version: string }>("app_paths").then((result) => {
      if (result) setPaths(result);
    });
  }

  const downloadModel = async (modelId: string) => {
    setBusy(modelId);
    try {
      await api.downloadModel(modelId);
      toast(`Descarga de ${modelId} iniciada.`);
      refresh();
    } catch (error) {
      toast(error instanceof Error ? error.message : "No se pudo descargar", "error");
    } finally {
      setBusy(null);
    }
  };

  const downloadRuntime = async () => {
    setBusy("runtime");
    try {
      const status = (await api.downloadRuntime()) as RuntimeStatus;
      toast(status.installed ? "Runtime de llama.cpp listo." : "Descarga del runtime iniciada.");
      refresh();
    } catch (error) {
      toast(error instanceof Error ? error.message : "No se pudo descargar el runtime", "error");
    } finally {
      setBusy(null);
    }
  };

  const startLlm = async () => {
    setBusy("llm");
    try {
      await api.startLlm();
      toast("Copiloto iniciado.");
      refresh();
    } catch (error) {
      toast(error instanceof Error ? error.message : "No se pudo iniciar el copiloto", "error");
    } finally {
      setBusy(null);
    }
  };

  const saveThreshold = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!threshold.trim()) return;
    try {
      const cents = Math.round(Number(threshold.replace(/\./g, "").replace(",", ".")) * 100);
      await api.patchSettings({ low_balance_threshold_cents: String(cents) });
      toast("Umbral de saldo actualizado.");
      refresh();
    } catch (error) {
      toast(error instanceof Error ? error.message : "No se pudo guardar", "error");
    }
  };

  const createGoal = async (event: React.FormEvent) => {
    event.preventDefault();
    try {
      await api.createGoal({ name: goalName, target: goalTarget || "0", savedCents: Math.round(Number(goalSaved || 0) * 100) });
      toast("Meta guardada.");
      setGoalTarget("");
      setGoalSaved("");
      refresh();
    } catch (error) {
      toast(error instanceof Error ? error.message : "No se pudo guardar la meta", "error");
    }
  };

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Privacidad y preferencias</p>
          <h1>Configuración.</h1>
          <p className="heading-copy">Decidís qué se guarda, cómo se interpreta y cuándo se sincroniza.</p>
        </div>
      </div>

      <div className="settings-grid">
        <Panel className="settings-card">
          <div className="settings-card-heading">
            <div className="settings-icon mint">
              <Icon name="lock" />
            </div>
            <div>
              <h2>Privacidad local</h2>
              <p>Ningún documento, movimiento o prompt sale de este equipo.</p>
            </div>
          </div>
          <div className="settings-lines">
            <div>
              <span>Procesamiento OCR</span>
              <strong>{models.data?.llmAvailable ? "Local" : "Local (OCR con GLM-OCR)"}</strong>
            </div>
            <div>
              <span>Backend</span>
              <strong>Solo 127.0.0.1</strong>
            </div>
            <div>
              <span>Sincronización en la nube</span>
              <strong>Desactivada</strong>
            </div>
            <div>
              <span>Directorio de datos</span>
              <strong className="mono">{paths?.dataDir ?? "—"}</strong>
            </div>
          </div>
        </Panel>

        <Panel className="settings-card">
          <div className="settings-card-heading">
            <div className="settings-icon blue">
              <Icon name="cpu" />
            </div>
            <div>
              <h2>Modelos locales</h2>
              <p>GLM-OCR para documentos y Spark para el copiloto.</p>
            </div>
          </div>
          {models.loading && !models.data ? (
            <LoadingBlock />
          ) : models.error ? (
            <ErrorBlock message={models.error} onRetry={models.reload} />
          ) : (
            <div className="stack-list">
              {(models.data?.models ?? []).map((model) => (
                <div className="list-row" key={`${model.id}:${model.quantization ?? ""}`}>
                  <div className="list-row-copy">
                    <strong>{model.name}</strong>
                    <small>
                      rev {model.revision.slice(0, 8)} · {humanBytes(model.sizeBytes || model.approxBytes)} ·{" "}
                      {model.license}
                    </small>
                    <ProgressBar value={model.verified ? 100 : model.installed ? 60 : 0} label={`Estado de ${model.name}`} />
                  </div>
                  {model.verified ? (
                    <span className="document-status confirmed">Verificado</span>
                  ) : (
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => downloadModel(model.id)}
                      disabled={busy === model.id}
                    >
                      <Icon name="download" /> {busy === model.id ? "Descargando…" : "Descargar"}
                    </button>
                  )}
                </div>
              ))}
              <div className="list-row">
                <div className="list-row-copy">
                  <strong>{models.data?.runtime.name ?? "llama.cpp"}</strong>
                  <small>
                    build {models.data?.runtime.build} · target {models.data?.runtime.target}
                  </small>
                </div>
                {models.data?.runtime.installed ? (
                  <span className="document-status confirmed">Listo</span>
                ) : (
                  <button type="button" className="secondary-button" onClick={downloadRuntime} disabled={busy === "runtime"}>
                    <Icon name="download" /> {busy === "runtime" ? "Descargando…" : "Instalar runtime"}
                  </button>
                )}
              </div>
              <div className="list-row">
                <div className="list-row-copy">
                  <strong>Copiloto</strong>
                  <small>{models.data?.llmAvailable ? "Servidor local activo" : "Iniciá el servidor para conversar"}</small>
                </div>
                <button type="button" className="secondary-button" onClick={startLlm} disabled={busy === "llm"}>
                  <Icon name="spark" /> {busy === "llm" ? "Iniciando…" : "Iniciar copiloto"}
                </button>
              </div>
            </div>
          )}
        </Panel>

        <Panel className="settings-card">
          <div className="settings-card-heading">
            <div className="settings-icon yellow">
              <Icon name="target" />
            </div>
            <div>
              <h2>Metas de ahorro</h2>
              <p>Fondo de emergencia y objetivos con porcentaje de avance.</p>
            </div>
          </div>
          {goals.data && goals.data.goals.length > 0 ? (
            <div className="stack-list">
              {goals.data.goals.map((goal) => {
                const progress = goal.target_cents > 0 ? (goal.saved_cents / goal.target_cents) * 100 : 0;
                return (
                  <div className="list-row" key={goal.id}>
                    <div className="list-row-copy">
                      <strong>{goal.name}</strong>
                      <small>
                        {formatCents(goal.saved_cents)} de {formatCents(goal.target_cents)}
                      </small>
                      <ProgressBar value={progress} label={`Avance de ${goal.name}`} />
                    </div>
                    <span className="document-status confirmed">{Math.round(progress)}%</span>
                  </div>
                );
              })}
            </div>
          ) : (
            <EmptyState icon="target" title="Sin metas configuradas" body="Creá una abajo para seguir su avance." />
          )}
          <form className="stack-form inline" onSubmit={createGoal}>
            <label>
              <span>Nombre</span>
              <input value={goalName} onChange={(event) => setGoalName(event.target.value)} required />
            </label>
            <label>
              <span>Objetivo</span>
              <input value={goalTarget} onChange={(event) => setGoalTarget(event.target.value)} inputMode="decimal" placeholder="2000000" />
            </label>
            <label>
              <span>Ahorrado</span>
              <input value={goalSaved} onChange={(event) => setGoalSaved(event.target.value)} inputMode="decimal" placeholder="0" />
            </label>
            <button type="submit" className="secondary-button">
              <Icon name="plus" /> Guardar meta
            </button>
          </form>
        </Panel>

        <Panel className="settings-card">
          <div className="settings-card-heading">
            <div className="settings-icon mint">
              <Icon name="alert" />
            </div>
            <div>
              <h2>Alerta de saldo bajo</h2>
              <p>Te avisamos cuando el saldo proyectado baja del umbral.</p>
            </div>
          </div>
          <form className="stack-form inline" onSubmit={saveThreshold}>
            <label>
              <span>Umbral</span>
              <input
                value={threshold}
                onChange={(event) => setThreshold(event.target.value)}
                inputMode="decimal"
                placeholder={settings.data?.settings.low_balance_threshold_cents ?? "20000000"}
              />
            </label>
            <button type="submit" className="secondary-button">
              <Icon name="save" /> Guardar umbral
            </button>
          </form>
          {!isTauri() && <p className="settings-note">Estás viendo la app en el navegador; algunas acciones requieren la ventana de escritorio.</p>}
        </Panel>
      </div>

      <div className="settings-divider" />
      <Updates />
    </>
  );
}
