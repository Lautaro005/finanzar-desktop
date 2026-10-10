/** Cliente del backend local.
 *
 * Dentro de Tauri las llamadas pasan por comandos de Rust (que hablan con
 * `127.0.0.1`). En el navegador (tests o `vite dev` sin Tauri) se usa `fetch`
 * directo contra `VITE_FINANZAR_API` o `http://127.0.0.1:8765`.
 */

import type {
  Account,
  ApiEnvelope,
  BootstrapStatus,
  CalendarEvent,
  CopilotAnswer,
  CreditCard,
  Dashboard,
  DocumentPageImage,
  IncomeEntry,
  Insight,
  Installment,
  Job,
  ModelStatus,
  Payment,
  RecurringIncome,
  RuntimeStatus,
  SavingsGoal,
  Statement,
  StatementField,
  Subscription,
  Transaction,
  UpdateStatus,
} from "../types/api";
import { invoke, isTauri } from "./tauri";

const FALLBACK_BASE = (import.meta.env?.VITE_FINANZAR_API as string | undefined) ?? "http://127.0.0.1:8765";

let resolvedBase: string | null = null;

export class ApiError extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

async function resolveBase(): Promise<string> {
  if (resolvedBase) return resolvedBase;
  if (isTauri()) {
    const status = await invoke<BootstrapStatus>("bootstrap_status");
    if (status?.base_url) {
      resolvedBase = status.base_url;
      return resolvedBase;
    }
  }
  resolvedBase = FALLBACK_BASE;
  return resolvedBase;
}

