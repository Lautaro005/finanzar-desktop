/** Asistente de primer arranque.

Pasos: nombre → modelos (Spark obligatorio, OCR a elección, embeddings
opcionales) → cuenta → ingreso o sueldo → primer resumen (opcional). No
descarga nada solo: cada modelo se baja cuando la persona lo pide, con barra de
progreso.
*/

import { useCallback, useEffect, useMemo, useState, type JSX } from "react";

import { Icon } from "../../components/Icon";
import { Select } from "../../components/Select";
import { ProgressBar } from "../../components/ui";
import { api } from "../../lib/backend";
import { formatCents } from "../../lib/format";
import { pickPdf } from "../../lib/tauri";
import { useApp } from "../../app/context";
import type { Account, ModelStatus, RuntimeStatus } from "../../types/api";

type Step = "name" | "models" | "account" | "income" | "document";
type ProgressKey = "runtime" | "spark" | "glm" | "gemma";

const STEPS: Array<{ id: Step; label: string }> = [
  { id: "name", label: "Tu nombre" },
  { id: "models", label: "Modelos" },
  { id: "account", label: "Cuentas" },
  { id: "income", label: "Ingresos" },
  { id: "document", label: "Primer resumen" },
];

interface Progress {
  label: string;
  value: number;
  message: string;
}

/** Porcentaje legible de una descarga en curso. */
function percentOf(state: Progress): string {
  const percent = Math.round(Math.min(1, Math.max(0, state.value)) * 100);
  return state.value <= 0 ? "…" : `${percent}%`;
}

/** Barra de progreso de una descarga, con porcentaje visible. */
function DownloadProgress({ state }: { state?: Progress }): JSX.Element | null {
  if (!state) return null;
  const percent = Math.round(Math.min(1, Math.max(0, state.value)) * 100);
  const unknown = state.value <= 0;
  return (
    <div className="model-progress" role="status" aria-live="polite">
      <div className="model-progress-head">
        <strong>{state.message || "Descargando…"}</strong>
        <span>{unknown ? "calculando…" : `${percent}%`}</span>
      </div>
      <ProgressBar
        value={percent}
        indeterminate={unknown}
        label={`Progreso de la descarga de ${state.label}`}
      />
    </div>
  );
}

