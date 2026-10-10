/** Detección del entorno Tauri y wrappers seguros de `invoke`. */

type InvokeFn = <T>(command: string, args?: Record<string, unknown>) => Promise<T>;

interface TauriWindow {
  __TAURI_INTERNALS__?: { invoke?: InvokeFn };
  __TAURI__?: { core?: { invoke?: InvokeFn }; dialog?: unknown };
}

export function isTauri(): boolean {
  if (typeof window === "undefined") return false;
  return Boolean((window as TauriWindow).__TAURI_INTERNALS__);
}

async function loadInvoke(): Promise<InvokeFn | null> {
  if (!isTauri()) return null;
  const globalInvoke = (window as TauriWindow).__TAURI_INTERNALS__?.invoke;
  if (globalInvoke) return globalInvoke;
  try {
    const module = await import("@tauri-apps/api/core");
    return module.invoke as InvokeFn;
  } catch {
    return null;
  }
}

export async function invoke<T>(command: string, args?: Record<string, unknown>): Promise<T | null> {
  const fn = await loadInvoke();
  if (!fn) return null;
  try {
    return await fn<T>(command, args);
  } catch (error) {
    // Los comandos devuelven CommandError { code, message }.
    const message =
      typeof error === "object" && error !== null && "message" in error
        ? String((error as { message: unknown }).message)
        : String(error);
    throw new Error(message);
  }
}

export async function pickPdf(): Promise<string | null> {
  if (!isTauri()) return null;
  try {
    const dialog = await import("@tauri-apps/plugin-dialog");
    const selection = await dialog.open({
      multiple: false,
      filters: [{ name: "Resumen PDF", extensions: ["pdf"] }],
    });
    if (typeof selection === "string") return selection;
    return null;
  } catch {
    return null;
  }
}

export async function saveFileDialog(defaultPath: string): Promise<string | null> {
  if (!isTauri()) return null;
  try {
    const dialog = await import("@tauri-apps/plugin-dialog");
    const selection = await dialog.save({
      defaultPath,
      filters: [{ name: "Planilla XLSX", extensions: ["xlsx"] }],
    });
    return typeof selection === "string" ? selection : null;
  } catch {
    return null;
  }
}

export async function openPath(path: string): Promise<void> {
  if (!isTauri()) return;
  try {
    const opener = await import("@tauri-apps/plugin-opener");
    await opener.openPath(path);
  } catch {
    /* abrir el archivo es best-effort */
  }
}

export interface UnlistenFn {
  (): void;
}

export async function listen<T>(event: string, handler: (payload: T) => void): Promise<UnlistenFn> {
  if (!isTauri()) return () => undefined;
  try {
    const api = await import("@tauri-apps/api/event");
    const unlisten = await api.listen<T>(event, (event) => handler(event.payload));
    return unlisten;
  } catch {
    return () => undefined;
  }
}
