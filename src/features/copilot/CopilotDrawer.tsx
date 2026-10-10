/** Copiloto local: preguntas con evidencia y fuentes visibles. */

import { useEffect, useRef, useState, type JSX } from "react";

import { Icon } from "../../components/Icon";
import { api } from "../../lib/backend";
import { formatCents } from "../../lib/format";
import { useApp } from "../../app/context";
import type { CopilotSource } from "../../types/api";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: CopilotSource[];
  evidenceAvailable?: boolean;
  engine?: string;
}

const SUGGESTIONS = [
  "¿Cuánto tengo que pagar?",
  "¿Qué cuotas siguen?",
  "¿Hay gastos repetidos?",
  "¿Cuándo cobro el sueldo?",
];

/**
 * Texto de la respuesta en párrafos y viñetas.
 *
 * El modelo local a veces devuelve markdown suelto (`- `, `**`, `#`); sin esto
 * el widget lo mostraría con los asteriscos a la vista.
 */
function AnswerText({ content, role }: { content: string; role: "user" | "assistant" }): JSX.Element {
  const blocks: JSX.Element[] = [];
  let listItems: string[] = [];

  const flushList = () => {
    if (listItems.length === 0) return;
    const items = [...listItems];
    blocks.push(
      <ul key={`ul-${blocks.length}`} className="answer-list">
        {items.map((item, index) => (
          <li key={index}>{stripMarkdown(item)}</li>
        ))}
      </ul>,
    );
    listItems = [];
  };

  for (const raw of content.split(/\n+/)) {
    const line = raw.trim();
    if (!line) continue;
    if (/^[-*•]\s+/.test(line) || /^\d+[.)]\s+/.test(line)) {
      listItems.push(line.replace(/^([-*•]|\d+[.)])\s+/, ""));
      continue;
    }
    flushList();
    blocks.push(<p key={`p-${blocks.length}`}>{stripMarkdown(line)}</p>);
  }
  flushList();

  if (blocks.length === 0) return <p>{content}</p>;
  return <div className={`answer-body ${role}`}>{blocks}</div>;
}

function stripMarkdown(text: string): string {
  return text
    .replace(/^\s*#{1,6}\s*/, "")
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/__(.*?)__/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .trim();
}

export function CopilotDrawer({ open, onClose }: { open: boolean; onClose: () => void }): JSX.Element {
  const { period, toast } = useApp();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open && messages.length === 0) {
      void api
        .copilotHistory()
        .then((history) => {
          setMessages(
            history.messages.map((message) => ({
              id: message.id,
              role: message.role === "user" ? "user" : "assistant",
              content: message.content,
              sources: message.sources as CopilotSource[],
            })),
          );
        })
        .catch(() => undefined);
    }
  }, [open, messages.length]);

  useEffect(() => {
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const ask = async (question: string) => {
    const trimmed = question.trim();
    if (!trimmed || busy) return;
    setInput("");
    setMessages((current) => [...current, { id: `u-${Date.now()}`, role: "user", content: trimmed }]);
    setBusy(true);
    try {
      const answer = await api.copilot(trimmed, period);
      setMessages((current) => [
        ...current,
        {
          id: `a-${Date.now()}`,
          role: "assistant",
          content: answer.answer,
          sources: answer.sources,
          evidenceAvailable: answer.evidenceAvailable,
          engine: answer.engine,
        },
      ]);
    } catch (error) {
      toast(error instanceof Error ? error.message : "El copiloto no está disponible", "error");
      setMessages((current) => [
        ...current,
        {
          id: `e-${Date.now()}`,
          role: "assistant",
          content: "No pude consultar los datos locales. Revisá que el backend y el modelo estén disponibles.",
          evidenceAvailable: false,
        },
      ]);
    } finally {
      setBusy(false);
    }
  };

  const clear = async () => {
    try {
      await api.clearHistory();
      setMessages([]);
      toast("Historial del copiloto borrado.");
    } catch (error) {
      toast(error instanceof Error ? error.message : "No se pudo borrar el historial", "error");
    }
  };

  return (
    <>
      <aside className={`chat-drawer ${open ? "open" : ""}`} aria-hidden={!open}>
        <div className="chat-header">
          <div>
            <div className="chat-title">
              <span className="ai-orb">
                <Icon name="spark" />
              </span>
              <strong>Copiloto local</strong>
              <span className="online-dot" />
            </div>
            <small>Responde solo con datos confirmados y muestra sus fuentes</small>
          </div>
          <div className="chat-header-actions">
            <button
              type="button"
              className="icon-button"
              aria-label="Reiniciar conversación"
              title="Reiniciar conversación"
              onClick={clear}
            >
              <Icon name="refresh" />
            </button>
            <button
              type="button"
              className="icon-button"
              aria-label="Cerrar copiloto"
              title="Cerrar copiloto"
              onClick={onClose}
            >
              <Icon name="close" />
            </button>
          </div>
        </div>

        <div className="chat-body" ref={bodyRef}>
          {messages.length === 0 && (
            <div className="chat-message assistant">
              <span className="chat-avatar">
                <Icon name="spark" />
              </span>
              <div>
                <p>Hola. Puedo responderte sobre tus datos confirmados de {period}. ¿Qué querés entender mejor?</p>
                <small>Solo uso lo que confirmaste en la app.</small>
              </div>
            </div>
          )}

          {messages.map((message) => (
            <div key={message.id} className={message.role === "user" ? "user-message" : "chat-message assistant"}>
              {message.role === "assistant" && (
                <span className="chat-avatar">
                  <Icon name="spark" />
                </span>
              )}
              <div>
                <AnswerText content={message.content} role={message.role} />
                {message.role === "assistant" && message.sources && message.sources.length > 0 && (
                  <details className="source-details">
                    <summary>{message.sources.length} fuentes usadas</summary>
                    <ul className="source-list">
                      {message.sources.map((source) => (
                        <li key={source.id}>
                          <code>{source.id}</code> {source.label}
                          {source.amountCents !== undefined ? ` · ${formatCents(source.amountCents)}` : ""}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
                {message.role === "assistant" && message.evidenceAvailable === false && (
                  <small className="no-evidence">
                    <Icon name="info" /> Sin datos confirmados suficientes
                  </small>
                )}
              </div>
            </div>
          ))}

          {busy && (
            <div className="chat-message assistant">
              <span className="chat-avatar">
                <Icon name="spark" />
              </span>
              <div>
                <p>Buscando en tus datos confirmados…</p>
              </div>
            </div>
          )}
        </div>

        {/* Las sugerencias solo aparecen con la conversación reiniciada. */}
        {messages.length === 0 && (
          <div className="suggested-prompts">
            {SUGGESTIONS.map((suggestion) => (
              <button key={suggestion} type="button" onClick={() => ask(suggestion)} disabled={busy}>
                {suggestion}
              </button>
            ))}
          </div>
        )}

        <form
          className="chat-input"
          onSubmit={(event) => {
            event.preventDefault();
            void ask(input);
          }}
        >
          <input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Preguntale sobre tus finanzas…"
            aria-label="Pregunta al copiloto"
            autoComplete="off"
          />
          <button type="submit" aria-label="Enviar pregunta" disabled={busy}>
            <Icon name="arrow-up" />
          </button>
        </form>
      </aside>
      <div className={`drawer-backdrop ${open ? "open" : ""}`} onClick={onClose} role="presentation" />
    </>
  );
}