export function Onboarding(): JSX.Element | null {
  const { backendReady, onboardingDone, setOnboardingDone, setUserName, toast, refresh } = useApp();
  const [step, setStep] = useState<Step>("name");
  const [name, setName] = useState("");
  const [models, setModels] = useState<ModelStatus[]>([]);
  const [runtime, setRuntime] = useState<RuntimeStatus | null>(null);
  const [progress, setProgress] = useState<Partial<Record<ProgressKey, Progress>>>({});
  const [ocrChoice, setOcrChoice] = useState<"layout" | "glm">("layout");
  const [withEmbeddings, setWithEmbeddings] = useState(false);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [accountName, setAccountName] = useState("Cuenta sueldo");
  const [accountCurrency, setAccountCurrency] = useState("ARS");
  const [accountOpening, setAccountOpening] = useState("");
  const [incomeAmount, setIncomeAmount] = useState("");
  const [incomeAccount, setIncomeAccount] = useState("");
  const [incomeDay, setIncomeDay] = useState(1);
  const [incomeRecurring, setIncomeRecurring] = useState(true);
  const [busy, setBusy] = useState(false);
  const [imported, setImported] = useState<string | null>(null);

  const spark = useMemo(() => models.find((model) => model.id === "spark-x2.5-1.7b"), [models]);
  const glm = useMemo(() => models.find((model) => model.id === "glm-ocr"), [models]);
  const gemma = useMemo(() => models.find((model) => model.id === "embeddinggemma-2"), [models]);

  const loadModels = useCallback(async () => {
    try {
      const data = await api.models();
      setModels(data.models);
      setRuntime(data.runtime);
    } catch {
      /* el backend puede estar arrancando */
    }
  }, []);

  useEffect(() => {
    if (!backendReady || onboardingDone) return;
    void loadModels();
    window.setTimeout(() => void loadModels(), 1500);
  }, [backendReady, onboardingDone, loadModels]);

  useEffect(() => {
    if (!incomeAccount && accounts.length > 0) setIncomeAccount(accounts[0].id);
  }, [accounts, incomeAccount]);

  /** Espera a que un modelo o el runtime queden instalados, mostrando progreso. */
  const waitForInstall = useCallback(
    async (key: ProgressKey, label: string, done: () => Promise<boolean>, jobKind: string) => {
      const started = Date.now();
      setProgress((current) => ({ ...current, [key]: { label, value: 0, message: "Preparando la descarga…" } }));
      for (;;) {
        await new Promise((resolve) => window.setTimeout(resolve, 700));
        try {
          const jobs = await api.jobs(jobKind);
          const running = jobs.jobs.find((job) => job.status === "running") ?? jobs.jobs[0];
          if (running) {
            setProgress((current) => ({
              ...current,
              [key]: { label, value: running.progress, message: running.message || "Descargando…" },
            }));
            if (running.status === "error") throw new Error(running.error ?? running.message);
          }
        } catch (error) {
          if (error instanceof Error && error.message && !error.message.includes("backend")) throw error;
        }
        if (await done()) {
          setProgress((current) => ({ ...current, [key]: { label, value: 1, message: "Listo" } }));
          return;
        }
        if (Date.now() - started > 20 * 60 * 1000) throw new Error("La descarga tardó demasiado.");
      }
    },
    [],
  );

  const installRuntime = async () => {
    setBusy(true);
    try {
      await api.downloadRuntime();
      await waitForInstall(
        "runtime",
        "llama.cpp",
        async () => {
          const data = await api.models();
          setRuntime(data.runtime);
          return data.runtime.installed;
        },
        "runtime_download",
      );
      toast("Runtime de llama.cpp listo.");
    } catch (error) {
      toast(error instanceof Error ? error.message : "No se pudo instalar llama.cpp", "error");
    } finally {
      setBusy(false);
      setProgress((current) => ({ ...current, runtime: undefined }));
      void loadModels();
    }
  };

  const installModel = async (modelId: string, key: ProgressKey, label: string) => {
    setBusy(true);
    try {
      await api.downloadModel(modelId);
      await waitForInstall(
        key,
        label,
        async () => {
          const data = await api.models();
          setModels(data.models);
          return Boolean(data.models.find((model) => model.id === modelId)?.installed);
        },
        "model_download",
      );
      toast(`${label} descargado.`);
    } catch (error) {
      toast(error instanceof Error ? error.message : `No se pudo descargar ${label}`, "error");
    } finally {
      setBusy(false);
      setProgress((current) => ({ ...current, [key]: undefined }));
      void loadModels();
    }
  };

  const createAccount = async () => {
    if (!accountName.trim()) {
      toast("Poné un nombre para la cuenta.", "error");
      return;
    }
    setBusy(true);
    try {
      const created = await api.createAccount({
        name: accountName.trim(),
        kind: "bank",
        currency: accountCurrency,
        openingBalance: accountOpening || "0",
      });
      setAccounts((current) => [...current, created.account]);
      setIncomeAccount(created.account.id);
      setAccountOpening("");
      toast(`Cuenta «${created.account.name}» creada.`);
      refresh();
    } catch (error) {
      toast(error instanceof Error ? error.message : "No se pudo crear la cuenta", "error");
    } finally {
      setBusy(false);
    }
  };

  const saveIncome = async () => {
    if (!incomeAmount.trim() || !incomeAccount) {
      setStep("document");
      return;
    }
    setBusy(true);
    try {
      const parsed = Number(incomeAmount.replace(/\./g, "").replace(",", "."));
      const cents = Number.isFinite(parsed) ? Math.round(parsed * 100) : 0;
      if (cents <= 0) throw new Error("Ingresá un importe válido.");
      if (incomeRecurring) {
        await api.createRecurring({
          name: "Sueldo",
          source: "Sueldo",
          kind: "salary",
          amountCents: cents,
          accountId: incomeAccount,
          dayOfMonth: incomeDay,
          startDate: `${new Date().toISOString().slice(0, 7)}-01`,
          active: true,
        });
      } else {
        await api.createIncome({
          amountCents: cents,
          source: "Ingreso",
          kind: "punctual",
          accountId: incomeAccount,
          occurredOn: new Date().toISOString().slice(0, 10),
        });
      }
      toast(`Ingreso guardado: ${formatCents(cents)}.`);
      refresh();
      setStep("document");
    } catch (error) {
      toast(error instanceof Error ? error.message : "No se pudo guardar el ingreso", "error");
    } finally {
      setBusy(false);
    }
  };

  const importStatement = async () => {
    const path = await pickPdf();
    if (!path) return;
    setBusy(true);
    try {
      const result = await api.importDocument(path);
      setImported(result.document.filename);
      toast("Resumen importado. Ejecutá el OCR desde Documentos.");
      refresh();
    } catch (error) {
      toast(error instanceof Error ? error.message : "No se pudo importar el resumen", "error");
    } finally {
      setBusy(false);
    }
  };

  const finish = async () => {
    setBusy(true);
    try {
      await api.patchSettings({
        user_name: name.trim(),
        onboarding_done: "true",
        ocr_preference: ocrChoice === "glm" ? "glm-ocr" : "layout",
      });
      if (withEmbeddings && gemma?.installed) {
        try {
          await api.startEmbeddings();
        } catch {
          /* los embeddings son opcionales */
        }
      }
      setUserName(name.trim());
      setOnboardingDone(true);
      toast(`¡Listo${name.trim() ? `, ${name.trim()}` : ""}! Ya podés cargar tu primer resumen.`);
      refresh();
    } catch (error) {
      toast(error instanceof Error ? error.message : "No se pudo guardar el asistente", "error");
    } finally {
      setBusy(false);
    }
  };

  const skipStep = () => {
    if (step === "account") setStep("income");
    else if (step === "income") setStep("document");
    else void finish();
  };

  if (!backendReady || onboardingDone) return null;

  const stepIndex = Math.max(0, STEPS.findIndex((item) => item.id === step));
  const sparkReady = Boolean(spark?.installed);
  const runtimeReady = Boolean(runtime?.installed);
  const modelsBlocked = !sparkReady || !runtimeReady;

  return (
    <div className="onboarding-overlay" role="dialog" aria-modal="true" aria-label="Primeros pasos">
      <div className="onboarding-card">
        <header className="onboarding-header">
          <div>
            <p className="eyebrow">Primeros pasos · todo local</p>
            <h1>Bienvenido a FinanzAR</h1>
            <p>En cuatro pasos dejamos la app lista. Nada sale de este equipo.</p>
          </div>
          <ol className="onboarding-steps">
            {STEPS.map((item, index) => (
              <li
                key={item.id}
                className={index < stepIndex ? "done" : index === stepIndex ? "active" : ""}
                aria-current={index === stepIndex ? "step" : undefined}
              >
                <span>{index + 1}</span>
                {item.label}
              </li>
            ))}
          </ol>
        </header>

        <div className="onboarding-body">
          {step === "name" && (
            <section className="onboarding-section">
              <h2>¿Cómo te llamás?</h2>
              <p>El copiloto te va a hablar por tu nombre y el sidebar lo muestra en lugar de «Perfil local».</p>
              <label className="onboarding-field">
                <span>Nombre</span>
                <input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="Lautaro"
                  autoFocus
                />
              </label>
            </section>
          )}

          {step === "models" && (
            <section className="onboarding-section">
              <h2>Los modelos que corren en tu equipo</h2>
              <p>
                Spark es el copiloto y es obligatorio. Para leer los resúmenes podés usar la lectura rápida por
                columnas (sin descargar nada) o GLM-OCR. EmbeddingGemma es opcional: mejora la memoria del copiloto.
              </p>

              <article className={`model-card ${sparkReady && runtimeReady ? "ready" : ""}`}>
                <div>
                  <strong>Spark-X2.5-1.7B</strong>
                  <small>Copiloto local · obligatorio</small>
                </div>
                {sparkReady && runtimeReady ? (
                  <span className="document-status confirmed">Listo</span>
                ) : (
                  <div className="model-actions">
                    {!runtimeReady && (
                      <button type="button" className="secondary-button" onClick={installRuntime} disabled={busy}>
                        <Icon name="download" />
                        {progress.runtime ? `Instalando llama.cpp… ${percentOf(progress.runtime)}` : "Instalar llama.cpp"}
                      </button>
                    )}
                    <button
                      type="button"
                      className="primary-button"
                      onClick={() => installModel("spark-x2.5-1.7b", "spark", "Spark")}
                      disabled={busy || !runtimeReady}
                    >
                      <Icon name="download" />
                      {progress.spark ? `Descargando Spark… ${percentOf(progress.spark)}` : "Descargar Spark"}
                    </button>
                  </div>
                )}
                <DownloadProgress state={progress.runtime ?? progress.spark} />
              </article>

              <article className="model-card">
                <div>
                  <strong>Lectura de resúmenes</strong>
                  <small>Elegí cómo extraer los datos del PDF</small>
                </div>
                <Select
                  value={ocrChoice}
                  options={[
                    { value: "layout", label: "Rápida por columnas (sin descargas)" },
                    { value: "glm", label: "GLM-OCR (2,6 GB, escaneos)" },
                  ]}
                  onChange={(next) => setOcrChoice(next as typeof ocrChoice)}
                  ariaLabel="Motor de extracción"
                />
              </article>
              {ocrChoice === "glm" && (
                <article className={`model-card ${glm?.installed ? "ready" : ""}`}>
                  <div>
                    <strong>GLM-OCR</strong>
                    <small>Lee resúmenes escaneados o sin capa de texto</small>
                  </div>
                  {glm?.installed ? (
                    <span className="document-status confirmed">Listo</span>
                  ) : (
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => installModel("glm-ocr", "glm", "GLM-OCR")}
                      disabled={busy}
                    >
                      <Icon name="download" />
                      {progress.glm ? `Descargando GLM-OCR… ${percentOf(progress.glm)}` : "Descargar GLM-OCR"}
                    </button>
                  )}
                  <DownloadProgress state={progress.glm} />
                </article>
              )}

              <article className={`model-card ${gemma?.installed ? "ready" : ""}`}>
                <div>
                  <strong>EmbeddingGemma-2</strong>
                  <small>Memoria del copiloto con búsqueda por significado · opcional (300 MB)</small>
                </div>
                {gemma?.installed ? (
                  <span className="document-status confirmed">Listo</span>
                ) : (
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => installModel("embeddinggemma-2", "gemma", "EmbeddingGemma")}
                    disabled={busy}
                  >
                    <Icon name="download" />
                    {progress.gemma
                      ? `Descargando EmbeddingGemma… ${percentOf(progress.gemma)}`
                      : "Descargar EmbeddingGemma"}
                  </button>
                )}
                <DownloadProgress state={progress.gemma} />
              </article>

              <label className="money-check">
                <input
                  type="checkbox"
                  checked={withEmbeddings}
                  onChange={(event) => setWithEmbeddings(event.target.checked)}
                />
                <span>
                  <strong>Activar los embeddings al terminar</strong>
                  <small>Se usa cuando el modelo está descargado; sin él la memoria sigue funcionando.</small>
                </span>
              </label>
            </section>
          )}

          {step === "account" && (
            <section className="onboarding-section">
              <h2>¿Dónde tenés la plata?</h2>
              <p>Cargá al menos una cuenta: los ingresos se acreditan ahí y el balance deja de estar en cero.</p>
              <div className="onboarding-grid">
                <label className="onboarding-field">
                  <span>Nombre</span>
                  <input value={accountName} onChange={(event) => setAccountName(event.target.value)} />
                </label>
                <label className="onboarding-field">
                  <span>Moneda</span>
                  <Select
                    value={accountCurrency}
                    options={[
                      { value: "ARS", label: "Pesos (AR$)" },
                      { value: "USD", label: "Dólares (US$)" },
                    ]}
                    onChange={setAccountCurrency}
                    ariaLabel="Moneda de la cuenta"
                  />
                </label>
                <label className="onboarding-field">
                  <span>Saldo inicial</span>
                  <input
                    value={accountOpening}
                    onChange={(event) => setAccountOpening(event.target.value)}
                    placeholder="0"
                    inputMode="decimal"
                  />
                </label>
              </div>
              <button type="button" className="secondary-button" onClick={createAccount} disabled={busy}>
                <Icon name="plus" /> Agregar cuenta
              </button>
              {accounts.length > 0 && (
                <ul className="onboarding-list">
                  {accounts.map((account) => (
                    <li key={account.id}>
                      <Icon name="check" /> {account.name} · {account.currency === "USD" ? "US$" : "AR$"}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}

          {step === "income" && (
            <section className="onboarding-section">
              <h2>Sueldo o ingreso</h2>
              <p>Si cargás tu sueldo, se acredita solo cada mes en la cuenta que elijas. Después lo podés cambiar.</p>
              {accounts.length === 0 ? (
                <div className="form-notice" role="alert">
                  <Icon name="wallet" />
                  <div>
                    <strong>Sin cuentas todavía</strong>
                    <span>Volvé un paso y agregá una cuenta para que el ingreso tenga dónde acreditarse.</span>
                  </div>
                </div>
              ) : (
                <div className="onboarding-grid">
                  <label className="onboarding-field">
                    <span>Importe</span>
                    <input
                      value={incomeAmount}
                      onChange={(event) => setIncomeAmount(event.target.value)}
                      placeholder="950000"
                      inputMode="decimal"
                    />
                  </label>
                  <label className="onboarding-field">
                    <span>Cuenta</span>
                    <Select
                      value={incomeAccount}
                      options={accounts.map((account) => ({ value: account.id, label: account.name }))}
                      onChange={setIncomeAccount}
                      ariaLabel="Cuenta del ingreso"
                    />
                  </label>
                  <label className="onboarding-field">
                    <span>Día del mes</span>
                    <input
                      type="number"
                      min={1}
                      max={31}
                      value={incomeDay}
                      onChange={(event) => setIncomeDay(Number(event.target.value))}
                    />
                  </label>
                </div>
              )}
              <label className="money-check">
                <input
                  type="checkbox"
                  checked={incomeRecurring}
                  onChange={(event) => setIncomeRecurring(event.target.checked)}
                />
                <span>
                  <strong>Es mi sueldo (se repite cada mes)</strong>
                  <small>Si lo desmarcás, se registra como un ingreso puntual de este mes.</small>
                </span>
              </label>
            </section>
          )}

          {step === "document" && (
            <section className="onboarding-section">
              <h2>¿Querés cargar un resumen?</h2>
              <p>Es opcional. Podés importar el PDF de la tarjeta y la app lo lee en tu equipo.</p>
              <div className="onboarding-actions">
                <button type="button" className="secondary-button" onClick={importStatement} disabled={busy}>
                  <Icon name="scan" /> {busy ? "Importando…" : "Elegir un PDF"}
                </button>
                {imported && (
                  <span className="document-status confirmed">
                    <Icon name="check" /> {imported}
                  </span>
                )}
              </div>
              <p className="settings-note">
                El OCR y la extracción corren cuando lo pidas desde Documentos; nada se sube a internet.
              </p>
            </section>
          )}
        </div>

        <footer className="onboarding-footer">
          <button
            type="button"
            className="ghost-button"
            onClick={() => setStep(STEPS[Math.max(0, stepIndex - 1)].id)}
            disabled={stepIndex === 0 || busy}
          >
            Atrás
          </button>
          <div className="onboarding-footer-right">
            {(step === "account" || step === "income" || step === "document") && (
              <button type="button" className="secondary-button" onClick={skipStep} disabled={busy}>
                Omitir
              </button>
            )}
            {step === "name" && (
              <button
                type="button"
                className="primary-button"
                onClick={() => setStep("models")}
                disabled={!name.trim()}
              >
                Continuar <Icon name="arrow" />
              </button>
            )}
            {step === "models" && (
              <button
                type="button"
                className="primary-button"
                onClick={() => setStep("account")}
                disabled={modelsBlocked || busy}
                title={modelsBlocked ? "Spark y llama.cpp son obligatorios" : undefined}
              >
                Continuar <Icon name="arrow" />
              </button>
            )}
            {(step === "account" || step === "income") && (
              <button
                type="button"
                className="primary-button"
                onClick={() => (step === "account" ? setStep("income") : void saveIncome())}
                disabled={busy}
              >
                Continuar <Icon name="arrow" />
              </button>
            )}
            {step === "document" && (
              <button type="button" className="primary-button" onClick={finish} disabled={busy}>
                <Icon name="check" /> Terminar
              </button>
            )}
          </div>
        </footer>
      </div>
    </div>
  );
}
