/** Estado global de la aplicación (período, avisos, copiloto, modales). */

import { createContext, useCallback, useContext, useMemo, useState, type JSX, type ReactNode } from "react";

import type { ToastMessage } from "../components/ui";
import { currentPeriod } from "../lib/format";

export type Route =
  | "dashboard"
  | "accounts"
  | "income"
  | "documents"
  | "calendar"
  | "movements"
  | "spreadsheet"
  | "settings"
  | "updates";

export interface MoneyModalIntent {
  mode: "income" | "salary";
}

interface AppContextValue {
  route: Route;
  setRoute: (route: Route) => void;
  period: string;
  setPeriod: (period: string) => void;
  refreshKey: number;
  refresh: () => void;
  toasts: ToastMessage[];
  toast: (text: string, tone?: "info" | "error") => void;
  dismissToast: (id: number) => void;
  chatOpen: boolean;
  setChatOpen: (open: boolean) => void;
  moneyIntent: MoneyModalIntent | null;
  openMoney: (mode: "income" | "salary") => void;
  closeMoney: () => void;
  backendReady: boolean;
  setBackendReady: (ready: boolean) => void;
  backendBase: string | null;
  setBackendBase: (base: string | null) => void;
}

const AppContext = createContext<AppContextValue | null>(null);

export function AppProvider({ children }: { children: ReactNode }): JSX.Element {
  const [route, setRoute] = useState<Route>("dashboard");
  const [period, setPeriod] = useState<string>(currentPeriod());
  const [refreshKey, setRefreshKey] = useState(0);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const [chatOpen, setChatOpen] = useState(false);
  const [moneyIntent, setMoneyIntent] = useState<MoneyModalIntent | null>(null);
  const [backendReady, setBackendReady] = useState(false);
  const [backendBase, setBackendBase] = useState<string | null>(null);

  const toast = useCallback((text: string, tone: "info" | "error" = "info") => {
    const id = Date.now() + Math.random();
    setToasts((current) => [...current, { id, text, tone }]);
    setTimeout(() => setToasts((current) => current.filter((message) => message.id !== id)), 4600);
  }, []);

  const dismissToast = useCallback((id: number) => {
    setToasts((current) => current.filter((message) => message.id !== id));
  }, []);

  const refresh = useCallback(() => setRefreshKey((value) => value + 1), []);

  const value = useMemo<AppContextValue>(
    () => ({
      route,
      setRoute,
      period,
      setPeriod,
      refreshKey,
      refresh,
      toasts,
      toast,
      dismissToast,
      chatOpen,
      setChatOpen,
      moneyIntent,
      openMoney: (mode) => setMoneyIntent({ mode }),
      closeMoney: () => setMoneyIntent(null),
      backendReady,
      setBackendReady,
      backendBase,
      setBackendBase,
    }),
    [route, period, refreshKey, toasts, toast, dismissToast, chatOpen, moneyIntent, backendReady, backendBase],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppContextValue {
  const value = useContext(AppContext);
  if (!value) throw new Error("useApp debe usarse dentro de AppProvider");
  return value;
}
