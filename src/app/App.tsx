/** Shell de la aplicación: sidebar, topbar, ruteo y overlays. */

import { useEffect, type JSX } from "react";

import { BrandLockup, BrandMark } from "../components/Brand";
import { Icon } from "../components/Icon";
import { ToastStack } from "../components/ui";
import { api } from "../lib/backend";
import { formatDate } from "../lib/format";
import { listen } from "../lib/tauri";
import { Accounts } from "../features/accounts/Accounts";
import { CalendarScreen } from "../features/calendar/CalendarScreen";
import { CopilotDrawer } from "../features/copilot/CopilotDrawer";
import { Dashboard } from "../features/dashboard/Dashboard";
import { Documents } from "../features/documents/Documents";
import { Income } from "../features/income/Income";
import { MoneyModal } from "../features/income/MoneyModal";
import { Settings } from "../features/settings/Settings";
import { Spreadsheet } from "../features/spreadsheet/Spreadsheet";
import { Transactions } from "../features/transactions/Transactions";
import { Updates } from "../features/updates/Updates";
import { AppProvider, useApp, type Route } from "./context";

const NAV: Array<{ route: Route; label: string; icon: string }> = [
  { route: "dashboard", label: "Dashboard", icon: "grid" },
  { route: "accounts", label: "Cuentas", icon: "wallet" },
  { route: "income", label: "Ingresos", icon: "arrow-down" },
  { route: "documents", label: "Documentos", icon: "file" },
  { route: "calendar", label: "Calendario", icon: "calendar" },
  { route: "movements", label: "Movimientos", icon: "receipt" },
  { route: "spreadsheet", label: "Datos", icon: "table" },
  { route: "settings", label: "Configuración", icon: "sliders" },
  { route: "updates", label: "Actualizaciones", icon: "download" },
];

const TITLES: Record<Route, string> = {
  dashboard: "Dashboard",
  accounts: "Cuentas",
  income: "Ingresos",
  documents: "Documentos",
  calendar: "Calendario",
  movements: "Movimientos",
  spreadsheet: "Datos",
  settings: "Configuración",
  updates: "Actualizaciones",
};

function BackendGate(): JSX.Element | null {
  const { backendReady, setBackendReady, setBackendBase, toast } = useApp();

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        const health = await api.health();
        if (!cancelled && health.status === "ok") {
          setBackendReady(true);
        }
      } catch {
        /* el backend todavía no responde */
      }
    };
    void check();
    const timer = window.setInterval(() => {
      if (!cancelled) void check();
    }, 1500);
    const unlistenPromise = listen<{ ready: boolean; baseUrl: string }>("backend://ready", (payload) => {
      if (payload.ready) {
        setBackendBase(payload.baseUrl);
        setBackendReady(true);
      }
    });
    const errorUnlisten = listen<{ message: string }>("backend://error", (payload) => {
      toast(payload.message, "error");
    });
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      void unlistenPromise.then((unlisten) => unlisten());
      void errorUnlisten.then((unlisten) => unlisten());
    };
  }, [setBackendBase, setBackendReady, toast]);

  if (backendReady) return null;
  return (
    <div className="bootstrap-overlay" role="status" aria-live="polite">
      <div className="bootstrap-card">
        <BrandMark className="bootstrap-mark" />
        <h1>FinanzAR Desktop</h1>
        <p>Preparando el entorno local y el backend en 127.0.0.1…</p>
        <div className="progress-track">
          <i className="indeterminate" />
        </div>
        <small>Todo el procesamiento ocurre en tu equipo. No se envía nada a la nube.</small>
      </div>
    </div>
  );
}

function Shell(): JSX.Element {
  const { route, setRoute, chatOpen, setChatOpen, moneyIntent, closeMoney, toasts, dismissToast } = useApp();

  const renderRoute = (): JSX.Element => {
    switch (route) {
      case "accounts":
        return <Accounts />;
      case "income":
        return <Income />;
      case "documents":
        return <Documents />;
      case "calendar":
        return <CalendarScreen />;
      case "movements":
        return <Transactions />;
      case "spreadsheet":
        return <Spreadsheet />;
      case "settings":
        return <Settings />;
      case "updates":
        return <Updates />;
      case "dashboard":
      default:
        return <Dashboard />;
    }
  };

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Navegación principal">
        <BrandLockup />
        <div className="demo-banner">
          <span className="status-dot" />
          <div>
            <strong>Local y privado</strong>
            <small>Datos en tu dispositivo</small>
          </div>
        </div>
        <nav className="nav-list" aria-label="Secciones">
          {NAV.map((item, index) => (
            <button
              key={item.route}
              type="button"
              className={`nav-item ${route === item.route ? "active" : ""}`}
              onClick={() => setRoute(item.route)}
              aria-current={route === item.route ? "page" : undefined}
            >
              <span className="nav-icon">
                <Icon name={item.icon} />
              </span>
              <span>{item.label}</span>
              {index < 2 && <span className="nav-shortcut">{String(index + 1).padStart(2, "0")}</span>}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <button type="button" className="help-link" onClick={() => setChatOpen(true)}>
            <span className="nav-icon">
              <Icon name="spark" />
            </span>
            <span>Copiloto local</span>
          </button>
          <div className="profile-chip">
            <div className="avatar">LP</div>
            <div>
              <strong>Perfil local</strong>
              <small>Sin sincronización</small>
            </div>
          </div>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div className="mobile-brand">
            <BrandMark />
            <strong>FinanzAR</strong>
          </div>
          <span className="topbar-title">{TITLES[route]}</span>
          <div className="topbar-actions">
            <div className="privacy-pill">
              <span className="lock-icon">
                <Icon name="lock" />
              </span>
              <span>Privado en tu dispositivo</span>
            </div>
            <button type="button" className="secondary-button" onClick={() => setChatOpen(true)}>
              <Icon name="spark" /> Preguntarle a la IA
            </button>
            <span className="topbar-date">{formatDate(new Date().toISOString().slice(0, 10))}</span>
          </div>
        </header>
        <div className="page-wrap">{renderRoute()}</div>
      </main>

      <BackendGate />
      <CopilotDrawer open={chatOpen} onClose={() => setChatOpen(false)} />
      {moneyIntent && <MoneyModal mode={moneyIntent.mode} onClose={closeMoney} />}
      <ToastStack messages={toasts} onDismiss={dismissToast} />
    </div>
  );
}

export function App(): JSX.Element {
  return (
    <AppProvider>
      <Shell />
    </AppProvider>
  );
}
