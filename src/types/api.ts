/** Tipos del contrato del backend local (envelope + entidades). */

export interface ApiEnvelope<T> {
  ok: boolean;
  data: T | null;
  error: { code: string; message: string; details?: Record<string, unknown> } | null;
  request_id: string;
}

export interface Account {
  id: string;
  name: string;
  kind: "bank" | "wallet" | "cash" | "savings" | "card";
  currency: string;
  opening_balance_cents: number;
  balance_cents?: number;
  institution: string | null;
  masked_number: string | null;
  close_day: number | null;
  due_day: number | null;
  archived: number;
  notes: string | null;
}

export interface CreditCard {
  id: string;
  name: string;
  brand: string;
  last4: string | null;
  close_day: number | null;
  due_day: number | null;
  currency: string;
  active: number;
}

export interface RecurringIncome {
  id: string;
  name: string;
  source: string;
  kind: string;
  amount_cents: number;
  currency: string;
  account_id: string | null;
  day_of_month: number;
  start_date: string;
  end_date: string | null;
  active: number;
  repeat_rule: string;
  inflation_pct: number;
}

export interface IncomeEntry {
  id: string;
  source: string;
  kind: string;
  amount_cents: number;
  currency: string;
  occurred_on: string;
  account_id: string | null;
  recurring_income_id: string | null;
}

export interface StatementField {
  id: string;
  field_key: string;
  field_value: string | null;
  value_type: string;
  confidence: number | null;
  source_page: number | null;
  source_bbox: number[] | null;
  evidence_text: string | null;
  status: string;
}

export interface Statement {
  id: string;
  filename: string;
  status: "imported" | "ocr" | "extracted" | "review" | "confirmed" | "error";
  period: string | null;
  close_date: string | null;
  due_date: string | null;
  total_cents: number | null;
  minimum_cents: number | null;
  currency: string;
  pages: number;
  card_id: string | null;
  imported_at: string;
  confirmed_at: string | null;
}

export interface Transaction {
  id: string;
  statement_id: string | null;
  card_id: string | null;
  occurred_on: string;
  description: string;
  category: string | null;
  amount_cents: number;
  currency: string;
  installment_number: number | null;
  installment_total: number | null;
  kind: string;
  confirmed: number;
  confidence: number | null;
  source_page?: number | null;
  source_bbox?: number[] | null;
}

/** Imagen de una página del PDF importado, con su tamaño para ubicar bboxes. */
export interface DocumentPageImage {
  page: number;
  pageCount: number;
  width: number;
  height: number;
  imageWidth: number;
  imageHeight: number;
  dataUrl: string;
}

export interface Installment {
  id: string;
  description: string;
  installment_number: number;
  installment_total: number;
  amount_cents: number;
  currency: string;
  first_period: string | null;
  remaining: number;
}

export interface Subscription {
  id: string;
  name: string;
  amount_cents: number;
  currency: string;
  periodicity: string;
  last_seen_period: string | null;
  active: number;
}

export interface Payment {
  id: string;
  statement_id: string | null;
  card_id: string | null;
  due_date: string;
  amount_cents: number;
  currency: string;
  kind: string;
  status: "pending" | "paid" | "scheduled";
}

export interface CalendarEvent {
  id: string;
  event_date: string;
  kind: string;
  title: string;
  amount_cents: number | null;
  currency: string | null;
}

export interface Insight {
  id: string;
  kind: string;
  period: string | null;
  title: string;
  body: string;
  severity: "good" | "review" | "info" | "alert";
  query: string | null;
  evidence: Array<{ label: string; amountCents?: number; text?: string }>;
}

export interface SavingsGoal {
  id: string;
  name: string;
  target_cents: number;
  saved_cents: number;
  currency: string;
  salary_percent: number | null;
  target_date: string | null;
  percent?: number;
  missingCents?: number;
}

export interface Projection {
  months: number;
  cutoff: string;
  startBalanceCents: number;
  futureIncomeCents: number;
  futurePaymentsCents: number;
  endBalanceCents: number;
  assumptions: string[];
  sources: Array<{ type: string; id: string; label: string; amountCents: number }>;
}

export interface Dashboard {
  period: string;
  balance: {
    totalCents: number;
    byCurrency: Record<string, number>;
    accounts: Array<Account & { balance_cents: number }>;
  };
  income: { monthCents: number; recurring: RecurringIncome[]; nextCredit: { date: string; amount_cents: number; name: string } | null };
  payments: { pendingCents: number; pendingCount: number; paidCents: number };
  upcomingPayments: Payment[];
  projection: Projection;
  projections: Record<string, Projection>;
  commitments: { installmentsCents: number; subscriptionsCents: number; activeInstallments: number; subscriptions: number };
  emergencyFund: SavingsGoal | null;
  lowBalanceAlert: { thresholdCents: number; projectedCents: number; title: string; body: string } | null;
  documents: { total: number; pending: number; pendingList: Array<{ id: string; filename: string; status: string }> };
  insights: Insight[];
  calendar: CalendarEvent[];
}

export interface CopilotSource {
  id: string;
  label: string;
  kind: string;
  amountCents?: number;
  amount?: string;
}

export interface CopilotAnswer {
  answer: string;
  sources: CopilotSource[];
  evidenceAvailable: boolean;
  engine: string;
  usedLlm: boolean;
  detectedIntents: string[];
}

export interface ModelStatus {
  id: string;
  name: string;
  kind: string;
  required: boolean;
  revision: string;
  license: string;
  approxBytes: number;
  installed: boolean;
  verified: boolean;
  path: string | null;
  sizeBytes: number;
  status: string;
  quantization: string | null;
  notes: string;
}

export interface RuntimeStatus {
  id: string;
  name: string;
  build: string;
  minimumBuild: string;
  target: string;
  installed: boolean;
  path: string | null;
  asset: string | null;
  approxBytes: number | null;
}

export interface UpdateStatus {
  currentVersion: string;
  latestVersion?: string | null;
  available?: boolean;
  channel?: string;
  target?: string;
  publishedAt?: string | null;
  notes?: string | null;
  asset?: { name: string; url: string; bytes: number } | null;
  checkedAt?: string;
  offline?: boolean;
  error?: string | null;
  requiresConsent?: boolean;
}

export interface Job {
  id: string;
  kind: string;
  status: string;
  progress: number;
  message: string;
  error: string | null;
}

export interface BootstrapStatus {
  backend: boolean;
  base_url: string | null;
  version: string;
  stage: string;
}
