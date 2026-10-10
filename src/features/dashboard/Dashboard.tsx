/** Dashboard mensual: balance, ingresos, a pagar, proyección e insights. */

import { useCallback, type JSX } from "react";

import { Icon } from "../../components/Icon";
import { MonthSelect } from "../../components/DateField";
import { EmptyState, ErrorBlock, LoadingBlock, Panel, ProgressBar, StatusPill } from "../../components/ui";
import { api } from "../../lib/backend";
import { formatCents, formatDate, formatDayMonth, monthLabel } from "../../lib/format";
import { useAsync } from "../../lib/hooks";
import { useApp } from "../../app/context";

const INSIGHT_CLASS: Record<string, string> = {
  good: "insight-green",
  review: "insight-yellow",
  alert: "insight-red",
  info: "insight-blue",
};

const INSIGHT_ICON: Record<string, string> = {
  good: "trend",
  review: "eye",
  alert: "alert",
  info: "spark",
};

/** Monto en pesos con el saldo en dólares debajo, cuando lo hay. */
function AmountStack({
  cents,
  usdCents,
  className = "stat-value",
  altClassName = "stat-alt",
}: {
  cents: number;
  usdCents: number;
  className?: string;
  altClassName?: string;
}): JSX.Element {
  return (
    <>
      <strong className={className}>{formatCents(cents)}</strong>
      {usdCents !== 0 && <span className={altClassName}>{formatCents(usdCents, "USD")} en dólares</span>}
    </>
  );
}