async function browserRequest<T>(method: string, path: string, body?: unknown): Promise<T> {
  const base = await resolveBase();
  const response = await fetch(`${base}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const envelope = (await response.json()) as ApiEnvelope<T>;
  if (!envelope.ok) {
    throw new ApiError(envelope.error?.code ?? "backend_error", envelope.error?.message ?? "Error del backend local");
  }
  return envelope.data as T;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  if (isTauri()) {
    if (method === "GET") {
      const data = await invoke<T>("api_get", { path });
      if (data !== null) return data;
    } else {
      const data = await invoke<T>("api_request", { method, path, body: body ?? null });
      if (data !== null) return data;
    }
  }
  return browserRequest<T>(method, path, body);
}

export const api = {
  health: () => request<{ status: string; version: string; llmAvailable: boolean; memoryBackend: string }>("GET", "/health"),
  bootstrap: () => request<Record<string, unknown>>("GET", "/api/bootstrap"),

  dashboard: (period: string) => request<Dashboard>("GET", `/api/dashboard?month=${period}`),

  accounts: () => request<{ accounts: Account[] }>("GET", "/api/accounts"),
  createAccount: (payload: Record<string, unknown>) => request<{ account: Account }>("POST", "/api/accounts", payload),
  patchAccount: (id: string, payload: Record<string, unknown>) =>
    request<{ account: Account }>("PATCH", `/api/accounts/${id}`, payload),

  cards: () => request<{ cards: CreditCard[] }>("GET", "/api/cards"),

  incomes: () => request<{ entries: IncomeEntry[]; recurring: RecurringIncome[] }>("GET", "/api/incomes"),
  createIncome: (payload: Record<string, unknown>) => request<{ entry: IncomeEntry; balanceCents: number }>("POST", "/api/incomes", payload),
  createRecurring: (payload: Record<string, unknown>) =>
    request<{ recurring: RecurringIncome; applied: IncomeEntry[] }>("POST", "/api/incomes/recurring", payload),
  patchRecurring: (id: string, payload: Record<string, unknown>) =>
    request<{ recurring: RecurringIncome }>("PATCH", `/api/incomes/recurring/${id}`, payload),
  patchIncome: (id: string, payload: Record<string, unknown>) =>
    request<{ entry: IncomeEntry; balanceCents: number }>("PATCH", `/api/incomes/${id}`, payload),
  deleteIncome: (id: string) =>
    request<{ deleted: boolean; balanceCents: number }>("DELETE", `/api/incomes/${id}`),

  documents: () => request<{ documents: Statement[] }>("GET", "/api/documents"),
  importDocument: async (path: string): Promise<{ document: Statement }> => {
    if (isTauri()) {
      const data = await invoke<{ document: Statement }>("pick_and_import_pdf", { path });
      if (data) return data;
    }
    throw new ApiError("tauri_required", "Importar un PDF requiere la aplicación de escritorio");
  },
  runOcr: (id: string, prefer = "auto") =>
    request<{ fields: number; transactions: number; engine: string }>("POST", `/api/documents/${id}/ocr?prefer=${prefer}`),
  review: (id: string) =>
    request<{ statement: Statement; fields: StatementField[]; transactions: Transaction[] }>("GET", `/api/documents/${id}/review`),
  patchFields: (id: string, fields: Array<{ fieldKey: string; value: string }>) =>
    request<{ fields: StatementField[] }>("PATCH", `/api/documents/${id}/fields`, { fields }),
  confirmDocument: (id: string) =>
    request<{ statement: Statement; indexedChunks: number }>("POST", `/api/documents/${id}/confirm`),
  documentPage: (id: string, page = 1, dpi = 150) =>
    request<DocumentPageImage>("GET", `/api/documents/${id}/page?page=${page}&dpi=${dpi}`),
  deleteDocument: (id: string) =>
    request<{ deleted: boolean; statementId: string }>("DELETE", `/api/documents/${id}`),
  extractRegions: (id: string, page: number, regions: number[][]) =>
    request<{ transactions: Transaction[]; engine: string; regions: number; added: number; skipped: number }>(
      "POST",
      `/api/documents/${id}/extract-regions`,
      { page, regions },
    ),
  addDocumentTransactions: (
    id: string,
    transactions: Array<Record<string, unknown>>,
  ) => request<{ transactions: Transaction[] }>("POST", `/api/documents/${id}/transactions`, { transactions }),

  transactions: (params: { month?: string; cardId?: string; kind?: string } = {}) => {
    const query = new URLSearchParams();
    if (params.month) query.set("month", params.month);
    if (params.cardId) query.set("cardId", params.cardId);
    if (params.kind) query.set("kind", params.kind);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return request<{ transactions: Transaction[] }>("GET", `/api/transactions${suffix}`);
  },
  deleteTransaction: (id: string) =>
    request<{ deleted: boolean }>("DELETE", `/api/transactions/${id}`),
  patchTransaction: (id: string, payload: Record<string, unknown>) =>
    request<{ transaction: Transaction }>("PATCH", `/api/transactions/${id}`, payload),

  calendar: (from: string, to: string) =>
    request<{ events: CalendarEvent[] }>("GET", `/api/calendar?from=${from}&to=${to}`),

  payments: (status?: string) =>
    request<{ payments: Payment[] }>("GET", `/api/payments${status ? `?status=${status}` : ""}`),
  setPaymentStatus: (id: string, status: string) =>
    request<{ payments: Payment[] }>("POST", `/api/payments/${id}`, { status }),

  goals: () => request<{ goals: SavingsGoal[]; emergencyFund: SavingsGoal | null }>("GET", "/api/goals"),
  createGoal: (payload: Record<string, unknown>) => request<{ goal: SavingsGoal }>("POST", "/api/goals", payload),

  insights: (period: string) => request<{ insights: Insight[]; period: string }>("GET", `/api/insights?month=${period}`),

  copilot: (question: string, period?: string) =>
    request<CopilotAnswer>("POST", "/api/copilot/chat", { question, month: period ?? null }),
  copilotHistory: () =>
    request<{ messages: Array<{ id: string; role: string; content: string; sources: unknown[] }> }>("GET", "/api/copilot/history"),
  clearHistory: () => request<{ cleared: boolean }>("DELETE", "/api/copilot/history"),

  exportPreview: (period: string) =>
    request<{ sheets: string[]; rowCounts: Record<string, number> }>("GET", `/api/export/preview?month=${period}`),
  exportXlsx: (period: string, path?: string) =>
    request<{ path: string; sheets: string[]; bytes: number }>("POST", "/api/export/xlsx", { month: period, path: path ?? null }),

  models: () => request<{ models: ModelStatus[]; runtime: RuntimeStatus; llmAvailable: boolean }>("GET", "/api/models/status"),
  downloadModel: (modelId: string, quantization?: string) =>
    request<{ model: ModelStatus }>("POST", "/api/models/download", { modelId, quantization: quantization ?? null }),
  cancelModel: (modelId: string) => request<{ cancelled: boolean }>("POST", "/api/models/cancel", { modelId }),
  downloadRuntime: () => request<RuntimeStatus>("POST", "/api/models/runtime/download"),
  startLlm: () => request<Record<string, unknown>>("POST", "/api/llm/start"),
  jobs: (kind?: string) => request<{ jobs: Job[] }>("GET", `/api/jobs${kind ? `?kind=${kind}` : ""}`),

  updateStatus: () => request<UpdateStatus>("GET", "/api/app/update-status"),
  updateCheck: () => request<UpdateStatus>("POST", "/api/app/update-check"),

  settings: () => request<{ settings: Record<string, string> }>("GET", "/api/settings"),
  patchSettings: (values: Record<string, string>) =>
    request<{ settings: Record<string, string> }>("PATCH", "/api/settings", { values }),

  installments: () => request<{ installments: Installment[] }>("GET", "/api/installments"),
  subscriptions: () => request<{ subscriptions: Subscription[] }>("GET", "/api/subscriptions"),
  commitments: () =>
    request<{
      installments: Installment[];
      subscriptions: Subscription[];
      installmentsCents: number;
      subscriptionsCents: number;
    }>("GET", "/api/commitments"),
};
