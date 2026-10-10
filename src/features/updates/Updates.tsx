/** Actualizaciones: versión, comprobación, changelog e instalación con permiso. */

import { useEffect, useState, type JSX } from "react";

import { Icon } from "../../components/Icon";
import { ErrorBlock, LoadingBlock, Panel } from "../../components/ui";
import { api } from "../../lib/backend";
import { formatDate } from "../../lib/format";
import { useAsync } from "../../lib/hooks";
import { invoke, isTauri, listen } from "../../lib/tauri";
import { useApp } from "../../app/context";
import type { UpdateStatus } from "../../types/api";

export function Updates(): JSX.Element {
  const { toast, refreshKey } = useApp();
  const status = useAsync(() => api.updateStatus(), [refreshKey]);
  const [checking, setChecking] = useState(false);
  const [last, setLast] = useState<UpdateStatus | null>(null);
  const [polling, setPolling] = useState(true);

  useEffect(() => {
    const unlisten = listen<UpdateStatus>("update://status", (payload) => {
      setLast(payload);
      if (payload.available) toast(`Hay una versión nueva: ${payload.latestVersion ?? "disponible"}`);
    });
    return () => {
      void unlisten.then((off) => off());
    };
  }, [toast]);

  const current = last ?? status.data ?? null;

  const checkNow = async () => {
    setChecking(true);
    try {
      // En la ventana Tauri se usa el updater firmado; en el navegador, la API local.
      const viaTauri = await invoke<UpdateStatus>("check_update");
      const result = viaTauri ?? ((await api.updateCheck()) as UpdateStatus);
      setLast(result);
      if (result.available) {
        toast(`Versión ${result.latestVersion ?? ""} disponible. Requiere tu confirmación para instalar.`);
      } else if (result.error) {
        toast(`No se pudo comprobar: ${result.error}`, "error");
      } else {
        toast("Estás en la última versión.");
      }
    } catch (error) {
      toast(error instanceof Error ? error.message : "No se pudo comprobar", "error");
    } finally {
      setChecking(false);
    }
  };

  const install = async () => {
    if (!isTauri()) {
      toast("La instalación de actualizaciones requiere la app de escritorio.", "error");
      return;
    }
    const confirmed = window.confirm("¿Descargar e instalar la actualización? La app se reiniciará al finalizar.");
    if (!confirmed) return;
    try {
      const result = await invoke<{ installed: boolean; version: string }>("install_update", { confirmed: true });
      toast(`Actualización ${result?.version ?? ""} instalada.`);
    } catch (error) {
      toast(error instanceof Error ? error.message : "No se pudo instalar", "error");
    }
  };

  const togglePolling = async () => {
    if (polling) {
      await invoke("stop_update_polling");
      setPolling(false);
      toast("Comprobación automática desactivada.");
    } else {
      await invoke("start_update_polling");
      setPolling(true);
      toast("Comprobación automática cada 3 horas activada.");
    }
  };

  if (status.loading && !status.data) return <LoadingBlock message="Consultando versión y estado…" />;
  if (status.error) return <ErrorBlock message={status.error} onRetry={status.reload} />;

  return (
    <>
      <div className="section-heading">
        <div>
          <h2>Actualizaciones</h2>
          <p>La app comprueba versiones cada 3 horas y nunca instala sin tu permiso.</p>
        </div>
        <button type="button" className="secondary-button" onClick={checkNow} disabled={checking}>
          <Icon name="refresh" /> {checking ? "Comprobando…" : "Comprobar ahora"}
        </button>
      </div>

      <div className="settings-grid">
        <Panel className="settings-card">
          <div className="settings-card-heading">
            <div className="settings-icon blue">
              <Icon name="download" />
            </div>
            <div>
              <h2>Versión</h2>
              <p>Estado actual y última comprobación.</p>
            </div>
          </div>
          <div className="settings-lines">
            <div>
              <span>Versión actual</span>
              <strong>{current?.currentVersion ?? "—"}</strong>
            </div>
            <div>
              <span>Última comprobación</span>
              <strong>{current?.checkedAt ? formatDate(current.checkedAt.slice(0, 10)) : "nunca"}</strong>
            </div>
            <div>
              <span>Target</span>
              <strong>{current?.target ?? "—"}</strong>
            </div>
            <div>
              <span>Estado</span>
              <strong>
                {current?.offline
                  ? "Sin conexión (último estado conocido)"
                  : current?.available
                    ? `Nueva versión ${current.latestVersion}`
                    : "Al día"}
              </strong>
            </div>
          </div>
        </Panel>

        <Panel className="settings-card">
          <div className="settings-card-heading">
            <div className="settings-icon mint">
              <Icon name="shield" />
            </div>
            <div>
              <h2>Seguridad</h2>
              <p>Firma verificada, compatibilidad y rollback.</p>
            </div>
          </div>
          <div className="settings-lines">
            <div>
              <span>Comprobación automática</span>
              <button type="button" className={`toggle ${polling ? "on" : ""}`} onClick={togglePolling} aria-label="Alternar comprobación automática">
                <i />
              </button>
            </div>
            <div>
              <span>Instalación</span>
              <strong>Requiere tu confirmación</strong>
            </div>
            <div>
              <span>Rollback</span>
              <strong>Se conserva la versión anterior</strong>
            </div>
          </div>
        </Panel>
      </div>

      {current?.notes && (
        <Panel title="Novedades" subtitle="Changelog de la versión disponible.">
          <pre className="changelog">{current.notes}</pre>
          <div className="detail-footer">
            <button type="button" className="primary-button" onClick={install} disabled={!current.available}>
              <Icon name="download" /> Descargar e instalar con confirmación
            </button>
          </div>
        </Panel>
      )}
    </>
  );
}