export function Dashboard(): JSX.Element {
  const { period, setPeriod, refreshKey, refresh, setRoute, openMoney, setChatOpen, toast } = useApp();
  const dashboard = useAsync(() => api.dashboard(period), [period, refreshKey]);

  const loading = dashboard.loading && !dashboard.data;
  const data = dashboard.data;

  const markPaid = useCallback(
    async (paymentId: string) => {
      try {
        await api.setPaymentStatus(paymentId, "paid");
        toast("Pago marcado como realizado.");
        refresh();
      } catch (error) {
        toast(error instanceof Error ? error.message : "No se pudo actualizar el pago", "error");
      }
    },
    [refresh, toast],
  );

  if (loading) return <LoadingBlock message="Leyendo tus datos confirmados…" />;
  if (dashboard.error) return <ErrorBlock message={dashboard.error} onRetry={dashboard.reload} />;
  if (!data) return <EmptyState title="Sin datos para mostrar" />;

  const totalDocs = data.documents.total;
  const pendingDocs = data.documents.pending;
  const closingProgress = totalDocs === 0 ? 0 : ((totalDocs - pendingDocs) / totalDocs) * 100;
  // Los saldos en dólares van aparte: la app no convierte moneda.
  const usdBalance = data.balance.byCurrency?.USD ?? 0;
  const usdIncome = data.income.byCurrency?.USD ?? 0;
  const usdPending = data.payments.byCurrency?.USD ?? 0;
  const usdProjectedStart = data.projection.startByCurrency?.USD ?? 0;
  const usdProjectedIncome = data.projection.incomeByCurrency?.USD ?? 0;
  const usdProjectedPayments = data.projection.paymentsByCurrency?.USD ?? 0;
  const usdProjectedEnd = data.projection.endByCurrency?.USD ?? 0;
  const usdInstallments = data.commitments.installmentsByCurrency?.USD ?? 0;
  const usdSubscriptions = data.commitments.subscriptionsByCurrency?.USD ?? 0;
  const usdPaid = data.payments.paidByCurrency?.USD ?? 0;

  return (
    <>
      <div className="page-heading dashboard-heading">
        <div>
          <p className="eyebrow">{monthLabel(period)} · resumen local</p>
          <h1>Tu mes, bajo control.</h1>
          <p className="heading-copy">Una vista clara de lo que ya pasó, lo que vence y lo que viene.</p>
        </div>
        <div className="heading-actions">
          <div className="period-picker">
            <Icon name="calendar" />
            <MonthSelect value={period} onChange={(next) => setPeriod(next)} ariaLabel="Período" />
          </div>
          <div className="heading-actions-end">
            <button type="button" className="secondary-button" onClick={() => openMoney("income")}>
              <Icon name="plus" /> Agregar dinero
            </button>
            <button type="button" className="primary-button" onClick={() => setRoute("documents")}>
              <Icon name="plus" /> Cargar resumen
            </button>
          </div>
        </div>
      </div>

      <div className="closing-strip">
        <div className="closing-icon">
          <Icon name="sun" />
        </div>
        <div className="closing-copy">
          <strong>Cierre de {monthLabel(period)}</strong>
          <span>
            {pendingDocs === 0
              ? "Tenés todos los documentos confirmados. Buen momento para exportar la planilla."
              : `Te quedan ${pendingDocs} documento${pendingDocs === 1 ? "" : "s"} por revisar.`}
          </span>
        </div>
        <div className="closing-progress">
          <span>
            {totalDocs - pendingDocs} de {totalDocs} listos
          </span>
          <ProgressBar value={closingProgress} label="Progreso del cierre mensual" />
        </div>
        <button type="button" className="text-button" onClick={() => setRoute("documents")}>
          Continuar <Icon name="arrow" />
        </button>
      </div>

      {data.lowBalanceAlert && (
        <div className="alert-strip" role="alert">
          <Icon name="alert" />
          <div>
            <strong>{data.lowBalanceAlert.title}</strong>
            <span>
              Proyectado {formatCents(data.lowBalanceAlert.projectedCents)} · umbral{" "}
              {formatCents(data.lowBalanceAlert.thresholdCents)}
            </span>
          </div>
        </div>
      )}

      <div className="stats-grid">
        <article className="stat-card stat-highlight">
          <div className="stat-top">
            <span className="stat-label">Balance disponible</span>
            <span className="stat-icon">
              <Icon name="wallet" />
            </span>
          </div>
          <AmountStack cents={data.balance.totalCents} usdCents={usdBalance} />
          <div className="stat-foot">
            <span>{data.balance.accounts.length} cuentas activas</span>
          </div>
        </article>
        <article className="stat-card">
          <div className="stat-top">
            <span className="stat-label">Ingresos del mes</span>
            <span className="stat-icon soft-yellow">
              <Icon name="arrow-down" />
            </span>
          </div>
          <AmountStack cents={data.income.monthCents} usdCents={usdIncome} />
          <div className="stat-foot">
            <span>{data.income.nextCredit ? `próximo ${formatDate(data.income.nextCredit.date)}` : "sin recurrencias"}</span>
          </div>
        </article>
        <article className="stat-card">
          <div className="stat-top">
            <span className="stat-label">A pagar este mes</span>
            <span className="stat-icon soft-blue">
              <Icon name="credit-card" />
            </span>
          </div>
          <AmountStack cents={data.payments.pendingCents} usdCents={usdPending} />
          <div className="stat-foot">
            <span>{data.payments.pendingCount} vencimientos</span>
          </div>
        </article>
        <article className="stat-card">
          <div className="stat-top">
            <span className="stat-label">Saldo proyectado</span>
            <span className="stat-icon soft-red">
              <Icon name="target" />
            </span>
          </div>
          <strong className="stat-value">{formatCents(data.projection.endBalanceCents)}</strong>
          <div className="stat-foot">
            <span>corte {formatDate(data.projection.cutoff)}</span>
          </div>
        </article>
      </div>

      <div className="cashflow-grid">
        <Panel title="Tus cuentas" subtitle="Saldo real disponible en cada lugar." className="accounts-panel">
          {data.balance.accounts.length === 0 ? (
            <EmptyState
              icon="wallet"
              title="Todavía no cargaste cuentas"
              body="Creá una cuenta para empezar a ver tu balance consolidado."
              action={
                <button type="button" className="secondary-button" onClick={() => setRoute("accounts")}>
                  <Icon name="plus" /> Crear cuenta
                </button>
              }
            />
          ) : (
            <>
              <div className="accounts-list">
                {data.balance.accounts.map((account) => (
                  <div className="account-row" key={account.id}>
                    <span className={`account-icon ${account.kind}`}>
                      <Icon name={account.kind === "bank" ? "building" : "wallet"} />
                    </span>
                    <span className="account-copy">
                      <strong>{account.name}</strong>
                      <small>
                        {account.institution ?? account.kind}
                        {account.masked_number ? ` · ${account.masked_number}` : ""}
                      </small>
                    </span>
                    <strong className="account-balance">{formatCents(account.balance_cents, account.currency)}</strong>
                  </div>
                ))}
              </div>
              <div className="accounts-total">
                <span>Total disponible</span>
                <AmountStack
                  cents={data.balance.totalCents}
                  usdCents={usdBalance}
                  className="accounts-total-value"
                  altClassName="accounts-total-alt"
                />
              </div>
            </>
          )}
        </Panel>

        <Panel
          title="Cómo termina el mes"
          subtitle="Proyección con ingresos y compromisos conocidos."
          className="forecast-panel"
          action={<span className="forecast-badge">{formatDate(data.projection.cutoff).slice(0, 5)}</span>}
        >
          <div className="forecast-flow">
            <div>
              <span>Saldo actual</span>
              <AmountStack
                cents={data.projection.startBalanceCents}
                usdCents={usdProjectedStart}
                className="forecast-value"
                altClassName="stat-alt"
              />
            </div>
            <span className="flow-sign positive-sign">+</span>
            <div>
              <span>Ingresos programados</span>
              <AmountStack
                cents={data.projection.futureIncomeCents}
                usdCents={usdProjectedIncome}
                className="forecast-value"
                altClassName="stat-alt"
              />
            </div>
            <span className="flow-sign negative-sign">−</span>
            <div>
              <span>Pagos y fijos</span>
              <AmountStack
                cents={data.projection.futurePaymentsCents}
                usdCents={usdProjectedPayments}
                className="forecast-value"
                altClassName="stat-alt"
              />
            </div>
            <span className="flow-sign">=</span>
            <div className="forecast-result">
              <span>Saldo estimado</span>
              <AmountStack
                cents={data.projection.endBalanceCents}
                usdCents={usdProjectedEnd}
                className="forecast-value"
                altClassName="stat-alt"
              />
            </div>
          </div>
          <details className="assumption-list">
            <summary>Supuestos y fuentes de la proyección</summary>
            <ul>
              {data.projection.assumptions.map((assumption) => (
                <li key={assumption}>{assumption}</li>
              ))}
            </ul>
          </details>
          {data.emergencyFund ? (
            <div className="goal-mini">
              <div className="goal-mini-head">
                <span>
                  <span className="goal-dot" /> {data.emergencyFund.name}
                </span>
                <strong>{Math.round(data.emergencyFund.percent ?? 0)}%</strong>
              </div>
              <ProgressBar value={data.emergencyFund.percent ?? 0} label="Avance del fondo de emergencia" />
              <small>Te faltan {formatCents(data.emergencyFund.missingCents ?? 0)}</small>
            </div>
          ) : (
            <button type="button" className="secondary-button full-button" onClick={() => setRoute("settings")}>
              <Icon name="target" /> Configurar una meta de ahorro
            </button>
          )}
        </Panel>
      </div>

      <div className="content-grid dashboard-grid">
        <Panel title="Próximos pagos" subtitle="Obligaciones confirmadas." className="payments-panel">
          {data.upcomingPayments.length === 0 ? (
            <EmptyState icon="credit-card" title="Sin vencimientos pendientes" body="Importá y confirmá un resumen para verlos acá." />
          ) : (
            <div className="payments-list">
              {data.upcomingPayments.map((payment) => {
                const when = formatDayMonth(payment.due_date);
                return (
                  <div className="payment-row" key={payment.id}>
                    <div className="payment-date">
                      <strong>{when.day}</strong>
                      <span>{when.month}</span>
                    </div>
                    <div className="payment-info">
                      <strong>Vencimiento {payment.kind}</strong>
                      <span>{formatDate(payment.due_date)}</span>
                    </div>
                    <strong className="payment-amount">{formatCents(payment.amount_cents, payment.currency)}</strong>
                    <button
                      type="button"
                      className="check-button"
                      aria-label={`Marcar ${formatCents(payment.amount_cents)} como pagado`}
                      onClick={() => markPaid(payment.id)}
                    >
                      <Icon name="check" />
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </Panel>

        <Panel title={`Cierre de ${monthLabel(period).split(" ")[0]}`} subtitle="Checklist mensual." className="checklist-panel">
          <div className="checklist">
            <div className={`check-item ${data.income.monthCents > 0 ? "done" : ""}`}>
              <span className="custom-check">{data.income.monthCents > 0 && <Icon name="check" />}</span>
              <span>
                <strong>Registrar ingresos del mes</strong>
                <small>{data.income.monthCents > 0 ? "Cargado" : "Pendiente"}</small>
              </span>
            </div>
            <div className={`check-item ${pendingDocs === 0 && totalDocs > 0 ? "done" : ""}`}>
              <span className="custom-check">{pendingDocs === 0 && totalDocs > 0 && <Icon name="check" />}</span>
              <span>
                <strong>Revisar y confirmar resúmenes</strong>
                <small>
                  {totalDocs === 0 ? "Sin documentos" : `${totalDocs - pendingDocs}/${totalDocs} confirmados`}
                </small>
              </span>
            </div>
            <button type="button" className="check-item" onClick={() => setRoute("documents")}>
              <span className="custom-check" />
              <span>
                <strong>Importar nuevo resumen</strong>
                <small>{pendingDocs > 0 ? `${pendingDocs} pendientes` : "Al día"}</small>
              </span>
              <span className="check-arrow">
                <Icon name="arrow" />
              </span>
            </button>
            <button type="button" className="check-item" onClick={() => setRoute("spreadsheet")}>
              <span className="custom-check" />
              <span>
                <strong>Exportar planilla XLSX</strong>
                <small>10 hojas listas</small>
              </span>
              <span className="check-arrow">
                <Icon name="arrow" />
              </span>
            </button>
          </div>
        </Panel>
      </div>

      <div className="stats-grid compact">
        <article className="stat-card">
          <div className="stat-top">
            <span className="stat-label">Cuotas activas</span>
            <span className="stat-icon soft-blue">
              <Icon name="receipt" />
            </span>
          </div>
          <AmountStack
            cents={data.commitments.installmentsCents}
            usdCents={usdInstallments}
            className="stat-value"
            altClassName="stat-alt"
          />
          <div className="stat-foot">
            <span>{data.commitments.activeInstallments} cuotas</span>
          </div>
        </article>
        <article className="stat-card">
          <div className="stat-top">
            <span className="stat-label">Suscripciones</span>
            <span className="stat-icon soft-yellow">
              <Icon name="repeat" />
            </span>
          </div>
          <AmountStack
            cents={data.commitments.subscriptionsCents}
            usdCents={usdSubscriptions}
            className="stat-value"
            altClassName="stat-alt"
          />
          <div className="stat-foot">
            <span>{data.commitments.subscriptions} recurrentes</span>
          </div>
        </article>
        <article className="stat-card">
          <div className="stat-top">
            <span className="stat-label">Documentos</span>
            <span className="stat-icon">
              <Icon name="file" />
            </span>
          </div>
          <strong className="stat-value">{data.documents.total}</strong>
          <div className="stat-foot">
            <span>{pendingDocs} por revisar</span>
          </div>
        </article>
        <article className="stat-card">
          <div className="stat-top">
            <span className="stat-label">Pagos realizados</span>
            <span className="stat-icon soft-green">
              <Icon name="check" />
            </span>
          </div>
          <AmountStack
            cents={data.payments.paidCents}
            usdCents={usdPaid}
            className="stat-value"
            altClassName="stat-alt"
          />
          <div className="stat-foot">
            <span>este período</span>
          </div>
        </article>
      </div>

      <section className="insights-section">
        <div className="section-heading">
          <div>
            <h2>Señales para mirar</h2>
            <p>Insights automáticos sobre datos confirmados.</p>
          </div>
          <button type="button" className="ghost-button" onClick={() => setChatOpen(true)}>
            Preguntar por mis gastos <Icon name="arrow" />
          </button>
        </div>
        {data.insights.length === 0 ? (
          <EmptyState
            icon="trend"
            title="Todavía no hay señales"
            body="Cuando confirmes resúmenes, acá aparecen comparaciones y avisos explicables."
          />
        ) : (
          <div className="insights-grid">
            {data.insights.map((insight) => (
              <article className={`insight-card ${INSIGHT_CLASS[insight.severity] ?? "insight-blue"}`} key={insight.id}>
                <div className="insight-marker">
                  <Icon name={INSIGHT_ICON[insight.severity] ?? "info"} />
                </div>
                <div>
                  <span className="insight-type">
                    {insight.severity.toUpperCase()} · {insight.period ?? ""}
                  </span>
                  <h3>{insight.title}</h3>
                  <p>{insight.body}</p>
                  <details className="insight-evidence">
                    <summary>Ver evidencia</summary>
                    <ul>
                      {insight.evidence.map((item, index) => (
                        <li key={`${insight.id}-${index}`}>
                          {item.label}
                          {item.amountCents !== undefined ? `: ${formatCents(item.amountCents)}` : item.text ? `: ${item.text}` : ""}
                        </li>
                      ))}
                    </ul>
                    {insight.query && <code>{insight.query}</code>}
                  </details>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <div className="document-strip">
        <strong>Documentos pendientes</strong>
        {data.documents.pendingList.length === 0 ? (
          <span>Todos confirmados.</span>
        ) : (
          data.documents.pendingList.map((doc) => (
            <button key={doc.id} type="button" className="chip" onClick={() => setRoute("documents")}>
              {doc.filename} <StatusPill status={doc.status} />
            </button>
          ))
        )}
      </div>
    </>
  );
}
