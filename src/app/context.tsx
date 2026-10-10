/** Estado global de la aplicación (período, avisos, copiloto, modales). */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type JSX,
  type ReactNode,
} from "react";

import type { ToastMessage } from "../components/ui";
import { api } from "../lib/backend";
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
  | "profile";

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
  userName: string;
  setUserName: (name: string) => void;
  onboardingDone: boolean;
  setOnboardingDone: (done: boolean) => void;
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
  const [userName, setUserName] = useState("");
  // Arranca en "hecho" para no mostrar el asistente mientras el backend responde;
  // el bootstrap lo corrige con lo guardado en app_settings.
  const [onboardingDone, setOnboardingDone] = useState(true);

  useEffect(() => {
    if (!backendReady) return;
    let cancelled = false;
    api
      .bootstrap()
      .then((data) => {
        if (cancelled) return;
        const stored = (data.settings ?? {}) as Record<string, string>;
        setUserName(stored.user_name ?? "");
        setOnboardingDone(stored.onboarding_done === "true");
      })
      .catch(() => {
        /* si falla, se sigue con lo que haya */
      });
    return () => {
      cancelled = true;
    };
  }, [backendReady]);

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
      userName,
      setUserName,
      onboardingDone,
      setOnboardingDone,
    }),
    [
      route,
      period,
      refreshKey,
      toasts,
      toast,
      dismissToast,
      chatOpen,
      moneyIntent,
      backendReady,
      backendBase,
      userName,
      onboardingDone,
    ],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppContextValue {
  const value = useContext(AppContext);
  if (!value) throw new Error("useApp debe usarse dentro de AppProvider");
  return value;
}
