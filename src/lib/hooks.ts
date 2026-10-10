/** Hooks compartidos: llamadas al backend con estado de carga y error. */

import { useCallback, useEffect, useRef, useState } from "react";

export interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

/** Ejecuta una consulta al backend y expone carga, error y recarga. */
export function useAsync<T>(loader: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    loader()
      .then((result) => {
        if (active) setData(result);
      })
      .catch((err: unknown) => {
        if (active) setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
    // `loader` se recrea en cada render; se controlan las dependencias desde afuera.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  const reload = useCallback(() => setNonce((value) => value + 1), []);
  return { data, loading, error, reload };
}

/** Avisos efímeros. */
export interface ToastController {
  messages: Array<{ id: number; text: string; tone?: "info" | "error" }>;
  push: (text: string, tone?: "info" | "error") => void;
  dismiss: (id: number) => void;
}

export function useToasts(): ToastController {
  const [messages, setMessages] = useState<Array<{ id: number; text: string; tone?: "info" | "error" }>>([]);
  const push = useCallback((text: string, tone: "info" | "error" = "info") => {
    const id = Date.now() + Math.random();
    setMessages((current) => [...current, { id, text, tone }]);
    setTimeout(() => {
      setMessages((current) => current.filter((message) => message.id !== id));
    }, 4200);
  }, []);
  const dismiss = useCallback((id: number) => {
    setMessages((current) => current.filter((message) => message.id !== id));
  }, []);
  return { messages, push, dismiss };
}

/** Consulta re-ejecutable cuando cambia el período u otro disparador. */
export function usePeriod(initial: string): [string, (value: string) => void] {
  const [period, setPeriod] = useState(initial);
  return [period, setPeriod];
}

/** Detecta si las preferencias piden menos movimiento. */
export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const query = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!query) return;
    setReduced(query.matches);
    const listener = (event: MediaQueryListEvent) => setReduced(event.matches);
    query.addEventListener("change", listener);
    return () => query.removeEventListener("change", listener);
  }, []);
  return reduced;
}