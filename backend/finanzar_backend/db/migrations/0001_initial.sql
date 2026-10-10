-- FinanzAR Desktop — migración inicial.
-- Reglas: dinero siempre INTEGER en centavos; importes derivados de OCR guardan
-- confianza, página, bbox y evidencia; nada de floats para dinero.

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,
    applied_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    id                    TEXT PRIMARY KEY,
    user_id               TEXT NOT NULL DEFAULT 'local',
    name                  TEXT NOT NULL,
    kind                  TEXT NOT NULL DEFAULT 'bank',  -- bank|wallet|cash|savings|card
    currency              TEXT NOT NULL DEFAULT 'ARS',
    opening_balance_cents INTEGER NOT NULL DEFAULT 0,
    institution           TEXT,
    masked_number         TEXT,
    close_day             INTEGER,
    due_day               INTEGER,
    archived              INTEGER NOT NULL DEFAULT 0,
    notes                 TEXT,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_accounts_user ON accounts(user_id, archived);

CREATE TABLE IF NOT EXISTS credit_cards (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL DEFAULT 'local',
    account_id  TEXT REFERENCES accounts(id) ON DELETE SET NULL,
    name        TEXT NOT NULL,
    brand       TEXT NOT NULL,          -- visa|master|amex|other
    last4       TEXT,
    currency    TEXT NOT NULL DEFAULT 'ARS',
    close_day   INTEGER,
    due_day     INTEGER,
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cards_user ON credit_cards(user_id, active);

CREATE TABLE IF NOT EXISTS recurring_income (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL DEFAULT 'local',
    name          TEXT NOT NULL,
    source        TEXT NOT NULL,
    kind          TEXT NOT NULL DEFAULT 'salary', -- salary|freelance|bonus|rent|other
    amount_cents  INTEGER NOT NULL,
    currency      TEXT NOT NULL DEFAULT 'ARS',
    account_id    TEXT REFERENCES accounts(id) ON DELETE SET NULL,
    day_of_month  INTEGER NOT NULL DEFAULT 1,
    start_date    TEXT NOT NULL,
    end_date      TEXT,
    active        INTEGER NOT NULL DEFAULT 1,
    repeat_rule   TEXT NOT NULL DEFAULT 'monthly',
    inflation_pct REAL NOT NULL DEFAULT 0,   -- porcentaje, no dinero
    notes         TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_recurring_user ON recurring_income(user_id, active);

CREATE TABLE IF NOT EXISTS income_entries (
    id                  TEXT PRIMARY KEY,
    user_id             TEXT NOT NULL DEFAULT 'local',
    account_id          TEXT REFERENCES accounts(id) ON DELETE SET NULL,
    recurring_income_id TEXT REFERENCES recurring_income(id) ON DELETE SET NULL,
    source              TEXT NOT NULL,
    kind                TEXT NOT NULL DEFAULT 'punctual', -- punctual|salary|freelance|bonus|transfer|adjustment
    amount_cents        INTEGER NOT NULL,
    currency            TEXT NOT NULL DEFAULT 'ARS',
    occurred_on         TEXT NOT NULL,
    note                TEXT,
    created_at          TEXT NOT NULL,
    UNIQUE (recurring_income_id, occurred_on)
);
CREATE INDEX IF NOT EXISTS idx_income_user_date ON income_entries(user_id, occurred_on);

CREATE TABLE IF NOT EXISTS statements (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL DEFAULT 'local',
    card_id       TEXT REFERENCES credit_cards(id) ON DELETE SET NULL,
    checksum      TEXT NOT NULL UNIQUE,
    filename      TEXT NOT NULL,
    stored_path   TEXT NOT NULL,
    period        TEXT,                 -- YYYY-MM
    close_date    TEXT,
    due_date      TEXT,
    total_cents   INTEGER,
    minimum_cents INTEGER,
    currency      TEXT NOT NULL DEFAULT 'ARS',
    status        TEXT NOT NULL DEFAULT 'imported', -- imported|ocr|extracted|review|confirmed|error
    pages         INTEGER NOT NULL DEFAULT 0,
    source        TEXT NOT NULL DEFAULT 'pdf',
    imported_at   TEXT NOT NULL,
    confirmed_at  TEXT,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_statements_user ON statements(user_id, period);

CREATE TABLE IF NOT EXISTS statement_fields (
    id            TEXT PRIMARY KEY,
    statement_id  TEXT NOT NULL REFERENCES statements(id) ON DELETE CASCADE,
    field_key     TEXT NOT NULL,
    field_value   TEXT,
    value_type    TEXT NOT NULL DEFAULT 'text', -- text|money|date|int|list
    confidence    REAL,
    source_page   INTEGER,
    source_bbox   TEXT,
    evidence_text TEXT,
    status        TEXT NOT NULL DEFAULT 'pending', -- pending|confirmed|edited|rejected
    confirmed_at  TEXT,
    updated_at    TEXT NOT NULL,
    UNIQUE (statement_id, field_key)
);
CREATE INDEX IF NOT EXISTS idx_fields_statement ON statement_fields(statement_id);

CREATE TABLE IF NOT EXISTS transactions (
    id                     TEXT PRIMARY KEY,
    user_id                TEXT NOT NULL DEFAULT 'local',
    statement_id           TEXT REFERENCES statements(id) ON DELETE CASCADE,
    card_id                TEXT REFERENCES credit_cards(id) ON DELETE SET NULL,
    occurred_on            TEXT NOT NULL,
    description            TEXT NOT NULL,
    normalized_description TEXT,
    category               TEXT,
    amount_cents           INTEGER NOT NULL,
    currency               TEXT NOT NULL DEFAULT 'ARS',
    foreign_amount_cents   INTEGER,
    foreign_currency       TEXT,
    installment_number     INTEGER,
    installment_total      INTEGER,
    kind                   TEXT NOT NULL DEFAULT 'purchase', -- purchase|installment|subscription|fee|tax|payment
    confirmed              INTEGER NOT NULL DEFAULT 0,
    source_page            INTEGER,
    source_bbox            TEXT,
    confidence             REAL,
    content_hash           TEXT,
    created_at             TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tx_user_date ON transactions(user_id, occurred_on);
CREATE INDEX IF NOT EXISTS idx_tx_statement ON transactions(statement_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tx_dedupe
    ON transactions(statement_id, content_hash) WHERE content_hash IS NOT NULL;

CREATE TABLE IF NOT EXISTS installments (
    id                 TEXT PRIMARY KEY,
    user_id            TEXT NOT NULL DEFAULT 'local',
    card_id            TEXT REFERENCES credit_cards(id) ON DELETE SET NULL,
    statement_id       TEXT REFERENCES statements(id) ON DELETE SET NULL,
    transaction_id     TEXT REFERENCES transactions(id) ON DELETE SET NULL,
    description        TEXT NOT NULL,
    installment_number INTEGER NOT NULL,
    installment_total  INTEGER NOT NULL,
    amount_cents       INTEGER NOT NULL,
    currency           TEXT NOT NULL DEFAULT 'ARS',
    first_period       TEXT,
    remaining          INTEGER NOT NULL DEFAULT 0,
    created_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_installments_card ON installments(card_id, first_period);

CREATE TABLE IF NOT EXISTS subscriptions (
    id               TEXT PRIMARY KEY,
    user_id          TEXT NOT NULL DEFAULT 'local',
    card_id          TEXT REFERENCES credit_cards(id) ON DELETE SET NULL,
    name             TEXT NOT NULL,
    amount_cents     INTEGER NOT NULL,
    currency         TEXT NOT NULL DEFAULT 'ARS',
    periodicity      TEXT NOT NULL DEFAULT 'monthly',
    last_seen_period TEXT,
    occurrences      INTEGER NOT NULL DEFAULT 1,
    active           INTEGER NOT NULL DEFAULT 1,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_subs_user ON subscriptions(user_id, active);

CREATE TABLE IF NOT EXISTS payments (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL DEFAULT 'local',
    card_id      TEXT REFERENCES credit_cards(id) ON DELETE SET NULL,
    statement_id TEXT REFERENCES statements(id) ON DELETE CASCADE,
    due_date     TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    currency     TEXT NOT NULL DEFAULT 'ARS',
    kind         TEXT NOT NULL DEFAULT 'total', -- total|minimum|partial
    status       TEXT NOT NULL DEFAULT 'pending', -- pending|paid|scheduled
    paid_at      TEXT,
    created_at   TEXT NOT NULL,
    UNIQUE (statement_id, kind)
);
CREATE INDEX IF NOT EXISTS idx_payments_user_due ON payments(user_id, due_date);

CREATE TABLE IF NOT EXISTS calendar_events (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL DEFAULT 'local',
    event_date   TEXT NOT NULL,
    kind         TEXT NOT NULL,   -- due|close|installment|subscription|income|goal
    title        TEXT NOT NULL,
    amount_cents INTEGER,
    currency     TEXT,
    ref_table    TEXT,
    ref_id       TEXT,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_calendar_range ON calendar_events(user_id, event_date);

CREATE TABLE IF NOT EXISTS savings_goals (
    id             TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL DEFAULT 'local',
    name           TEXT NOT NULL,
    target_cents   INTEGER NOT NULL,
    saved_cents    INTEGER NOT NULL DEFAULT 0,
    currency       TEXT NOT NULL DEFAULT 'ARS',
    account_id     TEXT REFERENCES accounts(id) ON DELETE SET NULL,
    salary_percent REAL,
    target_date    TEXT,
    active         INTEGER NOT NULL DEFAULT 1,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS insights (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL DEFAULT 'local',
    kind          TEXT NOT NULL,
    period        TEXT,
    title         TEXT NOT NULL,
    body          TEXT NOT NULL,
    severity      TEXT NOT NULL DEFAULT 'info', -- good|review|info|alert
    query         TEXT,
    evidence_json TEXT NOT NULL DEFAULT '[]',
    confirmed     INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_insights_user_period ON insights(user_id, period);

CREATE TABLE IF NOT EXISTS audit_events (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL DEFAULT 'local',
    at           TEXT NOT NULL,
    actor        TEXT NOT NULL DEFAULT 'local',
    action       TEXT NOT NULL,
    entity       TEXT,
    entity_id    TEXT,
    details_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS model_installations (
    id            TEXT PRIMARY KEY,
    model_id      TEXT NOT NULL,
    revision      TEXT NOT NULL,
    quantization  TEXT,
    path          TEXT NOT NULL,
    size_bytes    INTEGER NOT NULL DEFAULT 0,
    sha256        TEXT,
    status        TEXT NOT NULL DEFAULT 'installed', -- installed|downloading|error|missing
    installed_at  TEXT,
    updated_at    TEXT NOT NULL,
    UNIQUE (model_id, revision, quantization)
);

CREATE TABLE IF NOT EXISTS copilot_messages (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL DEFAULT 'local',
    role         TEXT NOT NULL,   -- user|assistant|system
    content      TEXT NOT NULL,
    sources_json TEXT NOT NULL DEFAULT '[]',
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_copilot_user ON copilot_messages(user_id, created_at);

CREATE TABLE IF NOT EXISTS statement_chunks_index (
    id           TEXT PRIMARY KEY,
    statement_id TEXT NOT NULL REFERENCES statements(id) ON DELETE CASCADE,
    page         INTEGER,
    content_hash TEXT NOT NULL,
    indexed_at   TEXT NOT NULL
);
